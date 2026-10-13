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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['begin','guard','end']);p.add_argument('--folder',required=True);p.add_argument('--address',choices=['192.168.50.1/24','192.168.50.2/24'],required=True);a=p.parse_args()
    folder=Path(a.folder).resolve()
    if os.geteuid()!=0 or 'ROSPacer' not in folder.parts or 'runs' not in folder.parts:raise ValueError('root and experiment folder required')
    if a.mode=='guard':
        end=time.monotonic()+3600
        while time.monotonic()<end and not (folder/'end').exists():time.sleep(1)
        restore(folder);return
    if a.mode=='end':
        (folder/'end').write_text('end');print(json.dumps(restore(folder)));return
    dev='enp1s0';before=json.loads(command(['ip','-j','addr','show','dev',dev]))
    if any(x['family']=='inet' for d in before for x in d['addr_info']):raise ValueError('preserve existing Ethernet IPv4 addresses')
    folder.mkdir(parents=True,exist_ok=False);(folder/'baseline.json').write_text(json.dumps({'dev':dev,'address':a.address,'before':before},indent=2))
    pid=subprocess.Popen(['python3',str(Path(__file__).resolve()),'guard','--folder',str(folder),'--address',a.address],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True).pid
    command(['ip','addr','add',a.address,'dev',dev]);print(json.dumps({'pid':pid,'address':a.address,'expiry_s':3600}))


if __name__=='__main__':main()
