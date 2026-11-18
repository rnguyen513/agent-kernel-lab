"""Fresh installation only, with pinned offline SSH and no shared credentials."""
from pathlib import Path
from xml.sax.saxutils import escape
import json, os, secrets, shutil, string, uuid, xml.etree.ElementTree as ET
from .config import ROOT
from .core import LabError, root, run, sha256, write_json, require_storage, private_dir, write_private
from .guest import Guest, render_script
from .vm import Lab, network_xml, customize

MEDIA_NAMES={'windows':'windows.iso','ewdk':'ewdk.iso','openssh':'OpenSSH-Win64.zip'}

def framework_fingerprint():
    import hashlib
    h=hashlib.sha256()
    for folder in ('akl','guest'):
        for p in sorted((ROOT/folder).iterdir()):
            if p.is_file():h.update(str(p.relative_to(ROOT)).encode());h.update(p.read_bytes())
    return h.hexdigest()


def verify_media(c):
    if set(c.data['media'])!=set(MEDIA_NAMES):raise LabError('Configure paths and SHA256 for windows, ewdk and openssh media first')
    result={}
    for kind,item in c.data['media'].items():
        p=Path(item['path'])
        if not p.is_file():raise LabError('Missing media: '+kind)
        digest=sha256(p)
        if digest.lower()!=item['sha256'].lower():raise LabError('Media SHA256 mismatch: '+kind)
        result[kind]={'sha256':digest,'bytes':p.stat().st_size}
    return result


def answer(c,role,password):
    text=(ROOT/'guest'/'Autounattend.xml.in').read_text()
    for key,value in {'NAME':c.name(role),'PASSWORD':password,'IMAGE':c.data['windows_image'],'TIMEZONE':c.data['windows_timezone']}.items():text=text.replace('@@'+key+'@@',escape(value))
    ET.fromstring(text)
    return text


def seeds(c):
    private_dir(c.secrets);c.secrets.chmod(0o700)
    key=c.secrets/'guest_ed25519'
    if not key.exists():run('ssh-keygen','-q','-t','ed25519','-N','','-f',key)
    key.chmod(0o600)
    owner=c.workspace.stat()
    for p in (key,key.with_suffix('.pub')):os.chown(p,owner.st_uid,owner.st_gid)
    credentials_file=c.secrets/'guest-credentials.json'
    credentials=json.loads(credentials_file.read_text()) if credentials_file.exists() else {}
    for role in ('dev','target'):
        if role not in credentials:credentials[role]={'username':'labadmin','password':'Lab!'+''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(28))}
    write_json(credentials_file,credentials)
    seed_manifest=c.secrets/'seed-integrity.json'
    seed_hashes=json.loads(seed_manifest.read_text()) if seed_manifest.exists() else {}
    for role in ('dev','target'):
        stage=c.secrets/role;private_dir(stage)
        (stage/'Autounattend.xml').write_text(answer(c,role,credentials[role]['password']))
        (stage/'lab.pub').write_bytes(key.with_suffix('.pub').read_bytes())
        for p in (ROOT/'guest').glob('*.ps1'):
            text=render_script(c,p.read_text())
            (stage/p.name).write_text(text)
        shutil.copyfile(c.storage/'media'/MEDIA_NAMES['openssh'],stage/'OpenSSH-Win64.zip')
        for p in stage.iterdir():
            p.chmod(0o600);os.chown(p,owner.st_uid,owner.st_gid)
        iso=c.storage/'media'/(role+'-seed.iso')
        if iso.exists():
            if seed_hashes.get(role)!=sha256(iso):raise LabError('Seed ISO is unrecorded or differs; inspect interrupted provisioning before repair')
        else:
            run('genisoimage','-J','-r','-V','AKLSEED','-o',iso,stage)
            seed_hashes[role]=sha256(iso);write_json(seed_manifest,seed_hashes)
        shutil.chown(iso,user=c.data['qemu_user'],group=c.data['qemu_group']);iso.chmod(0o600)


