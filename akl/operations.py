"""Diagnostics, bounded shutdown, storage watchdog and agent handoff."""
from pathlib import Path
import json, os, re, shutil, time
from .core import LabError, require_storage, root, run, timestamp, write_json, private_dir
from .guest import Guest
from .vm import Lab

TOOLS=('virsh','virt-install','virt-xml-validate','qemu-img','swtpm','genisoimage','ssh','scp','findmnt','ip','cp','sync')


def doctor(c):
    checks={'tools':{name:shutil.which(name) for name in TOOLS},'kvm_exists':Path('/dev/kvm').exists(),'kvm_access':os.access('/dev/kvm',os.R_OK|os.W_OK),'python':run('python3','--version')}
    try:
        checks['mount']=require_storage(c);checks['free_gib']=round(shutil.disk_usage(c.mount).free/2**30,1)
    except (LabError,OSError,ValueError,KeyError) as exc:checks['storage_error']=str(exc)
    for name in ('libvirt','PIL'):
        try:__import__(name);checks[name]=True
        except ImportError:checks[name]=False
    checks['ready']=all(checks['tools'].values()) and checks['kvm_access'] and 'storage_error' not in checks and checks['libvirt'] and checks['PIL']
    return checks


def stop(c,timeout=600):
    root();lab=Lab(c);lab.owned()
    states={r:lab.state(r) for r in ('dev','target')}
    if any(s not in ('running','shut off') for s in states.values()):raise LabError('Paused/unexpected guest state; inspect storage or debugger before shutdown')
    # SSH may be frozen in a debugger. Never force power off on a timeout.
    for role in ('target','dev'):
        if states[role]=='running':Guest(c,role).command('shutdown.exe /s /t 5')
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if all(lab.state(r)=='shut off' for r in states):return lab.status()
        time.sleep(5)
    raise LabError('Graceful shutdown timed out; inspect KD/storage/console. No reset or destroy was issued.')


def watch(c,interval=5):
    root();lab=Lab(c);lab.owned()
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    # journal cursor avoids reinterpreting historical failures as a new incident.
    cursor_text=run('journalctl','-k','-b','-n','0','--show-cursor','--no-pager')
    match=re.search(r'-- cursor: (.+)',cursor_text)
    if not match:raise LabError('Cannot establish kernel journal cursor')
    cursor=match.group(1)
    pattern=re.compile(r'I/O error|Buffer I/O|EXT4-fs error|XFS.*(?:error|corrupt)|USB disconnect|host controller not responding|HC died|reset (?:SuperSpeed|high-speed) USB',re.I)
    while True:
        fault=None
        try:require_storage(c)
        except (LabError,OSError,ValueError,KeyError) as exc:fault=str(exc)
        lines=run('journalctl','-k','-b','--after-cursor',cursor,'--show-cursor','--no-pager')
        match=re.search(r'-- cursor: (.+)',lines)
        if match:cursor=match.group(1)
        hits=[line for line in lines.splitlines() if pattern.search(line)]
        if hits:fault='New host storage/controller event; conservative pause for operator inspection'
        result={'time':timestamp(),'boot_id':boot_id,'fault':fault,'events':hits[-10:]}
        if fault:
            # Storage may be gone: verify VM metadata + UUID directly, without accessing disks.
            m=json.loads((c.state/'manifest.json').read_text())
            for role in ('dev','target'):
                d=lab.domain(role)
                if d.findtext('uuid')!=m['uuids'][role] or d.findtext('metadata/{urn:agent-kernel-lab:1}instance')!=c.data['instance_id']:raise LabError('Watchdog identity mismatch')
            result['paused']=[]
            for role in ('dev','target'):
                if lab.state(role)=='running':lab.virsh('suspend',c.name(role));result['paused'].append(role)
            write_json(c.state/'watchdog.json',result)
            raise LabError('Watchdog paused owned guests; inspect '+str(c.state/'watchdog.json')+'. No automatic resume.')
        write_json(c.state/'watchdog.json',result)
        time.sleep(interval)


def handoff(c,note=''):
    result={'schema_version':1,'generated_at':timestamp(),'config':str(c.path),'instance_id':c.data['instance_id'],'observed':Lab(c).status(),
            'note':note,'verification':'Status observes power/network only; inspect dated run evidence before claiming driver acceptance.',
            'next_agent':['Read AGENTS.md and docs/WORKFLOW.md.','Do not provision an existing instance.','Inspect storage, restore journal and watchdog before starting.','Inspect run result.json, transcripts and artifact hashes.','Never infer runtime/debugger success from a successful build.','Resume and detach KD before stopping; leave an explicit handoff.']}
    for name in ('watchdog.json','restore-in-progress.json'):
        path=c.state/name
        if path.exists():result[name]=json.loads(path.read_text())
    runs=c.workspace/'runs'
    result['recent_runs']=[str(p) for p in sorted(runs.glob('*/result.json'))[-10:]] if runs.exists() else []
    write_json(c.state/'handoff.json',result)
    return {'file':str(c.state/'handoff.json'),**result}
