"""Owned finite AP-switch profile for peer12; only ax/sr2/end commands."""
import argparse,json,os,subprocess,time
from pathlib import Path

def run(args):
    q=subprocess.run(args,capture_output=True,text=True,timeout=30)
    if q.returncode:raise RuntimeError(q.stderr)
    return q.stdout.strip()
def state(dev):
    return {'wall':time.time(),'addresses':json.loads(run(['ip','-j','addr','show','dev',dev])),'link':run(['iw','dev',dev,'link'])}
def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['begin','guard']);p.add_argument('--folder',required=True);p.add_argument('--dev',default='wlo1');a=p.parse_args();folder=Path(a.folder).resolve()
    if os.geteuid()!=0 or 'ROSPacer' not in folder.parts or 'runs' not in folder.parts or a.dev!='wlo1':raise ValueError('root, owned path and peer12 interface required')
    if a.mode=='begin':
        folder.mkdir(parents=True,exist_ok=True)
        owner=int(os.environ.get('SUDO_UID',0));group=int(os.environ.get('SUDO_GID',0))
        if owner and folder.parent.parent.name=='runs' and folder.parent.name.startswith('w1_'):
            os.chown(folder.parent,owner,group);os.chown(folder,owner,group)
        if (folder/'baseline.json').exists():raise ValueError('preserve existing session')
        before=state(a.dev)
        if 'SSID: iptime5GAX1500SR2\n' not in before['link']:raise ValueError('expected original SR2')
        original=run(['nmcli','-g','GENERAL.CON-UUID','device','show',a.dev]);owned='ROSPacer-multiphy-peer12-AX'
        if owned in run(['nmcli','-g','NAME','connection','show']).splitlines():raise ValueError('preserve existing name')
        run(['nmcli','connection','clone','iptime5GAX1500',owned]);uid=run(['nmcli','-g','connection.uuid','connection','show',owned])
        try:
            run(['nmcli','connection','modify','uuid',uid,'connection.autoconnect','no','ipv4.method','auto','ipv4.addresses','','ipv4.gateway','','ipv4.routes','','ipv6.method','ignore'])
            (folder/'baseline.json').write_text(json.dumps({'dev':a.dev,'original_uuid':original,'owned_uuid':uid,'before':before}))
            pid=subprocess.Popen(['systemd-inhibit','--what=sleep:idle','--mode=block','--who=ROSPacer','--why=FiniteMultiphyPeer12','python3',str(Path(__file__).resolve()),'guard','--folder',str(folder)],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True).pid
            (folder/'guard_pid.json').write_text(json.dumps({'pid':pid}));print(json.dumps({'ready':True,'pid':pid}),flush=True)
        except BaseException:run(['nmcli','connection','delete','uuid',uid]);raise
        return
    b=json.loads((folder/'baseline.json').read_text());deadline=time.monotonic()+21600;last=None
    try:
        while time.monotonic()<deadline:
            f=folder/'command.json'
            if f.exists():
                try:msg=json.loads(f.read_text())
                except (ValueError,OSError):time.sleep(.5);continue
                if msg.get('id')!=last and msg.get('action') in ['ax','sr2','end']:
                    last=msg['id']
                    if msg['action']=='end':break
                    uid=b['owned_uuid'] if msg['action']=='ax' else b['original_uuid']
                    run(['nmcli','connection','up','uuid',uid,'ifname',b['dev']]);(folder/'state.json').write_text(json.dumps({'id':last,'action':msg['action'],**state(b['dev'])}))
            time.sleep(.5)
    finally:
        run(['nmcli','connection','up','uuid',b['original_uuid'],'ifname',b['dev']]);run(['nmcli','connection','delete','uuid',b['owned_uuid']]);(folder/'restoration.json').write_text(json.dumps({'restored':True,**state(b['dev'])}))
if __name__=='__main__':main()