def provision(c,accept_eula=False,resume=False):
    root();mount_info=require_storage(c);lab=Lab(c)
    if not accept_eula:raise LabError('Unattended setup accepts the Windows EULA; supply --accept-windows-eula after reviewing your media license')
    manifest_path=c.state/'manifest.json'
    if resume:
        m=json.loads(manifest_path.read_text())
        if m.get('phase')!='provisioning' or m.get('config_sha256')!=c.fingerprint() or m.get('framework_sha256')!=framework_fingerprint():raise LabError('Resume requires this exact incomplete provisioning attempt')
        owner=json.loads((c.storage/'.akl-owner.json').read_text())
        if owner.get('instance_id')!=c.data['instance_id'] or owner.get('mount_uuid')!=mount_info.get('uuid'):raise LabError('Storage owner/mount mismatch')
    else:
        if c.storage.exists() or manifest_path.exists():raise LabError('Storage/state already exists; no overwrite (use --resume only for a recorded incomplete attempt)')
        if any(n in lab.virsh('list','--all','--name').splitlines() for n in c.names) or c.network in lab.virsh('net-list','--all','--name').splitlines():raise LabError('Libvirt name collision')
        import ipaddress
        subnet=ipaddress.ip_network(c.data['subnet'])
        for route in json.loads(run('ip','-j','route','show','table','all')):
            dst=route.get('dst','default')
            if dst!='default' and ':' not in dst and subnet.overlaps(ipaddress.ip_network(dst,strict=False)):raise LabError('Subnet overlaps a host route: '+dst)
        if shutil.disk_usage(c.mount).free<300*2**30:raise LabError('Provisioning requires at least 300 GiB free')
        verified=verify_media(c)
        c.storage.mkdir(parents=True,mode=0o755);private_dir(c.state)
        write_json(c.storage/'.akl-owner.json',{'instance_id':c.data['instance_id'],'mount_uuid':mount_info.get('uuid')})
        m={'phase':'provisioning','config_sha256':c.fingerprint(),'framework_sha256':framework_fingerprint(),'mount_uuid':mount_info.get('uuid'),'network_uuid':str(uuid.uuid4()),'uuids':{r:str(uuid.uuid4()) for r in ('dev','target')},'media':verified}
        write_json(manifest_path,m)
    (c.storage/'media').mkdir(exist_ok=True);(c.storage/'images').mkdir(exist_ok=True)
    for kind,item in c.data['media'].items():
        dest=c.storage/'media'/MEDIA_NAMES[kind]
        if dest.exists():
            if sha256(dest)!=item['sha256'].lower():raise LabError('Existing staged media differs: '+kind)
        else:
            source=Path(item['path'])
            if sha256(source)!=item['sha256'].lower():raise LabError('Source media changed: '+kind)
            shutil.copyfile(source,dest)
        dest.chmod(0o644)
    seeds(c)
    n=ET.fromstring(network_xml(c));ET.SubElement(n,'uuid').text=m['network_uuid']
    network=c.state/'network.xml';network.write_text(ET.tostring(n,encoding='unicode'))
    nets=lab.virsh('net-list','--all','--name').splitlines()
    if c.network in nets:
        if ET.fromstring(lab.virsh('net-dumpxml',c.network)).findtext('uuid')!=m['network_uuid']:raise LabError('Network identity collision during resume')
    else:lab.virsh('net-define',network)
    if c.network not in lab.virsh('net-list','--name').splitlines():lab.virsh('net-start',c.network)
    existing=lab.virsh('list','--all','--name').splitlines()
    for other in existing:
        d=ET.fromstring(lab.virsh('dumpxml',other,'--inactive'))
        paths={s.get('file') for s in d.findall('devices/disk/source')}
        if other not in c.names and paths & {str(c.disk(r)) for r in ('dev','target')}:raise LabError('A lab disk is referenced by another domain')
    for role in ('target','dev'):
        if c.name(role) in existing:
            d=lab.domain(role)
            if d.findtext('uuid')!=m['uuids'][role] or d.findtext('metadata/{urn:agent-kernel-lab:1}instance')!=c.data['instance_id'] or lab.state(role)!='shut off':raise LabError('Existing guest does not match inactive provisioning journal')
            disk=d.find("devices/disk[@device='disk']/source")
            if disk is None or disk.get('file')!=str(c.disk(role)):raise LabError('Existing disk mismatch')
            continue
        spec=c.data['vms'][role];disk=c.disk(role)
        if disk.exists():
            info=json.loads(run('qemu-img','info','--output=json',disk))
            if disk.stat().st_blocks*512>64*2**20 or info.get('format')!='qcow2' or info.get('virtual-size')!=spec['disk_gib']*2**30 or info.get('backing-filename'):raise LabError('Partial disk is not the expected empty standalone qcow2')
        else:run('qemu-img','create','-f','qcow2',disk,str(spec['disk_gib'])+'G')
        shutil.chown(disk,user=c.data['qemu_user'],group=c.data['qemu_group']);disk.chmod(0o600)
        xml=run('virt-install','--connect','qemu:///system','--name',c.name(role),'--uuid',m['uuids'][role],
                '--memory',spec['memory_mib'],'--vcpus',spec['cpus'],'--cpu','host-passthrough','--machine','q35','--os-variant','win10',
                '--boot','uefi','--tpm','backend.type=emulator,backend.version=2.0,model=tpm-crb',
                '--disk',f'path={disk},format=qcow2,bus=sata,cache=none',
                '--cdrom',c.storage/'media/windows.iso','--disk',f'path={c.storage}/media/{role}-seed.iso,device=cdrom,bus=sata,readonly=on',
                '--network',f'network={c.network},model=e1000e,mac={c.mac(role)}','--graphics','spice,listen=127.0.0.1','--video','vga',
                '--noautoconsole','--print-xml','1','--dry-run')
        path=c.state/(role+'.xml');path.write_text(customize(xml,c,role));run('virt-xml-validate',path,'domain');lab.virsh('define',path)
    m['phase']='provisioned';write_json(manifest_path,m)
    return {'phase':'provisioned','next':'install-start target; inspect console for DVD boot prompt, then install-start dev after target SSH is ready'}


