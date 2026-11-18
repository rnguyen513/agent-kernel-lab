"""SSH transport and guest script rendering. Credentials stay in a private workspace."""
from pathlib import Path
import base64, json, os, re, subprocess, tempfile
from .config import ROOT
from .core import LabError, write_json, private_dir, write_private


def render_script(c, text):
    values={'DEV':c.name('dev'),'DEV_UPPER':c.name('dev').upper(),
            'TARGET':c.name('target'),'TARGET_UPPER':c.name('target').upper(),
            'HOST_IP':c.ip('host'),'OPENSSH_SHA256':c.data['media'].get('openssh',{}).get('sha256','UNCONFIGURED').upper()}
    for key,value in values.items():text=text.replace('@@'+key+'@@',value)
    return text


class Guest:
    def __init__(self,c,role):self.c=c;self.role=role;self.name=c.name(role)
    def options(self):
        return ['-F','/dev/null','-o','PubkeyAuthentication=yes','-o','PreferredAuthentications=publickey',
                '-i',str(self.c.secrets/'guest_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
                '-o','ConnectTimeout=30','-o','StrictHostKeyChecking=accept-new',
                '-o','UserKnownHostsFile='+str(self.c.secrets/'known_hosts')]
    def endpoint(self):return 'labadmin@'+self.c.ip(self.role)
    def invoke(self,args,log=None,tty=False):
        if log:
            with Path(log).open('w') as f:p=subprocess.run(args,text=True,stdout=f,stderr=subprocess.STDOUT)
            if p.returncode:raise LabError(f'Guest command failed ({p.returncode}); inspect {log}')
            return {'exit_code':0,'log':str(log)}
        if tty:
            p=subprocess.run(args)
            if p.returncode:raise LabError(f'Guest terminal exited with {p.returncode}')
            return {'exit_code':p.returncode}
        p=subprocess.run(args,text=True,capture_output=True)
        if p.returncode:raise LabError(f'Guest command failed ({p.returncode}): {p.stderr.strip()}')
        return {'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    def command(self,code,log=None,tty=False):
        code="$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "+code
        encoded=base64.b64encode(code.encode('utf-16le')).decode()
        if len(encoded)>6500:raise LabError('Command too long for Windows SSH shell; use a .ps1 file')
        return self.invoke(['ssh',*(['-tt'] if tty else []),*self.options(),self.endpoint(),'powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand '+encoded],log,tty)
    def upload(self,path,destination):
        self._remote(destination)
        return self.invoke(['scp',*self.options(),str(Path(path).resolve()),self.endpoint()+':'+destination])
    def download(self,source,destination,to_role=None):
        self._remote(source)
        if to_role:
            self._remote(destination);destination=Guest(self.c,to_role).endpoint()+':'+destination
        else:
            destination=str(Path(destination).resolve());Path(destination).parent.mkdir(parents=True,exist_ok=True)
        return self.invoke(['scp',*(['-3'] if to_role else []),*self.options(),self.endpoint()+':'+source,destination])
    @staticmethod
    def _remote(path):
        # OpenSSH scp on supported Ubuntu uses a remote shell; reject shell metacharacters.
        if not re.fullmatch(r'[A-Za-z]:/[A-Za-z0-9_./-]+',path) or '..' in Path(path).parts:raise LabError('Remote transfers require a simple absolute Windows path using /, no spaces or shell characters')
    def script(self,path,log=None,tty=False):
        path=Path(path)
        if not re.fullmatch(r'[A-Za-z0-9_.-]+\.ps1',path.name):raise LabError('Use a simple .ps1 filename')
        staging=self.c.workspace/'rendered';private_dir(staging)
        target=staging/path.name;write_private(target,render_script(self.c,path.read_text()))
        remote='C:/Lab/Automation-'+path.name;self.upload(target,remote)
        return self.command("& '"+remote+"'",log,tty)
    def sync_tools(self):
        import zipfile
        bundle=self.c.workspace/'guest-tools.zip'
        with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
            for path in sorted((ROOT/'guest').glob('*.ps1')):z.writestr(path.name,render_script(self.c,path.read_text()))
        if os.geteuid()==0:
            owner=self.c.workspace.stat();os.chown(bundle,owner.st_uid,owner.st_gid)
        self.upload(bundle,'C:/Lab/guest-tools.zip')
        return self.script(ROOT/'guest'/'Sync-LabTools.ps1')
