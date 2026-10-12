"""Reversible manual management address on laptop5's direct Ethernet link.

Keeps the existing NetworkManager profiles intact. Laptop4 already has
192.168.50.2/24; laptop5's disconnected interface gets192.168.50.1/24.
An independent guard removes only the address we add if confirmation fails.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

ADDRESS = '192.168.50.1/24'
DEV = 'enp1s0'


def command(args):
    q = subprocess.run(args,capture_output=True,text=True,timeout=10)
    if q.returncode:
        raise RuntimeError(q.stderr)
    return q.stdout.strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['begin','guard','end'])
    p.add_argument('--folder',type=Path,required=True)
    a = p.parse_args()
    folder = a.folder.resolve()
    if os.geteuid()!=0 or folder.parts[-3:]!=('w1_20261012_radio45','clock_link','5'):
        raise ValueError('root and exact laptop5 clock-link artifact path required')
    if a.mode=='begin':
        folder.mkdir(parents=True,exist_ok=False)
        addresses=json.loads(command(['ip','-j','addr','show','dev',DEV]))
        if any(row['family']=='inet' for dev in addresses for row in dev['addr_info']):
            raise ValueError('preserve pre-existing Ethernet address')
        token=secrets.token_hex(16)
        (folder/'baseline.json').write_text(json.dumps({'address':ADDRESS,'dev':DEV,'addresses':addresses,'token':token},indent=2))
        q=subprocess.Popen(['python3',str(Path(__file__).resolve()),'guard','--folder',str(folder)],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
        command(['ip','addr','add',ADDRESS,'dev',DEV])
        print(json.dumps({'pid':q.pid,'token':token,'confirmation_timeout_s':90}),flush=True)
    elif a.mode=='guard':
        token=json.loads((folder/'baseline.json').read_text())['token']
        end=time.monotonic()+90
        while time.monotonic()<end:
            marker=folder/'confirmed.json'
            if marker.exists() and json.loads(marker.read_text()).get('token')==token:
                (folder/'confirmed_result.json').write_text(json.dumps({'confirmed':True}))
                return
            time.sleep(1)
        command(['ip','addr','del',ADDRESS,'dev',DEV])
        (folder/'rollback.json').write_text(json.dumps({'removed_only':ADDRESS}))
    else:
        command(['ip','addr','del',ADDRESS,'dev',DEV])
        (folder/'ended.json').write_text(json.dumps({'removed_only':ADDRESS}))


if __name__=='__main__':
    main()