def install_start(c,role):
    root();lab=Lab(c);lab.owned()
    if (c.state/'installed.json').exists():raise LabError('Already installed; use start, never reinstall')
    marker=c.state/('install-started-'+role+'.json')
    if marker.exists() or lab.state(role)!='shut off':raise LabError('Installation already started or guest active; inspect console rather than restarting install')
    if c.disk(role).stat().st_blocks*512>64*2**20:raise LabError('Disk is not empty; refusing unattended wipe')
    if role=='dev' and lab.state('target')!='running':raise LabError('Install target first and leave it running to provide the serial socket')
    if c.network not in lab.virsh('net-list','--name').splitlines():lab.virsh('net-start',c.network)
    write_json(marker,{'started':True})
    lab.virsh('start',c.name(role),'--paused')
    if role=='dev':lab.cable(False)
    lab.virsh('resume',c.name(role))
    return {'role':role,'state':'running','next':'Inspect console; send Enter only if the DVD boot prompt is visible. Wait for bootstrap-ready/SSH.'}


def finalize(c):
    root();lab=Lab(c);lab.owned()
    reports={}
    for role in ('dev','target'):
        code="[ordered]@{Name=$env:COMPUTERNAME;Ready=(Test-Path C:\\Lab\\bootstrap-ready.txt);Setup=(Get-ItemProperty HKLM:\\SYSTEM\\Setup).SystemSetupInProgress;TPM=(Get-Tpm).TpmReady;SecureBoot=(Confirm-SecureBootUEFI)} | ConvertTo-Json"
        result=json.loads(Guest(c,role).command(code)['stdout'])
        if result['Name'].lower()!=c.name(role) or not result['Ready'] or result['Setup'] or not result['TPM'] or result['SecureBoot']!=(role=='dev'):raise LabError('Guest readiness/firmware check failed: '+role)
        reports[role]=result
    for role in ('dev','target'):
        live=ET.fromstring(lab.virsh('dumpxml',c.name(role)));inactive=lab.domain(role)
        osnode=live.find('os')
        if not osnode.findtext('loader') or not osnode.findtext('nvram'):raise LabError('Firmware state not initialized')
        index=list(inactive).index(inactive.find('os'));inactive.remove(inactive.find('os'));inactive.insert(index,osnode)
        for b in osnode.findall('boot'):osnode.remove(b)
        ET.SubElement(osnode,'boot',dev='hd')
        path=c.state/(role+'.xml');path.write_text(ET.tostring(inactive,encoding='unicode'));run('virt-xml-validate',path,'domain');lab.virsh('define',path)
        for drive in ('sdb','sdc'):lab.virsh('change-media',c.name(role),drive,'--eject','--live','--config')
        if role=='dev':lab.virsh('change-media',c.name(role),'sdc',c.storage/'media/ewdk.iso','--insert','--live','--config')
    write_json(c.state/'installed.json',reports)
    return {'phase':'installed','reports':reports,'next':'sync-tools both; Configure-Development; cold clean backup; Configure-Target with test signing; reboot; cache symbols during explicit NAT maintenance'}
