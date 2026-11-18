"""System libvirt lifecycle with ownership checks and boot-time serial isolation."""
from pathlib import Path
import ipaddress, json, os, shutil, socket, time, xml.etree.ElementTree as ET
from .core import LabError, require_storage, root, run, write_json


def network_xml(c, mode='isolated'):
    if mode not in ('isolated','nat'): raise ValueError('Invalid network mode')
    n=ET.Element('network');ET.SubElement(n,'name').text=c.network
    if mode=='nat':ET.SubElement(n,'forward',mode='nat')
    ET.SubElement(n,'bridge',name=c.bridge,stp='on',delay='0')
    ip=ET.SubElement(n,'ip',address=c.ip('host'),netmask='255.255.255.0')
    dhcp=ET.SubElement(ip,'dhcp');prefix=c.ip('host').rsplit('.',1)[0]
    ET.SubElement(dhcp,'range',start=prefix+'.100',end=prefix+'.200')
    for role in ('dev','target'): ET.SubElement(dhcp,'host',mac=c.mac(role),name=c.name(role),ip=c.ip(role))
    return ET.tostring(n,encoding='unicode')


def customize(xml,c,role):
    d=ET.fromstring(xml);d.find('name').text=c.name(role)
    meta=d.find('metadata')
    if meta is None:meta=ET.SubElement(d,'metadata')
    ET.SubElement(meta,'{urn:agent-kernel-lab:1}instance').text=c.data['instance_id']
    cpu=d.find('cpu')
    if cpu is None:cpu=ET.SubElement(d,'cpu',mode='host-passthrough')
    for x in cpu.findall('topology'):cpu.remove(x)
    ET.SubElement(cpu,'topology',sockets='1',cores=str(c.data['vms'][role]['cpus']),threads='1')
    reboot=d.find('on_reboot')
    if reboot is None:reboot=ET.SubElement(d,'on_reboot')
    reboot.text='restart'
    osnode=d.find('os');osnode.set('firmware','efi')
    fw=osnode.find('firmware')
    if fw is None:fw=ET.SubElement(osnode,'firmware')
    for child in list(fw):fw.remove(child)
    ET.SubElement(fw,'feature',enabled='yes',name='secure-boot')
    ET.SubElement(fw,'feature',enabled='yes' if role=='dev' else 'no',name='enrolled-keys')
    for x in osnode.findall('boot'):osnode.remove(x)
    ET.SubElement(osnode,'boot',dev='hd');ET.SubElement(osnode,'boot',dev='cdrom')
    devices=d.find('devices')
    for tag in ('serial','console','channel','redirdev','filesystem'):
        for x in devices.findall(tag):devices.remove(x)
    serial=ET.SubElement(devices,'serial',type='unix')
    source=ET.SubElement(serial,'source',path=c.socket,mode='connect' if role=='dev' else 'bind')
    if role=='dev':ET.SubElement(source,'reconnect',enabled='yes',timeout='2')
    target=ET.SubElement(serial,'target',type='isa-serial',port='0');ET.SubElement(target,'model',name='isa-serial')
    for gfx in devices.findall('graphics'):
        gfx.set('listen','127.0.0.1')
        if gfx.get('type')=='spice':
            ET.SubElement(gfx,'clipboard',copypaste='no');ET.SubElement(gfx,'filetransfer',enable='no')
    return ET.tostring(d,encoding='unicode')


