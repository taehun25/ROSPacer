"""Temporary direct-Ethernet address; remove only owned address on end/expiry."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def command(args):
    q=subprocess.run(args,capture_output=True,text=True,timeout=8)
    if q.returncode:raise RuntimeError(q.stderr)
    return q.stdout


def restore(folder):
    cfg=json.loads((folder/'baseline.json').read_text());address=cfg['address'];dev=cfg['dev']
    before=json.loads(command(['ip','-j','addr','show','dev',dev]))
    local=address.split('/')[0]
    if any(x.get('local')==local for d in before for x in d['addr_info']):command(['ip','addr','del',address,'dev',dev])
    after=json.loads(command(['ip','-j','addr','show','dev',dev]))
    r={'removed_owned_address':address,'after':after,'restored':not any(x.get('local')==local for d in after for x in d['addr_info'])}
    (folder/'restoration.json').write_text(json.dumps(r,indent=2));return r


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['begin','guard','end']);p.add_argument('--folder',required=True);p.add_argument('--address',choices=['192.168.50.1/24','192.168.50.2/24'],required=True);p.add_argument('--adopt-address',action='store_true',help='explicitly adopt only the task-owned sole matching manual IPv4');p.add_argument('--expiry-seconds',type=int,default=3600);a=p.parse_args()
    if not 60<=a.expiry_seconds<=21600:p.error('expiry must be60..21600seconds')
    folder=Path(a.folder).resolve()
    if os.geteuid()!=0 or 'ROSPacer' not in folder.parts or 'runs' not in folder.parts:raise ValueError('root and experiment folder required')
    if a.mode=='guard':
        end=time.monotonic()+a.expiry_seconds
        while time.monotonic()<end and not (folder/'end').exists():time.sleep(1)
        restore(folder);return
    if a.mode=='end':
        (folder/'end').write_text('end');print(json.dumps(restore(folder)));return
    dev='enp1s0';before=json.loads(command(['ip','-j','addr','show','dev',dev]))
    ipv4=[x for d in before for x in d['addr_info'] if x['family']=='inet']
    adopted=bool(a.adopt_address and len(ipv4)==1 and ipv4[0]['local']==a.address.split('/')[0] and ipv4[0]['prefixlen']==24)
    if ipv4 and not adopted:raise ValueError('preserve existing Ethernet IPv4 addresses')
    folder.mkdir(parents=True,exist_ok=False);(folder/'baseline.json').write_text(json.dumps({'dev':dev,'address':a.address,'before':before,'adopted_task_address':adopted},indent=2))
    pid=subprocess.Popen(['python3',str(Path(__file__).resolve()),'guard','--folder',str(folder),'--address',a.address,'--expiry-seconds',str(a.expiry_seconds)],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True).pid
    if not adopted:command(['ip','addr','add',a.address,'dev',dev])
    print(json.dumps({'pid':pid,'address':a.address,'expiry_s':a.expiry_seconds,'adopted_task_address':adopted}))


if __name__=='__main__':main()
