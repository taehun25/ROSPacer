"""Prepare guarded Ethernet management and source power for gap diagnosis."""
import argparse
import json
from pathlib import Path
import shlex
from deploy import ROOT,REMOTE
from w1_b2 import Control


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['begin','end']);a=p.parse_args()
    out=ROOT/'runs/w1_20261013_sender_gap';out.mkdir(exist_ok=True)
    c=Control('192.168.0.4' if a.mode=='begin' else '192.168.50.2','192.168.0.5','Wi-Fi 2',out);c.bind='192.168.0.11'
    homes={'4':'/home/csilab','5':'/home/csi'};folders={h:home+'/'+REMOTE+'/runs/'+out.name for h,home in homes.items()}
    results={}
    if a.mode=='begin':
        # User restored source .50.2 after Wi-Fi stopped answering ARP. Prepare
        # receiver first, then explicitly adopt that task-owned manual address.
        q=c.extra('5','sudo -n python3 '+homes['5']+'/'+REMOTE+'/tools/w1_management_guard.py begin --folder '+folders['5']+'/wire --address 192.168.50.1/24');assert q.returncode==0,q.stderr;results['wire5']=json.loads(q.stdout)
        c.ip4='192.168.50.2'
        identity=c.python('4',"import json,socket;print(json.dumps({'hostname':socket.gethostname()}))");assert identity['hostname']=='csilab'
        name='tools/w1_management_guard.py'
        script="from pathlib import Path;import sys;p=Path("+repr(homes['4']+'/'+REMOTE+'/'+name)+");p.write_bytes(sys.stdin.buffer.read())"
        q=c.extra('4','python3 -c '+shlex.quote(script),(ROOT/name).read_bytes());assert q.returncode==0,q.stderr
        q=c.extra('4','sudo -n python3 '+homes['4']+'/'+REMOTE+'/tools/w1_management_guard.py begin --folder '+folders['4']+'/wire --address 192.168.50.2/24 --adopt-address');assert q.returncode==0,q.stderr;results['wire4']=json.loads(q.stdout)
        q=c.extra('4','sudo -n python3 '+homes['4']+'/'+REMOTE+'/tools/w1_session.py begin --folder '+folders['4']+'/source_session --dev wlp2s0');assert q.returncode==0,q.stderr;results['session4']=json.loads(q.stdout)
        # Root guards create the run parent; data collectors use the normal
        # account. Change only that parent's owner, never earlier run files.
        for h,user in [('4','csilab'),('5','csi')]:
            q=c.extra(h,'sudo -n chown '+user+':'+user+' '+folders[h]);assert q.returncode==0,q.stderr
    else:
        q=c.extra('4','sudo -n python3 '+homes['4']+'/'+REMOTE+'/tools/w1_session.py end --folder '+folders['4']+'/source_session --dev wlp2s0');assert q.returncode==0,q.stderr;results['session4']=json.loads(q.stdout)
        q=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');assert q.returncode==0,q.stderr
        c.ip4='192.168.0.4';assert c.python('4',"import json,socket;print(json.dumps({'hostname':socket.gethostname()}))")['hostname']=='csilab'
        for h,address in [('4','192.168.50.2/24'),('5','192.168.50.1/24')]:
            q=c.extra(h,'sudo -n python3 '+homes[h]+'/'+REMOTE+'/tools/w1_management_guard.py end --folder '+folders[h]+'/wire --address '+address);assert q.returncode==0,q.stderr;results['wire'+h]=json.loads(q.stdout)
    (out/('setup_'+a.mode+'.json')).write_text(json.dumps(results,indent=2),encoding='utf8');print(json.dumps({'mode':a.mode,'source_wire_ready':a.mode=='begin','guards':list(results)}))


if __name__=='__main__':main()
