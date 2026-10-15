"""Restore only owned sender-prototype changes and verify all four hosts."""
import json
from pathlib import Path
from deploy import ROOT,REMOTE,ssh
from w1_b2 import Control,SR2,OTHER


def main():
    base=ROOT/'runs/w1_20261013_sender_only';c=Control('192.168.0.4','192.168.0.5','Wi-Fi 2',base);results={}
    source="""import subprocess,json
r={}
for k,args in {'interfaces':['iw','dev'],'link':['iw','dev',DEV,'link'],'qdisc':['tc','-j','qdisc','show','dev',DEV],'sysctl':['sysctl','net.core.rmem_max','net.core.wmem_max'],'power':['iw','dev',DEV,'get','power_save'],'addresses':['ip','-j','address'],'processes':['ps','-eo','pid,args']}.items():
 q=subprocess.run(args,capture_output=True,text=True,timeout=6);r[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
print(json.dumps(r))
"""
    try:
        c.connect(SR2)
        for h,dev in [('12','wlo1'),('10','wlp2s0')]:
            q=ssh(h,'python3 -',('DEV='+repr(dev)+'\n'+source).encode());assert q.returncode==0,q.stderr;results[h]=json.loads(q.stdout)
    finally:c.connect(OTHER)
    # Source is reachable over restored Wi-Fi; remove the user-added address
    # there, then end the receiver's independently guarded wired address.
    q=c.extra('4','sudo -n ip address del 192.168.50.2/24 dev enp1s0');assert q.returncode==0,q.stderr
    guard='/home/csi/'+REMOTE+'/runs/w1_20261013_sender_only/wire_recovery'
    q=c.extra('5','sudo -n python3 /home/csi/'+REMOTE+'/tools/w1_management_guard.py end --folder '+guard+' --address 192.168.50.1/24');assert q.returncode==0,q.stderr
    results['wire5_restoration']=json.loads(q.stdout)
    for h in ['4','5']:
        results[h]=c.python(h,"DEV='wlp2s0'\n"+source)
        r=results[h]
        assert 'rpmon' not in r['interfaces']['stdout'] and 'w1mon' not in r['interfaces']['stdout']
        assert all(q['kind']=='noqueue' for q in json.loads(r['qdisc']['stdout']))
        assert 'net.core.rmem_max = 212992' in r['sysctl']['stdout'] and 'net.core.wmem_max = 212992' in r['sysctl']['stdout']
        assert 'Power save: on' in r['power']['stdout']
        assert not any(x.get('local') in ['192.168.50.1','192.168.50.2'] for d in json.loads(r['addresses']['stdout']) for x in d['addr_info'])
    for h in ['4','5','12','10']:
        assert not any(s in results[h]['processes']['stdout'] for s in ['tools/traffic.py',' -m rospacer sender-observe','iperf3 -c','iperf3 -s','tools/w1_monitor_guard.py'])
    results['restored']=True;results['notes']='Wi-Fi AX4/5, SR2 12/10; monitors removed; no prototype traffic; sysctl/power/root qdisc restored; owned wired IPv4 removed; kernel modules unchanged.'
    (base/'final_restoration.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    print(json.dumps({'restored':True,'verified_hosts':['4','5','12','10'],'owned_wired_addresses_removed':True,'prototype_processes':0}))


if __name__=='__main__':main()
