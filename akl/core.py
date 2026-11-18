"""Filesystem and subprocess primitives; all host commands use argv, never a shell."""
from pathlib import Path
import contextlib, fcntl, hashlib, json, os, subprocess, time, uuid

class LabError(RuntimeError): pass

def run(*args, check=True):
    p=subprocess.run([str(a) for a in args],text=True,capture_output=True)
    if check and p.returncode: raise LabError(f'{args[0]} failed ({p.returncode}): {p.stderr.strip()}')
    return p.stdout.strip()

def root():
    if os.geteuid()!=0: raise LabError('This host operation requires scoped sudo; do not run your agent as root.')

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def private_dir(path):
    path=Path(path)
    if path.is_symlink():raise LabError('Private runtime directories cannot be symlinks')
    if not path.exists():
        private_dir(path.parent)
        path.mkdir(mode=0o700)
        if os.geteuid()==0:
            parent=path.parent.stat();os.chown(path,parent.st_uid,parent.st_gid)
    return path


def write_private(path, data, mode=0o600):
    path=Path(path);private_dir(path.parent)
    temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    try:
        if os.geteuid()==0:
            parent=path.parent.stat();os.fchown(fd,parent.st_uid,parent.st_gid)
        with os.fdopen(fd,'wb') as f:
            f.write(data.encode() if isinstance(data,str) else data);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if temp.exists():temp.unlink()


def write_json(path, data, mode=0o600):
    write_private(path,json.dumps(data,indent=2)+'\n',mode)

def timestamp(): return time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())

def require_storage(c):
    info=json.loads(run('findmnt','-J','-o','TARGET,SOURCE,FSTYPE,OPTIONS,UUID','-T',c.storage if c.storage.exists() else c.mount))['filesystems'][0]
    if Path(info['target']).resolve()!=c.mount or 'rw' not in info['options'].split(','):
        raise LabError('Configured storage mount is absent or not writable; inspect actual host mount (sandbox views can differ).')
    if not c.mount.is_mount(): raise LabError('Configured mount is not a mount point')
    return info

@contextlib.contextmanager
def lock(c):
    c.workspace.mkdir(parents=True,exist_ok=True)
    path=c.workspace/'operation.lock'
    fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    if os.geteuid()==0:
        owner=c.workspace.stat();os.fchown(fd,owner.st_uid,owner.st_gid)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise LabError('Another lifecycle operation is active for this workspace')
        yield
    finally:os.close(fd)

def event(c, action, result):
    private_dir(c.state)
    fd=os.open(c.state/'events.jsonl',os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
    if os.geteuid()==0:
        owner=c.workspace.stat();os.fchown(fd,owner.st_uid,owner.st_gid)
    with os.fdopen(fd,'a') as f:
        f.write(json.dumps({'time':timestamp(),'action':action,'result':result})+'\n')
