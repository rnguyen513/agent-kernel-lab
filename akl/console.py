"""Bounded headless console access. No viewer, listening service or reset primitive."""
import io, re, time, uuid
from .core import LabError, root, timestamp
from .vm import Lab


def validate(actions):
    if not isinstance(actions,list) or not 1<=len(actions)<=25:raise ValueError('Use 1-25 console actions')
    for action in actions:
        if not isinstance(action,dict):raise ValueError('Console action must be an object')
        kind=action.get('action')
        if kind not in ('screenshot','inspect','key','wait'):raise ValueError('Supported console actions: screenshot, inspect, key, wait')
        if kind=='wait' and (not isinstance(action.get('seconds'),(int,float)) or not 0<=action['seconds']<=5):raise ValueError('Wait must be 0-5 seconds')
        if kind=='key' and not re.fullmatch(r'[a-z0-9_]+(?:-[a-z0-9_]+){0,3}',action.get('keys','')):raise ValueError('Invalid qcode key chord')
    if sum(a.get('seconds',0) for a in actions if a['action']=='wait')>15:raise ValueError('Total console wait exceeds 15 seconds')


def execute(c,role,actions):
    validate(actions);root();lab=Lab(c);lab.owned()
    if lab.state(role)!='running':raise LabError('Console input requires a running VM; inspect pauses before resuming')
    results=[]
    for a in actions:
        kind=a['action']
        if kind=='screenshot':
            import libvirt
            from PIL import Image
            conn=libvirt.open('qemu:///system')
            try:
                dom=conn.lookupByName(c.name(role));stream=conn.newStream(0);mime=dom.screenshot(stream,0,0);chunks=[]
                stream.recvAll(lambda stream,data,opaque:chunks.append(data),None);stream.finish()
                im=Image.open(io.BytesIO(b''.join(chunks)))
                dest=c.workspace/'console';dest.mkdir(parents=True,exist_ok=True)
                path=dest/(role+'-'+timestamp()+'-'+uuid.uuid4().hex[:6]+'.png');im.save(path)
                results.append({'action':kind,'file':str(path),'width':im.width,'height':im.height,'mime':mime})
            finally:conn.close()
        elif kind=='inspect':results.append({'action':kind,'status':lab.qmp(role,'query-status')})
        elif kind=='wait':time.sleep(a['seconds']);results.append({'action':kind,'ok':True})
        elif kind=='key':
            codes=[{'enter':'ret','escape':'esc','control':'ctrl','win':'meta_l'}.get(k,k) for k in a['keys'].split('-')]
            try:
                lab.qmp(role,'input-send-event',{'events':[{'type':'key','data':{'down':True,'key':{'type':'qcode','data':k}}} for k in codes]});time.sleep(.12)
            finally:lab.qmp(role,'input-send-event',{'events':[{'type':'key','data':{'down':False,'key':{'type':'qcode','data':k}}} for k in reversed(codes)]})
            results.append({'action':kind,'ok':True})
    return results
