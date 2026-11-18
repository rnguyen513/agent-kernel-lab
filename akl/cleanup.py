"""Preview-first teardown of one recorded instance. Never remove shared host packages."""
from pathlib import Path
import json
import os
import shutil
import uuid
import xml.etree.ElementTree as ET

from .config import ROOT
from .core import LabError, require_storage, root, run, write_json, observer_lock
from .vm import Lab


ROLES = ('target', 'dev')


def within(path, directory):
    path, directory = Path(path).resolve(), Path(directory).resolve()
    return path == directory or directory in path.parents


def deletion_roots(c):
    protected = {Path('/'), Path('/home'), Path('/root'), Path('/etc'), Path('/usr'),
                 Path('/var'), Path('/tmp'), Path('/media'), Path('/mnt'), Path('/srv'),
                 Path.home().resolve(), c.mount, ROOT.resolve()}
    # When invoked via sudo, also protect the invoking user's actual home directory.
    if os.environ.get('SUDO_UID'):
        import pwd
        protected.add(Path(pwd.getpwuid(int(os.environ['SUDO_UID'])).pw_dir).resolve())
    for path in (c.workspace, c.storage):
        if path in protected or within(ROOT, path) or path.is_symlink():
            raise LabError('Refusing broad, source-containing or symlink deletion root: '+str(path))
        # Resolve every mount, including bind mounts; st_dev/is_mount alone is insufficient.
    mounts = json.loads(run('findmnt', '-J', '-l', '-o', 'TARGET'))['filesystems']
    for item in mounts:
        path = Path(item['target']).resolve()
        if any(within(path, base) for base in (c.workspace, c.storage)):
            raise LabError('Refusing cleanup across a mount inside a deletion root: '+str(path))


def external_symlink(path):
    return Path(path).is_symlink()


def external_paths(c, role, uid, nvram=None):
    uuid.UUID(uid)
    paths = [
        {'kind': 'directory', 'path': '/var/lib/libvirt/swtpm/'+uid},
        {'kind': 'file', 'path': '/var/log/libvirt/qemu/'+c.name(role)+'.log'},
        {'kind': 'file', 'path': '/var/log/swtpm/libvirt/qemu/'+c.name(role)+'-swtpm.log'},
    ]
    if nvram:
        path = Path(nvram)
        if (path.parent != Path('/var/lib/libvirt/qemu/nvram') or
                not any(path.name.startswith(prefix+'_') for prefix in (c.name(role), uid)) or
                external_symlink(path)):
            raise LabError('Unexpected NVRAM path; cleanup requires inspection')
        paths.append({'kind': 'file', 'path': str(path)})
    for item in paths:
        if external_symlink(item['path']):
            raise LabError('Unexpected external state symlink: '+item['path'])
    return paths


