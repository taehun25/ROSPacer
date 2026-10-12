"""Diagnose self-TX versus AP relay: direct AP traffic, then station relay.

Monitor capture is restricted to the two authorised station MACs. No change
to station channel, AP profile, driver, or firmware. Raw counter differences
are observations; not an automatic semantics/model qualification.
"""
import argparse
import json
import shlex
import time
from w1_radio45 import Pair
from w1_b2 import OTHER,SR2
from deploy import ROOT,REMOTE


def main():
    a=argparse.Namespace(run='w1_20261012_radio45',ip4='192.168.0.4',ip5='192.168.0.5',ssid=OTHER)
    pair=Pair(a,'semantics');results={}
    try:
        pair.c.connect(OTHER);pair.check()
        source='import sys;from pathlib import Path;Path('+repr(pair.home['4']+'/'+REMOTE+'/tools/w1_monitor_guard.py')+').write_bytes(sys.stdin.buffer.read())'
        q=pair.c.extra('4','python3 -c '+shlex.quote(source),(ROOT/'tools/w1_monitor_guard.py').read_bytes());assert q.returncode==0,q.stderr
        pair.launch('4',['sudo','-n','timeout','-k','3','45','python3','tools/w1_monitor_guard.py','--seconds','38','--out',pair.base['4']+'/air.pcap'],'monitor.log')
        time.sleep(2)
        for name,peer in [('idle',None),('ap_only','192.168.0.1'),('relay','192.168.0.5')]:
            print('SEMANTICS '+name,flush=True)
            if name=='relay':pair.launch('5',['timeout','-k','2','14','iperf3','-s','-1','-B',a.ip5,'-p','55314','-J'],name+'_server.json');time.sleep(.3)
            base="import json,time,socket,subprocess,sys;sys.path.insert(0,"+repr(pair.home['4']+'/'+REMOTE)+");from rospacer.linux import observe;before=observe('wlp2s0');start=time.time_ns();tx=0\n"
            if name=='ap_only':
                base+="s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('192.168.0.4',0));s.settimeout(.1);payload=b'W1AP'+bytes(1396);deadline=time.monotonic()+8;due=time.monotonic();period=.001;batch=9\nwhile time.monotonic()<deadline:\n for i in range(batch):\n  try:s.sendto(payload,('192.168.0.1',55314));tx+=1\n  except OSError:pass\n due+=period;time.sleep(max(0,due-time.monotonic()))\ns.close()\n"
            elif name=='relay':
                base+="q=subprocess.run(['iperf3','-c','192.168.0.5','-B','192.168.0.4','-p','55314','-u','-b','100000000','-l','1400','-w','1048576','-t','8','-J'],capture_output=True,text=True,timeout=12)\n"
            else:base+='time.sleep(6)\n'
            base+="end=time.time_ns();after=observe('wlp2s0');r={'before':before,'after':after,'start_wall_ns':start,'end_wall_ns':end,'sent_datagrams':tx,'delta':{k:after[k]-before[k] for k in ['active_s','busy_s','tx_s','bytes','packets','retries']}}\n"
            if name=='relay':base+="r.update(client_rc=q.returncode,client_stdout=q.stdout,client_stderr=q.stderr)\n"
            base+='print(json.dumps(r))'
            q=pair.c.extra('4','sudo -n python3 -',base.encode());assert q.returncode==0,q.stderr
            results[name]=json.loads(q.stdout);(pair.out/(name+'.json')).write_bytes(q.stdout)
            print(json.dumps({'phase':name,'delta':results[name]['delta'],'sent_datagrams':results[name]['sent_datagrams']}),flush=True)
        time.sleep(14)
        for filename in ['air.pcap','air.pcap.capture.log','air.state.json','monitor.log']:
            q=pair.c.extra('4','cat '+shlex.quote(pair.base['4']+'/'+filename));assert q.returncode==0,q.stderr;(pair.out/filename).write_bytes(q.stdout)
        results['monitor_state']=json.loads((pair.out/'air.state.json').read_text());results['qualification']='qualitative probe; counters and radiotap reference retain uncertainty; no automatic model acceptance'
        (pair.out/'summary.json').write_text(json.dumps(results,indent=2))
    finally:pair.c.connect(SR2)


if __name__=='__main__':main()
