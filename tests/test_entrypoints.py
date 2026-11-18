"""Setup/teardown regression tests; no host VMs, mounts or packages are modified."""
from pathlib import Path
import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from akl.config import Config, example
from akl.core import LabError, write_json, observer_lock
from akl.vm import Lab
from akl import cleanup


def load_tool(name):
    spec = importlib.util.spec_from_file_location('entry_'+name, ROOT/'tools'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


quick = load_tool('quickstart')
clean = load_tool('cleanup')


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base/'instance.json'

    def options(self):
        options = ['--config', str(self.config), '--configure-only', '--workspace', str(self.base/'work'),
                   '--mount', str(self.base/'mount'), '--storage', str(self.base/'mount/data'),
                   '--lab-id', 'trial', '--subnet', '10.27.8.0/24']
        for kind in ('windows', 'ewdk', 'openssh'):
            media = self.base/(kind+'.media');media.write_bytes(kind.encode())
            options += ['--'+kind, str(media)]
        return options

    def test_configure_only_never_invokes_host_commands(self):
        with patch.object(quick, 'invoke') as invoke, patch.object(quick, 'prerequisites') as deps, patch('os.geteuid', return_value=1000), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(quick.main(self.options()), 0)
        invoke.assert_not_called();deps.assert_not_called()
        c = Config.load(self.config)
        self.assertEqual(set(c.data['media']), {'windows', 'ewdk', 'openssh'})
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertTrue((c.workspace/'.akl-workspace.json').is_file())
        self.assertFalse(c.storage.exists())

    def test_existing_config_is_preserved(self):
        args = quick.parser().parse_args(self.options())
        with contextlib.redirect_stdout(io.StringIO()):c = quick.create_config(args)
        before = self.config.read_bytes()
        with self.assertRaisesRegex(LabError, 'already exists'):quick.create_config(args)
        self.assertEqual(self.config.read_bytes(), before)
        reused = quick.create_config(quick.parser().parse_args(['--config', str(self.config)]))
        self.assertEqual(reused.data['instance_id'], c.data['instance_id'])

    def test_missing_media_does_not_save_partial_config(self):
        args = quick.parser().parse_args(self.options());args.windows = str(self.base/'missing')
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(LabError):quick.create_config(args)
        self.assertFalse(self.config.exists())

    def test_installed_instance_only_starts_never_provisions(self):
        c = Config(example(str(self.base/'work'), str(self.base/'mount/data'), str(self.base/'mount')), self.config)
        write_json(c.state/'installed.json', {})
        def invoke(config, *args, **kwargs):return {'ready': True} if args[0] == 'doctor' else {}
        with patch.object(quick, 'invoke', side_effect=invoke) as call, patch.object(quick, 'prerequisites'), contextlib.redirect_stdout(io.StringIO()):
            quick.advance(c, quick.parser().parse_args([]))
        self.assertEqual([x.args[1] for x in call.call_args_list], ['doctor', 'start'])

    def test_incomplete_tools_resume_without_reinstall(self):
        c = Config(example(str(self.base/'work'), str(self.base/'mount/data'), str(self.base/'mount')), self.config)
        write_json(c.state/'installed.json', {});write_json(c.state/'quickstart-install.json', {'tools_configured': False})
        def invoke(config, *args, **kwargs):return {'ready': True} if args[0] == 'doctor' else {}
        with patch.object(quick, 'invoke', side_effect=invoke) as call, patch.object(quick, 'prerequisites'), contextlib.redirect_stdout(io.StringIO()):
            quick.advance(c, quick.parser().parse_args([]))
        self.assertEqual([x.args[1] for x in call.call_args_list], ['doctor', 'start', 'sync-tools', 'guest'])
        self.assertTrue(json.loads((c.state/'quickstart-install.json').read_text())['tools_configured'])

    def test_started_guest_is_not_reinstalled(self):
        c = Config(example(str(self.base/'work'), str(self.base/'mount/data'), str(self.base/'mount')), self.config)
        write_json(c.state/'manifest.json', {'phase': 'provisioned'})
        write_json(c.state/'install-started-target.json', {})
        def invoke(config, *args, **kwargs):
            return {'ready': True} if args[0] == 'doctor' else {'guests': {'target': {'state': 'paused'}}}
        with patch.object(quick, 'invoke', side_effect=invoke) as call, patch.object(quick, 'prerequisites'), self.assertRaisesRegex(LabError, 'already started'):
            quick.advance(c, quick.parser().parse_args([]))
        self.assertNotIn('install-start', [x.args[1] for x in call.call_args_list])

    def test_doctor_not_ready_blocks_provision(self):
        c = Config(example(str(self.base/'work'), str(self.base/'mount/data'), str(self.base/'mount')), self.config)
        with patch.object(quick, 'invoke', return_value={'ready': False}) as call, patch.object(quick, 'prerequisites'), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(LabError):
            quick.advance(c, quick.parser().parse_args([]))
        self.assertEqual(call.call_count, 1)

    def test_shell_launchers_work_outside_checkout(self):
        for name in ('quickstart.sh', 'cleanup.sh'):
            result = subprocess.run(['bash', str(ROOT/name), '--help'], cwd=self.base, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('usage:', result.stdout)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.c = Config(example(str(self.base/'work'), str(self.base/'mount/data'), str(self.base/'mount')), self.base/'config.json')
        self.c.validate();self.c.storage.mkdir(parents=True);self.c.state.mkdir(parents=True)
        self.manifest = {'config_sha256': self.c.fingerprint(), 'mount_uuid': 'volume',
                         'uuids': {role: str(uuid.uuid4()) for role in cleanup.ROLES}, 'network_uuid': str(uuid.uuid4())}
        write_json(self.c.path, self.c.data);write_json(self.c.state/'manifest.json', self.manifest)
        write_json(self.c.storage/'.akl-owner.json', {'instance_id': self.c.data['instance_id'], 'mount_uuid': 'volume'})
        self.domains = {self.c.name(role): self.domain_xml(role) for role in cleanup.ROLES}
        self.states = {role: 'shut off' for role in cleanup.ROLES}
        self.network = True;self.network_uuid = self.manifest['network_uuid'];self.calls = []
        self.mounts = [{'target': '/'}]
        for target, kwargs in [
            ('akl.cleanup.root', {}),
            ('akl.cleanup.external_symlink', {'return_value': False}),
            ('akl.cleanup.require_storage', {'return_value': {'uuid': 'volume'}}),
            ('akl.cleanup.run', {'side_effect': lambda *a: json.dumps({'filesystems': self.mounts})}),
            ('akl.cleanup.Lab.virsh', {'side_effect': self.virsh}),
            ('akl.cleanup.Lab.domain', {'side_effect': lambda role: ET.fromstring(self.domains[self.c.name(role)])}),
            ('akl.cleanup.Lab.state', {'side_effect': lambda role: self.states[role]}),
        ]:
            patcher = patch(target, **kwargs);patcher.start();self.addCleanup(patcher.stop)

    def domain_xml(self, role):
        return ('<domain><name>'+self.c.name(role)+'</name><uuid>'+self.manifest['uuids'][role]+'</uuid>'
                '<metadata><instance xmlns="urn:agent-kernel-lab:1">'+self.c.data['instance_id']+'</instance></metadata>'
                '<os/><devices><disk device="disk"><source file="'+str(self.c.disk(role))+'"/></disk></devices></domain>')

    def virsh(self, *args):
        self.calls.append(args)
        if args[0] == 'list':return '\n'.join(self.domains)
        if args[0] == 'net-list':return self.c.network if self.network else ''
        if args[0] == 'net-dumpxml':return '<network><uuid>'+self.network_uuid+'</uuid></network>'
        if args[0] == 'dumpxml':return self.domains[args[1]]
        if args[0] == 'domstate':return 'shut off'
        if args[0] == 'destroy':
            self.states[next(r for r in cleanup.ROLES if self.manifest['uuids'][r] == args[1])] = 'shut off'
        if args[0] == 'undefine':
            role = next(r for r in cleanup.ROLES if self.manifest['uuids'][r] == args[1]);self.domains.pop(self.c.name(role))
        if args[0] == 'net-undefine':self.network = False
        return ''

    def mutations(self):
        return [x for x in self.calls if x[0] in ('destroy', 'undefine', 'net-destroy', 'net-undefine')]

    def test_cleanup_entrypoint_defaults_to_preview(self):
        with patch('os.geteuid', return_value=0), patch.object(clean.cleanup, 'execute') as execute, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(clean.main(['--config', str(self.c.path)]), 0)
        execute.assert_not_called();self.assertFalse(self.mutations())

    def test_unattended_delete_requires_explicit_uuid(self):
        with patch('os.geteuid', return_value=0), patch('sys.stdin.isatty', return_value=False), patch.object(clean.cleanup, 'execute') as execute, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(clean.main(['--config', str(self.c.path), '--delete']), 1)
        execute.assert_not_called();self.assertFalse(self.mutations())

    def test_preview_does_not_mutate(self):
        result = cleanup.plan(self.c)
        self.assertEqual(set(result['domains']), {'dev', 'target'})
        self.assertFalse(self.mutations());self.assertTrue(self.c.storage.exists())

    def test_wrong_confirmation_never_mutates(self):
        with self.assertRaises(LabError):cleanup.execute(self.c, 'wrong')
        self.assertFalse(self.mutations())

    def test_other_vm_sharing_storage_blocks_all_deletion(self):
        self.domains['unrelated'] = '<domain><devices><disk><source file="'+str(self.c.disk('target'))+'"/></disk></devices></domain>'
        with self.assertRaisesRegex(LabError, 'Another domain'):cleanup.execute(self.c, self.c.data['instance_id'])
        self.assertFalse(self.mutations());self.assertTrue(self.c.storage.exists())

    def test_shared_bridge_blocks_all_deletion(self):
        self.domains['unrelated'] = '<domain><devices><interface><source bridge="'+self.c.bridge+'"/></interface></devices></domain>'
        with self.assertRaisesRegex(LabError, 'network'):cleanup.execute(self.c, self.c.data['instance_id'])
        self.assertFalse(self.mutations())

    def test_domain_identity_mismatch_blocks_all_deletion(self):
        self.domains[self.c.name('dev')] = self.domains[self.c.name('dev')].replace(self.manifest['uuids']['dev'], str(uuid.uuid4()))
        with self.assertRaisesRegex(LabError, 'ownership'):cleanup.execute(self.c, self.c.data['instance_id'])
        self.assertFalse(self.mutations())

    def test_foreign_network_blocks_all_deletion(self):
        self.network_uuid = str(uuid.uuid4())
        with self.assertRaisesRegex(LabError, 'Network ownership'):cleanup.execute(self.c, self.c.data['instance_id'])
        self.assertFalse(self.mutations())

    def test_nested_mount_blocks_all_deletion(self):
        self.mounts.append({'target': str(self.c.storage/'foreign-mount')})
        with self.assertRaisesRegex(LabError, 'mount'):cleanup.execute(self.c, self.c.data['instance_id'])
        self.assertFalse(self.mutations())

    def test_external_tpm_mount_blocks_all_deletion(self):
        self.mounts.append({'target': '/var/lib/libvirt/swtpm/'+self.manifest['uuids']['dev']})
        with self.assertRaisesRegex(LabError, 'mounted'):cleanup.execute(self.c, self.c.data['instance_id'])
        self.assertFalse(self.mutations())

    def test_active_guest_requires_force(self):
        self.states['target'] = 'running'
        with self.assertRaisesRegex(LabError, 'active'):cleanup.execute(self.c, self.c.data['instance_id'])
        self.assertFalse(self.mutations());self.assertFalse((self.c.state/'cleanup-in-progress.json').exists())

    def test_delete_only_owned_temp_trees_and_leave_symlink_target(self):
        outside = self.base/'unrelated';outside.mkdir();(outside/'keep').write_text('user data')
        (self.c.storage/'link').symlink_to(outside, target_is_directory=True)
        with patch('akl.cleanup.remove_external') as external:
            cleanup.execute(self.c, self.c.data['instance_id'])
        self.assertFalse(self.c.storage.exists());self.assertFalse(self.c.workspace.exists());self.assertFalse(self.c.path.exists())
        self.assertTrue((outside/'keep').exists());self.assertTrue(external.called)
        self.assertTrue(all('--remove-all-storage' not in x for x in self.mutations()))

    def test_force_stops_guests_before_undefine(self):
        self.states['dev'] = 'running'
        with patch('akl.cleanup.remove_external'):cleanup.execute(self.c, self.c.data['instance_id'], force=True)
        operations = [x[0] for x in self.mutations()]
        self.assertLess(operations.index('destroy'), operations.index('undefine'))

    def test_interrupted_cleanup_can_resume_missing_domain(self):
        nvram='/var/lib/libvirt/qemu/nvram/'+self.c.name('target')+'_VARS.fd'
        self.domains[self.c.name('target')]=self.domains[self.c.name('target')].replace('<os/>', '<os><nvram>'+nvram+'</nvram></os>')
        preview = cleanup.plan(self.c);write_json(self.c.state/'cleanup-in-progress.json', preview)
        self.domains.pop(self.c.name('target'))
        with patch('akl.cleanup.remove_external') as external:cleanup.execute(self.c, self.c.data['instance_id'])
        self.assertIn(nvram, [call.args[0]['path'] for call in external.call_args_list])
        self.assertFalse(self.c.workspace.exists());self.assertFalse(self.network)

    def test_unprovisioned_workspace_has_no_external_state_to_delete(self):
        (self.c.state/'manifest.json').unlink();shutil.rmtree(self.c.storage)
        write_json(self.c.workspace/'.akl-workspace.json', {'instance_id': self.c.data['instance_id']})
        self.domains.clear();self.network = False
        result = cleanup.plan(self.c)
        self.assertFalse(result['external_state'])

    def test_active_watchdog_blocks_teardown(self):
        with observer_lock(self.c):
            with self.assertRaisesRegex(LabError, 'watchdog'):cleanup.execute(self.c, self.c.data['instance_id'])
        self.assertFalse(self.mutations());self.assertTrue(self.c.storage.exists())

    def test_unexpected_nvram_path_is_rejected(self):
        with self.assertRaisesRegex(LabError, 'NVRAM'):
            cleanup.external_paths(self.c, 'dev', self.manifest['uuids']['dev'], '/etc/unrelated-file')
        with self.assertRaisesRegex(LabError, 'NVRAM'):
            cleanup.external_paths(self.c, 'dev', self.manifest['uuids']['dev'], '/var/lib/libvirt/qemu/nvram/other_VARS.fd')

    def test_cleanup_marker_blocks_normal_lifecycle(self):
        write_json(self.c.state/'cleanup-in-progress.json', {})
        with self.assertRaisesRegex(LabError, 'Cleanup'):Lab(self.c).owned()


if __name__ == '__main__':unittest.main()
