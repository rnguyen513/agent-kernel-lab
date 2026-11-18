#!/usr/bin/env python3
"""Create a deterministic source-only archive from a strict publication allowlist."""
from pathlib import Path
import argparse, gzip, hashlib, io, json, re, sys, tarfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from akl import __version__
TOP={'akl.py','README.md','AGENTS.md','LICENSE','THIRD_PARTY_NOTICES.md','SECURITY.md','CONTRIBUTING.md','CHANGELOG.md','.gitignore','media.lock.json'}
DIRS={'akl','guest','examples','docs','tests','tools','.github'}
EXT={'.py','.ps1','.sh','.json','.md','.txt','.yml','.yaml','.xml','.in','.c','.h','.cpp','.hpp','.inf','.inx','.rc','.vcxproj','.filters','.props','.targets','.sln'}
SKIP={'__pycache__','.pytest_cache'}


def files(root=ROOT):
    result={}
    for p in sorted(root.iterdir()):
        if p.name not in TOP|DIRS:continue
        if p.is_symlink():raise ValueError('Publication paths cannot be symlinks: '+p.name)
        candidates=sorted(p.rglob('*')) if p.is_dir() else [p]
        for file in candidates:
            rel=file.relative_to(root)
            if any(x in SKIP for x in rel.parts):continue
            if file.is_symlink():raise ValueError('Publication symlink: '+str(rel))
            if file.is_dir():continue
            if file.suffix.lower() not in EXT and file.name not in ('LICENSE','.gitignore'):raise ValueError('Unexpected publication file: '+str(rel))
            data=file.read_bytes()
            if len(data)>2*2**20:raise ValueError('Oversized publication input: '+str(rel))
            # Upstream INF templates use UTF-16LE with BOM; preserve exact source bytes.
            text=data.decode('utf-16') if data.startswith((b'\xff\xfe',b'\xfe\xff')) else data.decode('utf-8-sig')
            if '\x00' in text:raise ValueError('Binary publication input: '+str(rel))
            if re.search(r'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----',text):raise ValueError('Private key detected: '+str(rel))
            if re.search(r'(?:[?&](?:P1|P2|P3|P4|sig|token)=)',text):raise ValueError('Signed/token-bearing URL detected: '+str(rel))
            result[str(rel)]=data
    missing=TOP-set(result)
    if missing:raise ValueError('Required release files missing: '+', '.join(sorted(missing)))
    return result


def build(destination,root=ROOT):
    contents=files(root)
    manifest={name:hashlib.sha256(data).hexdigest() for name,data in contents.items()}
    contents['MANIFEST.sha256']=''.join(f'{digest}  {name}\n' for name,digest in sorted(manifest.items())).encode()
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    prefix='agent-kernel-lab-'+__version__
    with destination.open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as zipped:
            with tarfile.open(fileobj=zipped,mode='w',format=tarfile.PAX_FORMAT) as archive:
                for name,data in sorted(contents.items()):
                    info=tarfile.TarInfo(prefix+'/'+name);info.size=len(data);info.mode=0o644;info.mtime=0;info.uid=0;info.gid=0
                    archive.addfile(info,io.BytesIO(data))
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_name(destination.name+'.sha256').write_text(digest+'  '+destination.name+'\n')
    return {'archive':str(destination),'sha256':digest,'files':len(contents),'bytes':destination.stat().st_size}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'dist'/('agent-kernel-lab-'+__version__+'.tar.gz'))
    print(json.dumps(build(p.parse_args().output),indent=2))