def plan(c, check_watchdog=True):
    root()
    if check_watchdog:
        with observer_lock(c, create=False):
            pass
    deletion_roots(c)
    lab = Lab(c)
    manifest_path = c.state/'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    journal_path = c.state/'cleanup-in-progress.json'
    journal = json.loads(journal_path.read_text()) if journal_path.exists() else None
    if journal and (journal.get('instance_id') != c.data['instance_id'] or
                    journal.get('config_sha256') != c.fingerprint()):
        raise LabError('Cleanup journal identity mismatch')
    if manifest:
        if manifest.get('config_sha256') != c.fingerprint():
            raise LabError('Configuration differs from the provisioned manifest')
        mount = require_storage(c)
        if mount.get('uuid') != manifest.get('mount_uuid'):
            raise LabError('Storage filesystem UUID differs from the manifest')
        if c.storage.exists():
            owner = json.loads((c.storage/'.akl-owner.json').read_text())
            if owner.get('instance_id') != c.data['instance_id'] or owner.get('mount_uuid') != mount.get('uuid'):
                raise LabError('Storage ownership mismatch')
        elif not journal:
            raise LabError('Storage is missing; refusing cleanup without a recorded cleanup attempt')
    else:
        owner = json.loads((c.workspace/'.akl-workspace.json').read_text())
        if owner.get('instance_id') != c.data['instance_id'] or c.storage.exists():
            raise LabError('Unprovisioned workspace/storage ownership is not established')
    names = lab.virsh('list', '--all', '--name').splitlines()
    networks = lab.virsh('net-list', '--all', '--name').splitlines()
    domains, external, nvram_paths = {}, [], {}
    for role in ROLES:
        name = c.name(role)
        uid = manifest['uuids'][role] if manifest else None
        nvram = (journal or {}).get('nvram', {}).get(role)
        if name in names:
            d = lab.domain(role)
            if not manifest or d.findtext('uuid') != uid or d.findtext('metadata/{urn:agent-kernel-lab:1}instance') != c.data['instance_id']:
                raise LabError('Domain ownership mismatch: '+name)
            disks = d.findall("devices/disk[@device='disk']/source")
            if len(disks) != 1 or Path(disks[0].get('file', '')).resolve() != c.disk(role):
                raise LabError('Domain disk identity mismatch: '+name)
            actual_nvram = d.findtext('os/nvram')
            if nvram and actual_nvram != nvram:
                raise LabError('NVRAM changed since cleanup began')
            nvram = actual_nvram
            domains[role] = {'name': name, 'uuid': uid, 'state': lab.state(role)}
        if uid:
            external.extend(external_paths(c, role, uid, nvram))
        nvram_paths[role] = nvram
    if c.network in networks:
        n = ET.fromstring(lab.virsh('net-dumpxml', c.network))
        if not manifest or n.findtext('uuid') != manifest['network_uuid']:
            raise LabError('Network ownership mismatch')
    # Check inactive and live XML of every other domain before touching either lab VM.
    # This catches shared networks, firmware, disks, media and debug sockets.
    external_names = {item['path'] for item in external} | {c.socket}
    for other in names:
        if other in c.names:
            continue
        documents = [lab.virsh('dumpxml', other, '--inactive')]
        if lab.virsh('domstate', other) != 'shut off':
            documents.append(lab.virsh('dumpxml', other))
        for xml in documents:
            d = ET.fromstring(xml)
            if d.findtext('uuid') in (manifest or {}).get('uuids', {}).values():
                raise LabError('Another domain uses a recorded UUID: '+other)
            for element in d.iter():
                if element.get('network') == c.network or element.get('bridge') == c.bridge:
                    raise LabError('Another domain uses this network: '+other)
                values = [element.get(k) for k in ('file', 'dir', 'path', 'dev')]
                if element.tag == 'nvram':
                    values.append(element.text)
                for value in filter(None, values):
                    if Path(value).is_absolute() and (value in external_names or any(within(value, base) for base in (c.storage, c.workspace))):
                        raise LabError('Another domain references lab storage/state: '+other)
    if manifest and external_symlink(c.socket):
        raise LabError('Unexpected debug socket symlink')
    if manifest:
        external.append({'kind': 'file', 'path': c.socket})
    mounts = json.loads(run('findmnt', '-J', '-l', '-o', 'TARGET'))['filesystems']
    for mount in mounts:
        if any(within(mount['target'], item['path']) for item in external):
            raise LabError('Refusing cleanup of mounted firmware/TPM/log state')
    retained = [item['path'] for item in c.data['media'].values()
                if not any(within(item['path'], base) for base in (c.storage, c.workspace))]
    return {'instance_id': c.data['instance_id'], 'config_sha256': c.fingerprint(),
            'domains': domains, 'network': c.network if c.network in networks else None,
            'directories': [str(c.storage), str(c.workspace)], 'config_file': str(c.path),
            'external_state': external, 'nvram': nvram_paths,
            'retained_downloads': retained,
            'shared_resources_retained': ['host packages/services', 'repository checkout', 'storage mount itself'],
            'irreversible': 'Includes every checkpoint, backup and evidence file inside this instance.'}


def remove_external(item):
    path = Path(item['path'])
    if path.is_symlink():
        raise LabError('External state changed to a symlink')
    if not path.exists():
        return
    if item['kind'] == 'directory':
        shutil.rmtree(path)
    else:
        path.unlink()


def _execute(c, confirmation, force=False):
    root()
    if confirmation != c.data['instance_id']:
        raise LabError('Deletion requires the exact instance UUID from the preview')
    current = plan(c, check_watchdog=False)  # Revalidate under the lifecycle lock, never apply an old preview.
    active = [item for item in current['domains'].values() if item['state'] != 'shut off']
    if active and not force:
        raise LabError('Guests are active. Shut them down normally first, or explicitly use --force to discard running state.')
    write_json(c.state/'cleanup-in-progress.json', current)
    lab = Lab(c)
    for item in active:
        lab.virsh('destroy', item['uuid'])
    # Recheck the complete selected pair before undefining either guest.
    for role in current['domains']:
        if lab.state(role) != 'shut off':
            raise LabError('Guest did not stop; cleanup journal retained')
    for item in current['domains'].values():
        # Explicit --keep-nvram prevents libvirt following an unreviewed storage path.
        lab.virsh('undefine', item['uuid'], '--managed-save', '--snapshots-metadata',
                  '--checkpoints-metadata', '--keep-nvram')
    if current['network']:
        if c.network in lab.virsh('net-list', '--name').splitlines():
            lab.virsh('net-destroy', c.network)
        lab.virsh('net-undefine', c.network)
    # Detect nested mounts that appeared since the initial preflight.
    deletion_roots(c)
    if c.storage.exists():
        require_storage(c)
    for item in current['external_state']:
        remove_external(item)
    if c.storage.exists():
        shutil.rmtree(c.storage)
    # Config is removed only after owned hypervisor/storage resources were removed.
    c.path.unlink(missing_ok=True)
    shutil.rmtree(c.workspace)
    return {'removed_instance': c.data['instance_id'],
            'retained_downloads': current['retained_downloads'],
            'shared_resources_retained': current['shared_resources_retained']}


def execute(c, confirmation, force=False):
    root()
    if confirmation != c.data['instance_id']:
        raise LabError('Deletion requires the exact instance UUID from the preview')
    plan(c)  # Read-only preflight before creating any cleanup state/locks.
    with observer_lock(c):
        return _execute(c, confirmation, force)
