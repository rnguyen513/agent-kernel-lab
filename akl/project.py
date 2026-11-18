"""Reproducible source capture and the reference Echo-compatible driver workflow."""
from pathlib import Path
import json, re, uuid, zipfile
from .config import ROOT
from .core import LabError, sha256, timestamp, write_json
from .guest import Guest

EXCLUDE={'.git','.vs','__pycache__','Debug','Release','x64','x86','node_modules'}
SOURCE_EXT={'.c','.h','.cpp','.hpp','.inf','.inx','.rc','.vcxproj','.filters','.props','.targets','.sln','.md','.txt'}


def source_files(source):
    source=Path(source).resolve()
    for required in ('driver/AutoSync/echo.vcxproj','exe/echoapp.vcxproj'):
        if not (source/required).is_file():raise LabError('Echo-compatible project missing '+required)
    files=[]
    for p in sorted(source.rglob('*')):
        relative=p.relative_to(source)
        if any(part in EXCLUDE for part in relative.parts):continue
        if p.is_symlink():raise LabError('Source trees cannot contain symlinks')
        if p.is_file():
            if p.suffix.lower() not in SOURCE_EXT and p.name not in ('LICENSE','makefile','sources'):raise LabError('Unexpected source file; remove credentials/artifacts before upload: '+str(relative))
            files.append(p)
    if sum(p.stat().st_size for p in files)>64*2**20:raise LabError('Source bundle exceeds 64 MiB')
    return source,files


def archive(source,destination):
    source,files=source_files(source);hashes={}
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:
            rel=str(p.relative_to(source));data=p.read_bytes()
            item=zipfile.ZipInfo('kmdf/'+rel,(1980,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16
            z.writestr(item,data);hashes[rel]=sha256(p)
    return hashes


def cycle(c,source=None,deploy=False):
    source=Path(source) if source else ROOT/'examples/observable-echo/kmdf'
    run_id=timestamp()+'-'+uuid.uuid4().hex[:8]
    out=c.workspace/'runs'/run_id;out.mkdir(parents=True,mode=0o700)
    report={'schema_version':1,'run_id':run_id,'profile':'echo-compatible','status':'incomplete','deployed':False,'runtime_observed':False}
    write_json(out/'result.json',report)
    try:
        bundle=out/'source.zip';write_json(out/'source-sha256.json',archive(source,bundle))
        dev=Guest(c,'dev');target=Guest(c,'target')
        dev.upload(bundle,'C:/Lab/kmdf-echo-source.zip')
        for script in ('Build-Sample.ps1','Sign-Sample.ps1'):
            dev.script(ROOT/'guest'/script,log=out/(script+'.log'))
        for remote,local in [('SignedEcho.zip','SignedEcho.zip'),('Build/driver/echo.pdb','echo.pdb'),('sample-build-hashes.json','build-hashes.json'),('signed-package-hashes.json','package-hashes.json')]:
            dev.download('C:/Lab/'+remote,out/local)
        report['artifact_sha256']={p.name:sha256(p) for p in (out/'SignedEcho.zip',out/'echo.pdb',out/'source.zip')}
        if deploy:
            target.upload(out/'SignedEcho.zip','C:/Lab/SignedEcho.zip')
            target.script(ROOT/'guest/Install-Sample.ps1',log=out/'deploy.log')
            target.script(ROOT/'guest/Test-ObservableDriver.ps1',log=out/'probe.log')
            report['deployed']=True;report['functional_tests']='passed'
        report['status']='passed'
    except Exception:
        report['status']='failed';raise
    finally:write_json(out/'result.json',report)
    return {'evidence':str(out),**report,'next':'Capture live KD breakpoints and matching PDB/build identity; build/test success alone is not debugger evidence.'}