class Lab:
    def __init__(self,c):self.c=c
    def virsh(self,*args):return run('virsh','-c','qemu:///system',*args)
    def domain(self,role):return ET.fromstring(self.virsh('dumpxml',self.c.name(role),'--inactive'))
    def state(self,role):return self.virsh('domstate',self.c.name(role)).strip()
    def owned(self):
        mount_info=require_storage(self.c)
        owner=json.loads((self.c.storage/'.akl-owner.json').read_text())
        if owner.get('instance_id')!=self.c.data['instance_id'] or owner.get('mount_uuid')!=mount_info.get('uuid'):raise LabError('Storage instance or filesystem UUID mismatch')
        manifest=json.loads((self.c.state/'manifest.json').read_text())
        if manifest.get('config_sha256')!=self.c.fingerprint() or manifest.get('mount_uuid')!=mount_info.get('uuid'):raise LabError('Configuration differs from the provisioned manifest; explicit migration is required')
        for role in ('dev','target'):
            d=self.domain(role)
            if d.findtext('metadata/{urn:agent-kernel-lab:1}instance')!=self.c.data['instance_id']:raise LabError('Domain instance identity mismatch')
            if d.findtext('uuid')!=manifest['uuids'][role]:raise LabError('Domain UUID mismatch')
            disks=d.findall("devices/disk[@device='disk']/source")
            if len(disks)!=1 or Path(disks[0].get('file','')).resolve()!=self.c.disk(role):raise LabError('Domain disk path mismatch')
        n=ET.fromstring(self.virsh('net-dumpxml',self.c.network))
        if n.findtext('uuid')!=manifest['network_uuid']:raise LabError('Network UUID mismatch')
    def stopped(self):
        if any(self.state(r)!='shut off' for r in ('dev','target')):raise LabError('Both guests must be fully shut off; no force-stop is performed')
    def qmp(self,role,command,args=None):
        request={'execute':command}
        if args is not None:request['arguments']=args
        result=json.loads(self.virsh('qemu-monitor-command',self.c.name(role),json.dumps(request)))
        if 'error' in result:raise LabError(str(result['error']))
        return result.get('return')
    def status(self):
        result={'instance_id':self.c.data['instance_id'],'guests':{},'network':None}
        domains=self.virsh('list','--all','--name').splitlines()
        for r in ('dev','target'):
            state=self.state(r) if self.c.name(r) in domains else 'undefined'
            result['guests'][r]={'name':self.c.name(r),'state':state,'ip':self.c.ip(r)}
        nets=self.virsh('net-list','--all','--name').splitlines()
        if self.c.network in nets:
            n=ET.fromstring(self.virsh('net-dumpxml',self.c.network));forward=n.find('forward')
            result['network']='isolated' if forward is None else forward.get('mode')
        return result
    def wait_ssh(self,role,timeout=600):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if self.state(role)!='running':raise LabError('Guest stopped or paused while awaiting SSH')
            try:
                with socket.create_connection((self.c.ip(role),22),timeout=3) as s:
                    s.settimeout(3)
                    if s.recv(128).startswith(b'SSH-'):return
            except OSError:pass
            time.sleep(5)
        raise LabError(f'{role} SSH timed out; inspect console and storage before retrying')
    def cable(self,connected):
        root();self.owned()
        if self.state('dev') not in ('running','paused'):raise LabError('Dev must be active')
        d=ET.fromstring(self.virsh('dumpxml',self.c.name('dev')))
        serials=d.findall('devices/serial');source=serials[0].find('source') if len(serials)==1 else None
        alias=serials[0].find('alias') if len(serials)==1 else None
        if source is None or source.get('path')!=self.c.socket or alias is None or alias.get('name')!='serial0':raise LabError('Unexpected serial identity')
        backend={'type':'null','data':{}}
        if connected:
            if self.state('target')!='running':raise LabError('Target must be running before cable connection')
            backend={'type':'socket','data':{'addr':{'type':'unix','data':{'path':self.c.socket}},'server':False,'reconnect':2}}
        self.qmp('dev','chardev-change',{'id':'charserial0','backend':backend})
    def start(self):
        root();self.owned()
        if (self.c.state/'restore-in-progress.json').exists():raise LabError('Interrupted recovery: inspect restore journal before starting')
        if not (self.c.state/'installed.json').exists():raise LabError('Use install-start for new guests; finalize installation first')
        states={r:self.state(r) for r in ('dev','target')}
        if any(s not in ('running','shut off') for s in states.values()):raise LabError('Preexisting paused/unexpected guest state; no automatic resume')
        if all(s=='running' for s in states.values()):return self.status()
        if states['target']=='running' and states['dev']=='shut off':raise LabError('Shut target down normally before cold pair start')
        if self.c.network not in self.virsh('net-list','--name').splitlines():self.virsh('net-start',self.c.network)
        created=False
        if states['dev']=='shut off':
            self.virsh('start',self.c.name('target'),'--paused');created=True
            self.virsh('start',self.c.name('dev'),'--paused');self.cable(False)
            self.virsh('resume',self.c.name('dev'))
        else:self.cable(False)
        self.wait_ssh('dev');self.owned()
        if self.state('dev')!='running':raise LabError('Dev state changed during startup')
        if created:
            if self.state('target')!='paused':raise LabError('New target changed state unexpectedly')
            self.virsh('resume',self.c.name('target'))
        else:self.virsh('start',self.c.name('target'))
        self.wait_ssh('target');self.cable(True)
        return self.status()
    def network(self,mode):
        root();self.owned();self.stopped()
        if mode not in ('isolated','nat'):raise ValueError('Unknown network mode')
        n=ET.fromstring(self.virsh('net-dumpxml',self.c.network,'--inactive'))
        for f in n.findall('forward'):n.remove(f)
        if mode=='nat':ET.SubElement(n,'forward',mode='nat')
        path=self.c.state/'network.xml';path.write_text(ET.tostring(n,encoding='unicode'))
        run('virt-xml-validate',path,'network')
        if self.c.network in self.virsh('net-list','--name').splitlines():self.virsh('net-destroy',self.c.network)
        self.virsh('net-define',path);self.virsh('net-start',self.c.network)
        return {'network':mode}
