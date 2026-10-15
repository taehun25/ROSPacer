"""Short-lived Ethernet egress to a verified Wi-Fi IP, no laptop IP changes."""
import json
import subprocess
import time
from pathlib import Path
import argparse

def cmd(args):return subprocess.run(args,capture_output=True,text=True,timeout=5)
def clean():
    r=cmd(['ip','-j','route','show','to','exact','192.168.0.4/32'])
    rows=json.loads(r.stdout)
    if any(x.get('dev')=='enp1s0' and x.get('prefsrc')=='192.168.0.5' for x in rows):
        cmd(['ip','route','del','192.168.0.4/32','dev','enp1s0'])
    rows=json.loads(cmd(['ip','-j','neigh','show','dev','enp1s0']).stdout)
    if any(x.get('dst')=='192.168.0.4' and x.get('lladdr')=='c4:c6:e6:e3:90:a5' for x in rows):
        cmd(['ip','neigh','del','192.168.0.4','dev','enp1s0'])

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['begin','guard','end']);p.add_argument('--folder',required=True);a=p.parse_args()
    folder=Path(a.folder)
    if a.mode=='end':(folder/'stop').write_text('stop');clean();print('{}');return
    if a.mode=='guard':
        deadline=time.monotonic()+180
        while time.monotonic()<deadline and not (folder/'stop').exists():time.sleep(.5)
        clean();return
    assert not json.loads(cmd(['ip','-j','route','show','to','exact','192.168.0.4/32']).stdout)
    assert not json.loads(cmd(['ip','-j','neigh','show','dev','enp1s0']).stdout)
    folder.mkdir(parents=True,exist_ok=False)
    subprocess.Popen(['python3',str(Path(__file__).resolve()),'guard','--folder',str(folder)],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
    try:
        for args in [['ip','route','add','192.168.0.4/32','dev','enp1s0','src','192.168.0.5'],['ip','neigh','add','192.168.0.4','lladdr','c4:c6:e6:e3:90:a5','nud','permanent','dev','enp1s0']]:
            q=cmd(args);assert q.returncode==0,q.stderr
    except BaseException:clean();raise
    print(json.dumps({'temporary_ethernet_egress':True,'expires_seconds':180}))

if __name__=='__main__':main()
