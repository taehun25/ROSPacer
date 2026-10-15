"""Recover a failed finite probe over Ethernet; preserve its failure label."""
import json
from pathlib import Path
import shlex
from deploy import ROOT,REMOTE,ssh
from w1_b2 import Control,SR2,OTHER

def main():
    base=ROOT/'runs/w1_20261013_sender_gap';label='control_b2_repeat'
    c=Control('192.168.50.2','192.168.0.5','Wi-Fi 2',base);c.bind='192.168.0.11'
    local=base/label;local.mkdir(exist_ok=True)
    for h,user in [('4','csilab'),('5','csi')]:
        folder='/home/'+user+'/'+REMOTE+'/runs/'+base.name+'/'+label
        target=local/h;target.mkdir(exist_ok=True)
        for name in ['air.pcap','air.state.json','air.pcap.capture.log','guard.log','radio.json','radio.log']+(['server.json'] if h=='5' else []):
            q=c.extra(h,'cat '+shlex.quote(folder+'/'+name));assert q.returncode==0,q.stderr
            (target/name).write_bytes(q.stdout)
    diagnostic=c.python('4',"import json,subprocess; r={}\nfor k,args in {'link':['iw','dev','wlp2s0','link'],'neighbors':['ip','neigh','show'],'dmesg':['sudo','-n','dmesg','--since','30 minutes ago'],'interfaces':['iw','dev']}.items():\n q=subprocess.run(args,capture_output=True,text=True,timeout=7);r[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}\nprint(json.dumps(r))")
    diagnostic['failed_run_reason']='main iperf TCP control connection timeout; post-run ARP to peer failed; no valid delivered-load measurement'
    (local/'failure.json').write_text(json.dumps(diagnostic,indent=2),encoding='utf8')
    try:
        c.connect(SR2)
        for h,user,name in [('12','csi2','client.json'),('10','csi','server.json')]:
            folder='/home/'+user+'/'+REMOTE+'/runs/'+base.name+'/'+label+'_background'
            q=ssh(h,'cat '+shlex.quote(folder+'/'+name));assert q.returncode==0,q.stderr
            (base/(label+'_background')/(h+'_'+name)).write_bytes(q.stdout)
    finally:c.connect(OTHER)
    q=c.extra('4','sudo -n nmcli connection up id iptime5GAX1500 ifname wlp2s0');assert q.returncode==0,q.stderr
    q=c.extra('4','ping -c 2 -W 2 192.168.0.5');assert q.returncode==0,q.stdout
    (local/'reconnect.json').write_text(json.dumps({'reconnected_same_profile':True,'peer_ping':q.stdout.decode()},indent=2))
    print(json.dumps({'failed_capture_recovered':True,'peer_ping_restored':True}))

if __name__=='__main__':main()
