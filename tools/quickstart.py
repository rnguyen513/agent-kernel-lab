#!/usr/bin/env python3
"""Interactive setup and resumable Windows installation; existing instances are preserved."""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from akl.config import Config, example
from akl.core import LabError, sha256, write_json

MEDIA = {'windows': 'Windows 11 Pro x64 en-US ISO', 'ewdk': 'EWDK ISO',
         'openssh': 'Microsoft Win32-OpenSSH x64 ZIP'}


def ask(label, default=None):
    if not sys.stdin.isatty():
        raise LabError('Interactive input required; provide the missing options or use an existing --config.')
    result = input(label + (f' [{default}]' if default is not None else '') + ': ').strip()
    if not result and default is None:
        raise LabError('A value is required for ' + label)
    return result or str(default)


def confirm(label):
    return ask(label + ' [y/N]', 'n').lower() in ('y', 'yes')


def absolute(value):
    return str(Path(value).expanduser().resolve())


def invoke(config, *args, privileged=False):
    command = [sys.executable, str(ROOT/'akl.py'), '--config', str(config), *map(str, args)]
    if privileged:
        command.insert(0, 'sudo')
    print('Running: ' + shlex.join(command), flush=True)
    # Inherit stderr and the terminal so sudo prompts work normally; never handle passwords.
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE)
    if result.returncode:
        raise LabError('Step failed; inspect the error above. Re-run quickstart after resolving it.')
    envelope = json.loads(result.stdout)
    if not envelope.get('ok'):
        raise LabError('Command did not report success')
    return envelope['result']


def create_config(args):
    if args.config.exists():
        # Supplying new paths must not quietly edit an established instance.
        overrides = ('workspace', 'mount', 'storage', 'lab_id', 'subnet', *MEDIA)
        if any(getattr(args, key, None) is not None for key in overrides):
            raise LabError('Config already exists; omit new-instance options. Existing configuration will not be overwritten.')
        return Config.load(args.config)
    lab_id = args.lab_id or ask('Lab ID (1-8 lowercase letters/digits/dashes)', 'akl')
    mount = absolute(args.mount or ask('Existing mounted volume for VM storage', '/mnt/lab'))
    workspace = absolute(args.workspace or ask('Private host runtime directory', str(Path.home()/'.misc'/f'{lab_id}-runtime')))
    storage = absolute(args.storage or ask('New storage subdirectory (must not already exist)', str(Path(mount)/('.'+lab_id))))
    subnet = args.subnet or ask('Unused private /24 subnet', '192.168.231.0/24')
    config = Config(example(workspace, storage, mount, lab_id), args.config)
    config.data['subnet'] = subnet
    config.validate()
    if config.storage.exists():
        raise LabError('Storage directory already exists; use a new dedicated subdirectory.')
    if config.workspace.exists() and any(config.workspace.iterdir()):
        raise LabError('Workspace must be new or empty.')
    print('Provide official downloaded media. Links and reference hashes: ' + str(ROOT/'media.lock.json'))
    print('Hashes below pin local bytes; they do not independently authenticate a download.')
    for kind, label in MEDIA.items():
        path = Path(absolute(getattr(args, kind) or ask(label + ' path')))
        if not path.is_file():
            raise LabError('Missing media file: ' + str(path))
        print('Hashing ' + label + ' (large ISOs can take several minutes)...', flush=True)
        digest = sha256(path)
        print('  SHA256: ' + digest)
        config.data['media'][kind] = {'path': str(path), 'sha256': digest}
    config.validate()
    config.workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(config.workspace/'.akl-workspace.json', {'instance_id': config.data['instance_id']})
    write_json(config.path, config.data)
    print('Saved private configuration: ' + str(config.path))
    return config


def prerequisites(args):
    needed = ('sudo', 'virsh', 'virt-install', 'virt-xml-validate', 'qemu-img', 'swtpm', 'genisoimage', 'ssh', 'scp', 'findmnt', 'ip')
    missing = [name for name in needed if not shutil.which(name)]
    missing += [name+' (Python module)' for name in ('libvirt', 'PIL') if importlib.util.find_spec(name) is None]
    if not missing:
        return
    print('Missing host tools: ' + ', '.join(missing))
    if not args.install_deps and not confirm('Install Ubuntu/Debian host packages using apt and sudo?'):
        raise LabError('Run bash tools/install-host.sh, then rerun quickstart.')
    subprocess.run(['bash', str(ROOT/'tools/install-host.sh')], check=True)


def show_console(c, role):
    result = invoke(c.path, 'console', role, privileged=True)
    print(json.dumps(result, indent=2))
    actions = c.workspace/'boot-enter.json'
    write_json(actions, [{'action': 'key', 'keys': 'enter'}, {'action': 'wait', 'seconds': 1}, {'action': 'screenshot'}])
    print('Inspect the saved screenshot. Only if it shows the DVD "press any key" prompt, run:')
    print(shlex.join(['sudo', sys.executable, str(ROOT/'akl.py'), '--config', str(c.path),
                      'console', role, '--actions', str(actions)]))
    print('No viewer is launched. Re-run quickstart when Windows setup/bootstrap completes.')


