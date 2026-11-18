import base64, contextlib, copy, io, json, os, shutil, subprocess, sys, tempfile, unittest, uuid, xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from akl.config import Config, ROOT, example
from akl.core import LabError, lock, private_dir, sha256, write_json
from akl.guest import Guest, render_script
from akl.vm import Lab, network_xml, customize
from akl import cli, console, project, recovery, windows


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.c=Config(example(str(self.base/'work'),str(self.base/'mount/data'),str(self.base/'mount')),self.base/'lab.json')
        self.c.validate();self.c.workspace.mkdir();self.c.state.mkdir();self.c.storage.mkdir(parents=True)

class Configuration(Fixture):
    def test_reject_bad_paths_and_subnets(self):
        for key,value in [('workspace','relative'),('storage',str(self.c.mount)),('storage',str(self.c.workspace/'data')),('mount','/mnt/a,b'),('subnet','8.8.8.0/24'),('subnet','127.0.0.0/24'),('subnet','192.168.0.0/16'),('lab_id','../../x')]:
            with self.subTest(key=key,value=value):
                d=copy.deepcopy(self.c.data);d[key]=value
                with self.assertRaises(ValueError):Config(d,self.c.path).validate()
    def test_instances_do_not_share_macs(self):
        d=copy.deepcopy(self.c.data);d['instance_id']=str(uuid.uuid4());other=Config(d,self.c.path)
        self.assertNotEqual(self.c.mac('dev'),other.mac('dev'));self.assertNotEqual(self.c.mac('dev'),self.c.mac('target'))
    def test_hash_tracks_resource_changes(self):
        original=self.c.fingerprint();self.c.data['vms']['dev']['cpus']=6;self.assertNotEqual(original,self.c.fingerprint())
    def test_network_isolated_and_nat(self):
        n=ET.fromstring(network_xml(self.c));self.assertIsNone(n.find('forward'))
        self.assertEqual({x.get('ip') for x in n.findall('ip/dhcp/host')},{self.c.ip('dev'),self.c.ip('target')})
        self.assertEqual(ET.fromstring(network_xml(self.c,'nat')).find('forward').get('mode'),'nat')
    def test_answer_escapes_values_and_contains_no_unresolved_markers(self):
        self.c.data['windows_timezone']='A&B';text=windows.answer(self.c,'dev','x<&y')
        root=ET.fromstring(text);ns={'u':'urn:schemas-microsoft-com:unattend'}
        self.assertIn('x<&y',[x.text for x in root.findall('.//u:Password/u:Value',ns)]);self.assertNotIn('@@',text)
    def test_render_every_guest_helper(self):
        self.c.data['lab_id']='research';self.c.data['subnet']='10.99.12.0/24';self.c.data['media']['openssh']={'sha256':'a'*64}
        for p in (ROOT/'guest').glob('*.ps1'):
            text=render_script(self.c,p.read_text());self.assertNotIn('@@',text,p.name);self.assertNotIn('192.168.231.1',text,p.name)
    def test_guest_renderer_runs_without_linux_modules(self):
        # Reproduce Windows' missing host modules while executing the actual CLI.
        output=self.base/'portable-guest'
        code="""
import builtins,runpy,sys
original_import=builtins.__import__
def portable_import(name,*args,**kwargs):
    if name.split('.')[0] in ('fcntl','pwd','grp','resource'):
        raise ModuleNotFoundError('Windows does not provide '+name)
    return original_import(name,*args,**kwargs)
builtins.__import__=portable_import
script=sys.argv[1]
sys.argv=sys.argv[1:]
runpy.run_path(script,run_name='__main__')
"""
        result=subprocess.run([sys.executable,'-c',code,str(ROOT/'tools/render-guest.py'),'--output',str(output)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['rendered'],19)
        self.assertNotIn('@@',(output/'Bootstrap.ps1').read_text())

    def test_private_atomic_json_and_lock(self):
        write_json(self.c.state/'private.json',{'test':1});self.assertEqual((self.c.state/'private.json').stat().st_mode&0o777,0o600)
        with lock(self.c):
            with self.assertRaises(LabError):
                with lock(self.c):pass
    def test_private_dir_rejects_symlink(self):
        p=self.c.workspace/'alias';p.symlink_to(self.c.state,target_is_directory=True)
        with self.assertRaises(LabError):private_dir(p)
    def test_config_missing_is_json_error(self):
        output=io.StringIO()
        with contextlib.redirect_stderr(output):code=cli.main(['--config',str(self.base/'missing'),'status'])
        self.assertEqual(code,1);self.assertFalse(json.loads(output.getvalue())['ok'])

class Transport(Fixture):
    def test_encoded_powershell_does_not_interpolate_shell(self):
        g=Guest(self.c,'dev');code="Write-Output '$()`;&'"
        with patch.object(g,'invoke',return_value={'exit_code':0}) as invoke:
            g.command(code);argv=invoke.call_args.args[0]
        decoded=base64.b64decode(argv[-1].split()[-1]).decode('utf-16le')
        self.assertTrue(decoded.endswith(code));self.assertIn('PubkeyAuthentication=yes',argv);self.assertIn('IdentitiesOnly=yes',argv)
    def test_long_inline_rejected_before_ssh(self):
        with self.assertRaises(LabError):Guest(self.c,'dev').command('x'*5000)
    def test_scp_shell_metacharacters_rejected(self):
        for p in ['C:/x;whoami','C:/../secret','relative','C:/x$(foo)','C:/two words','C:/x\nfoo']:
            with self.subTest(path=p),self.assertRaises(LabError):Guest._remote(p)
        Guest._remote('C:/Lab/file.zip')
    def test_console_validates_entire_batch(self):
        with self.assertRaises(ValueError):console.validate([{'action':'key','keys':'enter'},{'action':'reset'}])
        with self.assertRaises(ValueError):console.validate([{'action':'wait','seconds':6}])
        with self.assertRaises(ValueError):console.validate([{'action':'key','keys':'enter;foo'}])
        console.validate([{'action':'screenshot'},{'action':'key','keys':'ctrl-alt-delete'}])

class FakeLab(Lab):
    def __init__(self,c,states=None):
        super().__init__(c);self.states=states or {'dev':'shut off','target':'shut off'};self.calls=[]
    def owned(self):self.calls.append(('owned',))
    def state(self,role):return self.states[role]
    def status(self):return dict(self.states)
    def virsh(self,*args):
        self.calls.append(args)
        if args[0] in ('start','resume'):
            role='dev' if args[1]==self.c.name('dev') else 'target';self.states[role]='paused' if '--paused' in args else 'running'
        return ''
    def cable(self,connected):self.calls.append(('cable',connected))
    def wait_ssh(self,role,timeout=600):self.calls.append(('ssh',role))

class Lifecycle(Fixture):
    def setUp(self):
        super().setUp();write_json(self.c.state/'installed.json',{})
        p=patch('akl.vm.root');p.start();self.addCleanup(p.stop)
    def test_cold_start_serial_order(self):
        lab=FakeLab(self.c);lab.start();calls=lab.calls
        self.assertLess(calls.index(('cable',False)),calls.index(('resume',self.c.name('dev'))))
        self.assertLess(calls.index(('ssh','dev')),calls.index(('resume',self.c.name('target'))))
        self.assertLess(calls.index(('ssh','target')),calls.index(('cable',True)))
    def test_existing_pause_never_resumed(self):
        lab=FakeLab(self.c,{'dev':'paused','target':'shut off'})
        with self.assertRaises(LabError):lab.start()
        self.assertEqual(lab.calls,[('owned',)])
    def test_dev_ready_failure_never_resumes_target(self):
        lab=FakeLab(self.c)
        with patch.object(lab,'wait_ssh',side_effect=LabError('timeout')):
            with self.assertRaises(LabError):lab.start()
        self.assertNotIn(('resume',self.c.name('target')),lab.calls);self.assertEqual(lab.state('target'),'paused')
    def test_interrupted_restore_blocks_boot(self):
        write_json(self.c.state/'restore-in-progress.json',{});lab=FakeLab(self.c)
        with self.assertRaises(LabError):lab.start()
        self.assertEqual(lab.calls,[('owned',)])
    def test_watchdog_pause_during_start_blocks_target_resume(self):
        lab=FakeLab(self.c)
        def wait(role,timeout=600):lab.states['dev']='paused'
        with patch.object(lab,'wait_ssh',side_effect=wait):
            with self.assertRaises(LabError):lab.start()
        self.assertNotIn(('resume',self.c.name('target')),lab.calls)
    def test_resume_provision_requires_exact_fingerprint(self):
        write_json(self.c.state/'manifest.json',{'phase':'provisioning','config_sha256':'wrong'})
        with patch('akl.windows.root'),patch('akl.windows.require_storage'):
            with self.assertRaises(LabError):windows.provision(self.c,True,True)
    def test_provision_refuses_existing_storage_before_any_virsh(self):
        with patch('akl.windows.root'),patch('akl.windows.require_storage'),patch.object(Lab,'virsh') as virsh:
            with self.assertRaises(LabError):windows.provision(self.c,True)
        virsh.assert_not_called()
    def test_ownership_rejects_uuid_before_mutation(self):
        m={'config_sha256':self.c.fingerprint(),'uuids':{'dev':str(uuid.uuid4())}}
        write_json(self.c.state/'manifest.json',m)
        write_json(self.c.storage/'.akl-owner.json',{'instance_id':self.c.data['instance_id']})
        d=ET.fromstring('<domain><uuid>wrong</uuid><metadata><instance xmlns="urn:agent-kernel-lab:1">'+self.c.data['instance_id']+'</instance></metadata></domain>')
        with patch('akl.vm.require_storage',return_value={}),patch.object(Lab,'domain',return_value=d),patch.object(Lab,'virsh') as virsh:
            with self.assertRaisesRegex(LabError,'UUID'):Lab(self.c).owned()
        virsh.assert_not_called()

class BuildAndRecovery(Fixture):
    def test_source_archive_deterministic(self):
        source=ROOT/'examples/observable-echo/kmdf';a=self.base/'a.zip';b=self.base/'b.zip'
        hashes=project.archive(source,a);project.archive(source,b)
        self.assertEqual(a.read_bytes(),b.read_bytes());self.assertIn('driver/AutoSync/queue.c',hashes)
    def test_source_rejects_binary_and_symlink(self):
        source=self.base/'source';shutil.copytree(ROOT/'examples/observable-echo/kmdf',source)
        (source/'private.key').write_text('secret')
        with self.assertRaises(LabError):project.source_files(source)
        (source/'private.key').unlink();(source/'link.c').symlink_to(source/'exe/public.h')
        with self.assertRaises(LabError):project.source_files(source)
    def test_bad_media_hash_rejected(self):
        f=self.base/'fake';f.write_bytes(b'bad')
        self.c.data['media']={k:{'path':str(f),'sha256':'0'*64} for k in ('windows','ewdk','openssh')}
        with self.assertRaises(LabError):windows.verify_media(self.c)
    def test_invalid_pair_never_creates_rollback_or_mutates(self):
        with patch('akl.recovery.root'),patch.object(Lab,'owned'),patch.object(Lab,'stopped'),patch('akl.recovery.validate',side_effect=LabError('target invalid')),patch('akl.recovery.create') as create,patch('akl.recovery.run') as run:
            with self.assertRaises(LabError):recovery.restore(self.c,'test')
        create.assert_not_called();run.assert_not_called()
    def test_checkpoint_integrity_detects_tampering(self):
        directory=self.base/'bundle';directory.mkdir();(directory/'data').write_bytes(b'one');before=recovery.inventory(directory)
        (directory/'data').write_bytes(b'two');self.assertNotEqual(before,recovery.inventory(directory))
    def test_recovery_label_rejects_traversal(self):
        for label in ('../x','a/b','a b',''):
            with self.assertRaises(ValueError):recovery.label_ok(label)
    @unittest.skipUnless(shutil.which('qemu-img') and shutil.which('qemu-io'),'QEMU image tools required')
    def test_real_qcow2_snapshot_and_restore(self):
        disk=self.base/'small.qcow2'
        def run(*args):return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        run('qemu-img','create','-f','qcow2',str(disk),'8M')
        run('qemu-io','-f','qcow2','-c','write -P 0x41 0 4096',str(disk))
        run('qemu-img','snapshot','-c','original',str(disk))
        run('qemu-io','-f','qcow2','-c','write -P 0x42 0 4096',str(disk))
        run('qemu-img','snapshot','-a','original',str(disk))
        run('qemu-io','-f','qcow2','-c','read -P 0x41 0 4096',str(disk))
        self.assertEqual(recovery.info(disk)['format'],'qcow2');run('qemu-img','check',str(disk))


class RestorePairValidation(Fixture):
    def test_second_guest_identity_corruption_blocks_restore(self):
        label='baseline';bundle=self.c.storage/'checkpoints'/label;bundle.mkdir(parents=True)
        write_json(bundle/'bundle.json',{'schema_version':1,'instance_id':self.c.data['instance_id'],'config_sha256':self.c.fingerprint(),'kind':'checkpoint','label':label})
        metadata={}
        for role in ('dev','target'):
            uid=str(uuid.uuid4());paths={'disk':str(self.c.disk(role)),'uuid':uid,'nvram':'/var/lib/libvirt/qemu/nvram/'+role+'.fd','tpm':'/var/lib/libvirt/swtpm/'+uid}
            xml='<domain><name>'+self.c.name(role)+'</name><uuid>'+uid+'</uuid><metadata><instance xmlns="urn:agent-kernel-lab:1">'+self.c.data['instance_id']+'</instance></metadata><os><nvram>'+paths['nvram']+'</nvram></os><devices><disk device="disk"><source file="'+paths['disk']+'"/></disk></devices></domain>'
            metadata[role]=(xml,paths);item=bundle/role;item.mkdir();(item/'tpm').mkdir();(item/'tpm/state').write_bytes(b'tpm');(item/'nvram.fd').write_bytes(b'nvram');write_json(item/'paths.json',paths)
            # Integrity can pass even if a bundle was deliberately edited; identity must still fail.
            (item/'domain.xml').write_text(xml.replace(uid,'wrong-uuid') if role=='target' else xml)
        write_json(bundle/'integrity.json',recovery.inventory(bundle));(bundle/'COMPLETE').touch()
        with patch('akl.recovery.root'),patch.object(Lab,'owned'),patch.object(Lab,'stopped'),patch('akl.recovery.metadata',side_effect=lambda c,r:metadata[r]),patch('akl.recovery.info',return_value={'format':'qcow2','snapshots':[{'name':label}]}),patch('akl.recovery.run') as command,patch('akl.recovery.create') as create:
            with self.assertRaisesRegex(LabError,'identity'):recovery.restore(self.c,label)
        create.assert_not_called()
        self.assertTrue(all(call.args[0]=='virt-xml-validate' for call in command.call_args_list))
    def test_foreign_mount_identity_blocks_owned(self):
        write_json(self.c.storage/'.akl-owner.json',{'instance_id':self.c.data['instance_id'],'mount_uuid':'original-volume'})
        with patch('akl.vm.require_storage',return_value={'uuid':'different-volume'}),patch.object(Lab,'domain') as domain:
            with self.assertRaisesRegex(LabError,'filesystem UUID'):Lab(self.c).owned()
        domain.assert_not_called()
    def test_custom_domain_keeps_secure_boot_distinction(self):
        xml='<domain><name>template</name><os><type arch="x86_64">hvm</type></os><devices><serial/><console/><channel/><redirdev/><filesystem/><graphics type="spice"/></devices></domain>'
        for role in ('dev','target'):
            d=ET.fromstring(customize(xml,self.c,role))
            self.assertEqual(d.find("os/firmware/feature[@name='enrolled-keys']").get('enabled'),'yes' if role=='dev' else 'no')
            for tag in ('console','channel','redirdev','filesystem'):self.assertIsNone(d.find('devices/'+tag))
            self.assertEqual(d.find('devices/serial/source').get('path'),self.c.socket)


if __name__=='__main__':unittest.main()
