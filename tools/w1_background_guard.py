"""Finite two-profile AP controller for unattended background host10.

Only ax/sr2/end markers are accepted. No arbitrary command or privileged input.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

def run(args):
    q=subprocess.run(args,capture_output=True,text=True,timeout=30)
    if q.returncode:raise RuntimeError(q.stderr)
    return q.stdout.strip()

def state():
    return {'wall':time.time(),'addresses':json.loads(run(['ip','-j','addr','show','dev','wlp2s0'])),'link':run(['iw','dev','wlp2s0','link'])}

def restore(folder):
    b=json.loads((folder/'baseline.json').read_text())
    run(['nmcli','connection','up','uuid',b['original_uuid'],'ifname','wlp2s0'])
    run(['nmcli','connection','delete','uuid',b['owned_uuid']])
    (folder/'restoration.json').write_text(json.dumps({'restored':True,'state':state()}))

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['begin','guard']);p.add_argument('--folder',required=True);a=p.parse_args()
    folder=Path(a.folder).resolve()
    if os.geteuid()!=0 or 'ROSPacer' not in folder.parts or 'runs' not in folder.parts:raise ValueError('root and owned run folder required')
    if a.mode=='begin':
        if (folder/'baseline.json').exists():raise ValueError('preserve existing session')
        folder.mkdir(parents=True,exist_ok=True)
        # The unprivileged controller writes only finite AP action markers.
        # A manually invoked sudo begin may have created the run parent as root.
        owner=int(os.environ.get('SUDO_UID',0));group=int(os.environ.get('SUDO_GID',0))
        if owner and folder.parent.parent.name=='runs' and folder.parent.name.startswith('w1_'):
            os.chown(folder.parent,owner,group);os.chown(folder,owner,group)
        original=run(['nmcli','-g','GENERAL.CON-UUID','device','show','wlp2s0'])
        if 'SSID: iptime5GAX1500SR2' not in state()['link']:raise ValueError('expected original SR2 connection')
        owned='ROSPacer-sender-validation-10-AX'
        names=run(['nmcli','-g','NAME','connection','show']).splitlines()
        if owned in names:raise ValueError('preserve existing profile name')
        run(['nmcli','connection','clone','iptime5GAX1500',owned])
        uuid=run(['nmcli','-g','connection.uuid','connection','show',owned])
        try:
            run(['nmcli','connection','modify','uuid',uuid,'connection.autoconnect','no','ipv4.method','auto','ipv4.addresses','','ipv4.gateway','','ipv4.routes','','ipv6.method','ignore'])
            (folder/'baseline.json').write_text(json.dumps({'original_uuid':original,'owned_uuid':uuid,'before':state()}))
            pid=subprocess.Popen(['systemd-inhibit','--what=sleep:idle','--mode=block','--who=ROSPacer','--why=Finite sender validation','python3',str(Path(__file__).resolve()),'guard','--folder',str(folder)],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True).pid
        except BaseException:
            run(['nmcli','connection','delete','uuid',uuid]);raise
        print(json.dumps({'ready':True,'pid':pid,'expires_hours':6}),flush=True);return
    baseline=json.loads((folder/'baseline.json').read_text());deadline=time.monotonic()+21600;last=None
    try:
        while time.monotonic()<deadline:
            path=folder/'command.json'
            if path.exists():
                try:msg=json.loads(path.read_text())
                except (ValueError,OSError):time.sleep(.5);continue
                if msg.get('id')!=last and msg.get('action') in ['ax','sr2','end']:
                    last=msg['id']
                    if msg['action']=='end':break
                    uuid=baseline['owned_uuid'] if msg['action']=='ax' else baseline['original_uuid']
                    run(['nmcli','connection','up','uuid',uuid,'ifname','wlp2s0'])
                    (folder/'state.json').write_text(json.dumps({'id':last,'action':msg['action'],**state()}))
            time.sleep(.5)
    finally:restore(folder)

if __name__=='__main__':main()
