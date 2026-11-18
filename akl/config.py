"""Validated, portable configuration. No machine identities or credentials in source."""
from dataclasses import dataclass
from pathlib import Path
import hashlib, ipaddress, json, re, uuid

ROOT = Path(__file__).resolve().parents[1]

@dataclass
class Config:
    data: dict
    path: Path

    @classmethod
    def load(cls, path):
        path = Path(path).expanduser().resolve()
        value = cls(json.loads(path.read_text()), path)
        value.validate()
        return value

    def validate(self):
        d = self.data
        if d.get('schema_version') != 1: raise ValueError('Unsupported config schema_version')
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,7}', d.get('lab_id', '')): raise ValueError('lab_id: 1-8 lowercase letters/digits/dashes, starting with a letter')
        uuid.UUID(d['instance_id'])
        for key in ('workspace', 'storage', 'mount'):
            p = Path(d[key])
            if not p.is_absolute() or any(c in str(p) for c in ',\n\r'): raise ValueError(f'{key}: use an absolute path without commas/newlines')
            d[key] = str(p.resolve())
        if self.storage == self.mount or self.mount not in self.storage.parents: raise ValueError('storage must be a dedicated subdirectory of mount')
        if self.storage == self.workspace or self.storage in self.workspace.parents or self.workspace in self.storage.parents: raise ValueError('workspace and storage must not contain one another')
        net = ipaddress.ip_network(d['subnet'])
        if net.version != 4 or net.prefixlen != 24 or not any(net.subnet_of(ipaddress.ip_network(n)) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')): raise ValueError('Use a private IPv4 /24 subnet')
        for role in ('dev', 'target'):
            spec = d['vms'][role]
            if any(type(spec.get(k)) is not int for k in ('cpus','memory_mib','disk_gib')):raise ValueError('VM resources must be integers')
            if not 1 <= spec['cpus'] <= 64 or not 4096 <= spec['memory_mib'] <= 262144 or not 64 <= spec['disk_gib'] <= 4096: raise ValueError('Invalid VM resources')
        for key in ('qemu_user', 'qemu_group'):
            if not re.fullmatch(r'[a-z_][a-z0-9_-]*', d[key]): raise ValueError('Invalid QEMU account name')
        for kind, media in d['media'].items():
            if kind not in ('windows', 'ewdk', 'openssh'): raise ValueError('Unknown media kind')
            p = Path(media['path'])
            if not p.is_absolute() or any(c in str(p) for c in ',\n\r'): raise ValueError('Media paths must be absolute without commas/newlines')
            if not re.fullmatch(r'[0-9a-fA-F]{64}', media['sha256']): raise ValueError('Each media item requires its SHA256')
        if d.get('windows_image')!='Windows 11 Pro': raise ValueError('This release supports the Windows 11 Pro en-US image only')
        if not isinstance(d.get('windows_timezone'),str) or not d['windows_timezone']:raise ValueError('windows_timezone required')

    @property
    def workspace(self): return Path(self.data['workspace'])
    @property
    def storage(self): return Path(self.data['storage'])
    @property
    def mount(self): return Path(self.data['mount'])
    @property
    def state(self): return self.workspace/'state'
    @property
    def secrets(self): return self.workspace/'secrets'
    @property
    def lab_id(self): return self.data['lab_id']
    @property
    def network(self): return self.lab_id+'-isolated'
    @property
    def bridge(self): return 'virbr-'+self.lab_id
    @property
    def socket(self): return '/var/lib/libvirt/qemu/'+self.lab_id+'-com1.sock'
    @property
    def names(self): return [self.name(r) for r in ('target','dev')]
    def name(self, role):
        if role not in ('dev','target'): raise ValueError('Expected dev or target')
        return self.lab_id+'-'+role
    def ip(self, role):
        offset={'host':1,'dev':165,'target':178}[role]
        return str(ipaddress.ip_network(self.data['subnet']).network_address+offset)
    def mac(self, role):
        digest=hashlib.sha256((self.data['instance_id']+role).encode()).digest()
        return '52:54:00:'+':'.join(f'{x:02x}' for x in digest[:3])
    def disk(self, role): return self.storage/'images'/(self.name(role)+'.qcow2')
    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.data,sort_keys=True).encode()).hexdigest()


def example(workspace='/srv/agent-kernel-lab/workspace', storage='/mnt/lab/agent-kernel-lab', mount='/mnt/lab', lab_id='akl'):
    return {'schema_version':1,'instance_id':str(uuid.uuid4()),'lab_id':lab_id,
            'workspace':workspace,'storage':storage,'mount':mount,'subnet':'192.168.231.0/24',
            'qemu_user':'libvirt-qemu','qemu_group':'kvm','windows_image':'Windows 11 Pro',
            'windows_timezone':'UTC','vms':{'dev':{'cpus':8,'memory_mib':16384,'disk_gib':150},'target':{'cpus':4,'memory_mib':8192,'disk_gib':80}},
            'media':{}}