def ready(c, role):
    command = "[ordered]@{Name=$env:COMPUTERNAME;Ready=(Test-Path C:\\Lab\\bootstrap-ready.txt)} | ConvertTo-Json"
    try:
        result = invoke(c.path, 'guest', role, '--command', command)
        data = json.loads(result['stdout'])
        return data.get('Name', '').lower() == c.name(role) and data.get('Ready') is True
    except (LabError, ValueError, KeyError):
        return False


def next_steps(c):
    prefix = [sys.executable, str(ROOT/'akl.py'), '--config', str(c.path)]
    print('\nNext: complete the clean backup, target debugging/test-signing and symbol steps in:')
    print(str(ROOT/'docs/INSTALL.md') + ' (Configure development and debugging)')
    print('The wizard does not claim kernel-development acceptance from installation alone.')
    print('Common commands:')
    for args, privileged in [(('watch',), True), (('start',), True), (('stop',), True), (('cycle', '--deploy'), False), (('debug',), False)]:
        print('  ' + shlex.join((['sudo'] if privileged else []) + prefix + list(args)))


def finish_tools(c):
    marker = c.state/'quickstart-install.json'
    record = json.loads(marker.read_text()) if marker.exists() else {}
    if record.get('tools_configured'):
        return
    invoke(c.path, 'sync-tools', 'both')
    invoke(c.path, 'guest', 'dev', '--script', ROOT/'guest/Configure-Development.ps1')
    write_json(marker, {'instance_id': c.data['instance_id'], 'tools_configured': True})


def advance(c, args):
    # Each invocation advances at most one Windows setup boot. Markers are never reset.
    if (c.state/'cleanup-in-progress.json').exists() or (c.state/'restore-in-progress.json').exists():
        raise LabError('Interrupted cleanup/recovery requires inspection before setup or startup.')
    prerequisites(args)
    report = invoke(c.path, 'doctor', privileged=True)
    if not report.get('ready'):
        print(json.dumps(report, indent=2))
        raise LabError('Host checks are not ready; correct the reported issues before continuing.')
    if (c.state/'installed.json').exists():
        print('Existing Windows installation detected; starting through the normal guarded lifecycle.')
        print(json.dumps(invoke(c.path, 'start', privileged=True), indent=2))
        if (c.state/'quickstart-install.json').exists():
            finish_tools(c)
        next_steps(c)
        return
    manifest_file = c.state/'manifest.json'
    manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else None
    if manifest is None or manifest.get('phase') == 'provisioning':
        if not args.accept_windows_eula and not confirm('Have you reviewed and accepted the Windows media license for these two VMs?'):
            print('Configuration saved. Provisioning was not started.')
            return
        command = ['provision', '--accept-windows-eula']
        if manifest:
            if not confirm('Resume this recorded incomplete provisioning attempt?'):
                return
            command.append('--resume')
        invoke(c.path, *command, privileged=True)
    elif manifest.get('phase') != 'provisioned':
        raise LabError('Unexpected provisioning phase; inspect the manifest.')
    states = invoke(c.path, 'status', privileged=True)['guests']
    for role in ('target', 'dev'):
        marker = c.state/('install-started-'+role+'.json')
        if not marker.exists():
            write_json(c.state/'quickstart-install.json', {'instance_id': c.data['instance_id'], 'tools_configured': False})
            invoke(c.path, 'install-start', role, privileged=True)
            show_console(c, role)
            return
        if states[role]['state'] != 'running':
            raise LabError(role+' installation was already started but is not running. Inspect state; do not reinstall or reset its start marker.')
        if not ready(c, role):
            print(role + ' is not reporting bootstrap readiness yet.')
            show_console(c, role)
            return
    write_json(c.state/'quickstart-install.json', {'instance_id': c.data['instance_id'], 'tools_configured': False})
    invoke(c.path, 'install-finalize', privileged=True)
    finish_tools(c)
    print('Windows installation finalized and the development tools configured.')
    next_steps(c)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=ROOT/'local/lab.json')
    p.add_argument('--configure-only', action='store_true', help='Write config and media hashes only; no sudo, packages or VM operations')
    p.add_argument('--install-deps', action='store_true', help='Allow apt installation if host tools are missing')
    p.add_argument('--accept-windows-eula', action='store_true')
    for option in ('workspace', 'storage', 'mount', 'lab-id', 'subnet', *MEDIA):
        p.add_argument('--'+option)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if sys.platform != 'linux' or sys.version_info < (3, 10):
            raise LabError('Quickstart requires Linux and Python 3.10 or newer.')
        if os.geteuid() == 0:
            raise LabError('Run quickstart as your ordinary user, without sudo; individual host steps request sudo.')
        args.config = args.config.expanduser().absolute()
        config = create_config(args)
        if args.configure_only:
            print('Configuration ready. Run bash quickstart.sh --config '+shlex.quote(str(config.path))+' to continue.')
        else:
            advance(config, args)
        return 0
    except (LabError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print('Quickstart: '+str(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nStopped. Existing state is preserved; rerun quickstart to continue.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
