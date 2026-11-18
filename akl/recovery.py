"""Cold pair recovery. Checkpoints share disks; full backups copy standalone images."""
from pathlib import Path
import json, re, shutil, uuid, xml.etree.ElementTree as ET
from .core import LabError, root, run, sha256, write_json, timestamp
from .vm import Lab


def label_ok(label):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',label):raise ValueError('Label requires 1-64 letters, digits, dashes or underscores')


def info(disk):
    data=json.loads(run('qemu-img','info','--output=json',disk))
    if data.get('format')!='qcow2' or data.get('backing-filename'):raise LabError('Recovery requires standalone qcow2 images')
    return data


def metadata(c,role):
    lab=Lab(c);xml=lab.virsh('dumpxml',c.name(role),'--inactive');d=ET.fromstring(xml)
    nvram=Path(d.findtext('os/nvram') or '')
    tpm=Path('/var/lib/libvirt/swtpm')/d.findtext('uuid')
    if nvram.parent!=Path('/var/lib/libvirt/qemu/nvram') or nvram.is_symlink() or not nvram.is_file() or tpm.is_symlink() or not tpm.is_dir():raise LabError('Expected initialized NVRAM/TPM state missing')
    return xml,{'disk':str(c.disk(role)),'uuid':d.findtext('uuid'),'nvram':str(nvram),'tpm':str(tpm)}


def inventory(directory):
    result={}
    for p in sorted(directory.rglob('*')):
        if p.is_symlink():raise LabError('Recovery bundles must not contain symlinks')
        if p.is_file() and p.name not in ('integrity.json','COMPLETE'):
            result[str(p.relative_to(directory))]={'bytes':p.stat().st_size,'sha256':sha256(p)}
    return result


def create(c,label,full=False):
    label_ok(label);root();lab=Lab(c);lab.owned();lab.stopped()
    dest=c.storage/('backups' if full else 'checkpoints')/label
    if dest.exists():raise LabError('Recovery label already exists; no overwrite')
    meta={r:metadata(c,r) for r in ('dev','target')}
    needed=20*2**30
    for r,(_,paths) in meta.items():
        data=info(paths['disk'])
        if not full and any(s.get('name')==label for s in data.get('snapshots',[])):raise LabError('Snapshot label already exists')
        if full:needed+=Path(paths['disk']).stat().st_blocks*512
    if shutil.disk_usage(c.storage).free<needed:raise LabError('Insufficient recovery space including 20 GiB growth reserve')
    dest.mkdir(parents=True,mode=0o700)
    write_json(dest/'bundle.json',{'schema_version':1,'instance_id':c.data['instance_id'],'config_sha256':c.fingerprint(),'kind':'backup' if full else 'checkpoint','label':label,'time':timestamp()})
    for r,(xml,paths) in meta.items():
        out=dest/r;out.mkdir()
        (out/'domain.xml').write_text(xml);write_json(out/'paths.json',paths)
        run('cp','--preserve=all',paths['nvram'],out/'nvram.fd');run('cp','-a',paths['tpm'],out/'tpm')
        if full:
            run('qemu-img','convert','-p','-O','qcow2',paths['disk'],out/'disk.qcow2')
            run('qemu-img','check',out/'disk.qcow2')
        else:run('qemu-img','snapshot','-c',label,paths['disk'])
    (dest/'network.xml').write_text(lab.virsh('net-dumpxml',c.network,'--inactive'))
    write_json(dest/'integrity.json',inventory(dest));run('sync','-f',c.storage)
    (dest/'COMPLETE').touch(exist_ok=False);run('sync','-f',c.storage)
    return {'directory':str(dest),'kind':'backup' if full else 'checkpoint','complete':True}


def validate(c,label,full=False):
    label_ok(label);source=c.storage/('backups' if full else 'checkpoints')/label
    if source.is_symlink() or not (source/'COMPLETE').is_file():raise LabError('Bundle missing or incomplete')
    bundle=json.loads((source/'bundle.json').read_text())
    expected={'schema_version':1,'instance_id':c.data['instance_id'],'config_sha256':c.fingerprint(),'kind':'backup' if full else 'checkpoint','label':label}
    if any(bundle.get(k)!=v for k,v in expected.items()):raise LabError('Recovery bundle identity mismatch')
    if inventory(source)!=json.loads((source/'integrity.json').read_text()):raise LabError('Recovery integrity check failed')
    entries={}
    # All roles, XML and image structures are validated before any mutation.
    for r in ('dev','target'):
        item=source/r;_,current=metadata(c,r);saved=json.loads((item/'paths.json').read_text())
        if current!=saved:raise LabError('Saved paths/UUID differ from this instance')
        d=ET.parse(item/'domain.xml').getroot();disks=d.findall("devices/disk[@device='disk']/source")
        if d.findtext('name')!=c.name(r) or d.findtext('uuid')!=saved['uuid'] or d.findtext('metadata/{urn:agent-kernel-lab:1}instance')!=c.data['instance_id']:raise LabError('Saved domain identity mismatch')
        if len(disks)!=1 or disks[0].get('file')!=saved['disk'] or d.findtext('os/nvram')!=saved['nvram']:raise LabError('Saved domain storage mismatch')
        if not (item/'nvram.fd').is_file() or not (item/'tpm').is_dir():raise LabError('Firmware/TPM state missing')
        run('virt-xml-validate',item/'domain.xml','domain')
        if full:
            if info(item/'disk.qcow2')['virtual-size']!=info(saved['disk'])['virtual-size']:raise LabError('Saved image size mismatch')
            run('qemu-img','check',item/'disk.qcow2')
        elif not any(s.get('name')==label for s in info(saved['disk']).get('snapshots',[])):raise LabError('Required internal snapshot is missing')
        entries[r]=(item,saved)
    return entries


def restore(c,label,full=False):
    root();lab=Lab(c);lab.owned();lab.stopped();entries=validate(c,label,full)
    if (c.state/'restore-in-progress.json').exists():raise LabError('Interrupted restore requires inspection; refusing another restore')
    before='before-'+timestamp()+'-'+uuid.uuid4().hex[:6]
    # A full restore replaces images, so its rollback must also be a full backup.
    preserved=create(c,before,full)
    journal=c.state/'restore-in-progress.json'
    if journal.exists():raise LabError('Interrupted restore requires inspection; refusing another restore')
    write_json(journal,{'label':label,'full':full,'rollback':preserved,'phase':'applying'})
    for r,(item,paths) in entries.items():
        if full:
            replacement=Path(paths['disk']+'.restore-'+uuid.uuid4().hex)
            run('qemu-img','convert','-O','qcow2',item/'disk.qcow2',replacement)
            run('qemu-img','check',replacement)
            shutil.chown(replacement,user=c.data['qemu_user'],group=c.data['qemu_group']);replacement.chmod(0o600)
            run('sync','-f',replacement);replacement.replace(paths['disk'])
        else:run('qemu-img','snapshot','-a',label,paths['disk'])
        run('cp','--preserve=all',item/'nvram.fd',paths['nvram'])
        shutil.rmtree(paths['tpm']);run('cp','-a',item/'tpm',paths['tpm'])
        lab.virsh('define',item/'domain.xml')
    run('sync','-f',c.storage);lab.network('isolated');journal.unlink()
    return {'restored':label,'rollback':preserved,'state':'off','network':'isolated'}
