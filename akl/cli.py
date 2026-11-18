"""Stable JSON CLI for agent orchestration; interactive KD is explicit."""
from pathlib import Path
import argparse, contextlib, json, os, sys
from . import __version__
from .config import Config, ROOT, example
from .core import LabError, event, lock, write_json
from .guest import Guest
from .vm import Lab


def parser():
    p=argparse.ArgumentParser(description='Agent Kernel Lab: headless Windows kernel development on Linux/KVM')
    p.add_argument('--version',action='version',version=__version__)
    p.add_argument('--config',type=Path,default=ROOT/'local/lab.json')
    commands=p.add_subparsers(dest='action',required=True)
    q=commands.add_parser('init');q.add_argument('--workspace',required=True);q.add_argument('--storage',required=True);q.add_argument('--mount',required=True);q.add_argument('--lab-id',default='akl');q.add_argument('--subnet',default='192.168.231.0/24')
    for action in ('doctor','media-verify','status','start','stop','install-finalize','watch'):commands.add_parser(action)
    q=commands.add_parser('provision');q.add_argument('--accept-windows-eula',action='store_true');q.add_argument('--resume',action='store_true')
    q=commands.add_parser('install-start');q.add_argument('role',choices=('dev','target'))
    q=commands.add_parser('network');q.add_argument('mode',choices=('isolated','nat'))
    q=commands.add_parser('debug-link');q.add_argument('mode',choices=('connect','disconnect'))
    for action in ('checkpoint','backup'):
        q=commands.add_parser(action);q.add_argument('operation',choices=('create','validate','restore'));q.add_argument('label')
    q=commands.add_parser('console');q.add_argument('role',choices=('dev','target'));q.add_argument('--actions',type=Path)
    q=commands.add_parser('sync-tools');q.add_argument('role',choices=('dev','target','both'))
    q=commands.add_parser('guest');q.add_argument('role',choices=('dev','target'));q.add_argument('--tty',action='store_true');q.add_argument('--log',type=Path)
    group=q.add_mutually_exclusive_group(required=True)
    group.add_argument('--command');group.add_argument('--script',type=Path);group.add_argument('--upload',type=Path);group.add_argument('--download')
    q.add_argument('--destination');q.add_argument('--to-role',choices=('dev','target'))
    commands.add_parser('debug')
    q=commands.add_parser('cycle');q.add_argument('--source',type=Path);q.add_argument('--deploy',action='store_true')
    q=commands.add_parser('handoff');q.add_argument('--note',default='')
    return p


def dispatch(a,c):
    from . import windows, recovery, operations, console, project
    lab=Lab(c)
    if a.action=='doctor':return operations.doctor(c)
    if a.action=='media-verify':return windows.verify_media(c)
    if a.action=='status':return lab.status()
    if a.action=='provision':return windows.provision(c,a.accept_windows_eula,a.resume)
    if a.action=='install-start':return windows.install_start(c,a.role)
    if a.action=='install-finalize':return windows.finalize(c)
    if a.action=='start':return lab.start()
    if a.action=='stop':return operations.stop(c)
    if a.action=='network':return lab.network(a.mode)
    if a.action=='debug-link':lab.cable(a.mode=='connect');return {'cable':a.mode}
    if a.action in ('checkpoint','backup'):
        if a.operation=='validate':
            from .core import root
            root();lab.owned();lab.stopped();recovery.validate(c,a.label,a.action=='backup');return {'valid':True,'label':a.label}
        return getattr(recovery,a.operation)(c,a.label,a.action=='backup')
    if a.action=='console':return console.execute(c,a.role,json.loads(a.actions.read_text()) if a.actions else [{'action':'screenshot'}])
    if a.action=='sync-tools':return {r:Guest(c,r).sync_tools() for r in (('dev','target') if a.role=='both' else (a.role,))}
    if a.action=='guest':
        guest=Guest(c,a.role)
        if a.to_role and not a.download:raise ValueError('--to-role requires --download')
        if (a.upload or a.download) and not a.destination:raise ValueError('Transfers require --destination')
        if a.script:return guest.script(a.script,a.log,a.tty)
        if a.command:return guest.command(a.command,a.log,a.tty)
        if a.upload:return guest.upload(a.upload,a.destination)
        if a.download:return guest.download(a.download,a.destination,a.to_role)
    if a.action=='debug':return Guest(c,'dev').script(ROOT/'guest/Start-KernelDebugger.ps1',tty=True)
    if a.action=='cycle':return project.cycle(c,a.source,a.deploy)
    if a.action=='watch':return operations.watch(c)
    if a.action=='handoff':return operations.handoff(c,a.note)
    raise ValueError('Unsupported command')


def main(argv=None):
    a=parser().parse_args(argv);c=None
    try:
        if a.action=='init':
            if a.config.exists():raise LabError('Config already exists; no overwrite')
            d=example(a.workspace,a.storage,a.mount,a.lab_id);d['subnet']=a.subnet
            c=Config(d,a.config.resolve());c.validate()
            c.workspace.mkdir(parents=True,exist_ok=True,mode=0o700)
            if any(c.workspace.iterdir()):raise LabError('Use a new empty workspace')
            write_json(c.workspace/'.akl-workspace.json',{'instance_id':d['instance_id']})
            write_json(a.config,d);result={'config':str(a.config.resolve()),'next':'Configure all three media paths and SHA256; run doctor and media-verify.'}
        else:
            c=Config.load(a.config)
            # Dedicated locks serialize lifecycle and build/deploy; KD and stimulus may run concurrently.
            serialized={'provision','install-start','install-finalize','start','stop','network','debug-link','checkpoint','backup','cycle','sync-tools'}
            with lock(c) if a.action in serialized else contextlib.nullcontext():
                result=dispatch(a,c)
            if a.action not in ('guest','debug','watch','status','doctor','media-verify','console'):
                event(c,a.action,{'ok':True})
        print(json.dumps({'ok':True,'action':a.action,'result':result},indent=2))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({'ok':False,'error':'Interrupted; inspect actual guest/job state before retrying.'}),file=sys.stderr);return 130
    except (LabError,OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'ok':False,'action':a.action,'error':str(exc)}),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
