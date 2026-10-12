"""Guarded activation of existing WiFi profiles, keeping wired management.

No passwords/profiles modified. Both APs are user-authorised test APs.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def command(args):
    q=subprocess.run(args,capture_output=True,text=True,timeout=30)
    if q.returncode:raise RuntimeError(q.stderr or q.stdout)
    return q.stdout


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['begin','guard']);p.add_argument('--ssid',choices=['iptime5GAX1500','iptime5GAX1500SR2'],required=True);p.add_argument('--folder',required=True);a=p.parse_args()
    folder=Path(a.folder).resolve()
    if os.geteuid()!=0 or 'ROSPacer' not in folder.parts or 'runs' not in folder.parts:p.error('root and artifact folder required')
    if a.mode=='begin':
        q=subprocess.run(['pgrep','-af','[i]perf3|[t]raffic.py|[r]ospacer govern'],capture_output=True,text=True)
        if q.returncode!=1:raise RuntimeError('preserve running traffic')
        uuid=command(['nmcli','-g','GENERAL.CON-UUID','dev','show','wlp2s0']).strip()
        target=command(['nmcli','-g','connection.uuid','connection','show',a.ssid]).strip()
        if not uuid or not target:raise RuntimeError('existing profile unavailable')
        folder.mkdir(parents=True,exist_ok=False)
        (folder/'baseline.json').write_text(json.dumps({'original_uuid':uuid,'target_uuid':target,'target_ssid':a.ssid}))
        q=subprocess.Popen(['python3',str(Path(__file__).resolve()),'guard','--ssid',a.ssid,'--folder',str(folder)],stdin=subprocess.DEVNULL,stdout=open(folder/'guard.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
        print(json.dumps({'pid':q.pid,'delay':5,'confirmation_timeout_s':150}));return
    b=json.loads((folder/'baseline.json').read_text());result={'confirmed':False}
    try:
        time.sleep(5);command(['nmcli','--wait','25','con','up','uuid',b['target_uuid'],'ifname','wlp2s0'])
        end=time.monotonic()+150
        while time.monotonic()<end:
            if (folder/'confirmed').exists():result['confirmed']=True;break
            time.sleep(1)
    except Exception as e:result['error']=str(e)
    finally:
        if not result['confirmed']:result['rollback']=command(['nmcli','--wait','25','con','up','uuid',b['original_uuid'],'ifname','wlp2s0'])
        result['link']=command(['iw','dev','wlp2s0','link']);result['addresses']=json.loads(command(['ip','-j','addr','show','dev','wlp2s0']))
        (folder/'result.json').write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()
