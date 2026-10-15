"""Finite, non-shaping sender-side monitor feasibility experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import time
import socket
import struct
from deploy import ROOT, REMOTE
from w1_b2 import Control


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--inventory-only',action='store_true')
    p.add_argument('--label',default='pilot')
    p.add_argument('--rate-mbps',type=float,default=100)
    p.add_argument('--management4',default='192.168.0.4')
    p.add_argument('--awake',action='store_true')
    p.add_argument('--fcsfail',action='store_true')
    p.add_argument('--ap-control',action='store_true')
    p.add_argument('--origin',choices=['sender','pc'],default='sender')
    a=p.parse_args()
    if Path(a.run).name!=a.run:p.error('single run directory required')
    out=ROOT/'runs'/a.run;out.mkdir(parents=True,exist_ok=True)
    c=Control(a.management4,'192.168.0.5','Wi-Fi 2',out);c.bind='192.168.0.11'
    reports={}
    for h in ['5','4']:
        code="""import json,subprocess
from pathlib import Path
r={'hostname':subprocess.check_output(['hostname'],text=True).strip()}
for k,args in {'link':['iw','dev','wlp2s0','link'],'info':['iw','dev','wlp2s0','info'],'interfaces':['iw','dev'],'addresses':['ip','-j','address'],'qdisc':['tc','-j','qdisc','show','dev','wlp2s0'],'programs':['bash','-c','command -v tshark; command -v tcpdump; command -v iperf3'],'processes':['ps','-eo','pid,args'],'root':['sudo','-n','true']}.items():
 q=subprocess.run(args,capture_output=True,text=True,timeout=8);r[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
print(json.dumps(r))
"""
        reports[h]=c.python(h,code)
    (out/'inventory.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
    for h,r in reports.items():
        print(json.dumps({'host':h,'hostname':r['hostname'],'link':r['link']['stdout'],'root':r['root']['rc'],'programs':r['programs']['stdout']}),flush=True)
    if a.inventory_only:return
    if Path(a.label).name!=a.label:p.error('single label required')
    if not 10<=a.rate_mbps<=350:p.error('bounded 10..350Mbps required')
    label=a.label;local=out/label;local.mkdir(exist_ok=False)
    homes={'4':'/home/csilab','5':'/home/csi'}
    folders={h:home+'/'+REMOTE+'/runs/'+a.run+'/'+label for h,home in homes.items()}
    for h,r in reports.items():
        assert 'SSID: iptime5GAX1500\n' in r['link']['stdout']
        assert 'channel 149 ' in r['info']['stdout'] and 'width: 80 MHz' in r['info']['stdout']
        assert 'w1mon' not in r['interfaces']['stdout']
        assert all(q['kind']=='noqueue' for q in json.loads(r['qdisc']['stdout']))
        assert not any(x in r['processes']['stdout'] for x in ['tools/traffic.py','tools/w1_counter_worker.py',' -m rospacer govern','iperf3 -c','iperf3 -s'])
        for name in ['tools/w1_monitor_guard.py','tools/w1_counter_worker.py','tools/w1_gap_sink.py']:
            script="from pathlib import Path;import sys;p=Path("+repr(homes[h]+'/'+REMOTE+'/'+name)+");p.write_bytes(sys.stdin.buffer.read())"
            q=c.extra(h,'python3 -c '+shlex.quote(script),(ROOT/name).read_bytes());assert q.returncode==0,q.stderr
        c.python(h,"import json;from pathlib import Path;Path("+repr(folders[h])+").mkdir(parents=True,exist_ok=False);print('{}')")
    def launch(h,args,name):
        return c.python(h,"import json,subprocess;from pathlib import Path;p=Path("+repr(folders[h])+");q=subprocess.Popen("+repr(args)+",cwd="+repr(homes[h]+'/'+REMOTE)+",stdin=subprocess.DEVNULL,stdout=open(p/"+repr(name)+",'w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))")
    for h in homes:
        launch(h,['sudo','-n','timeout','-k','3','27','python3','tools/w1_monitor_guard.py','--seconds','20','--out',folders[h]+'/air.pcap']+(['--disable-power-save'] if a.awake and h=='4' else [])+(['--fcsfail'] if a.fcsfail else [])+(['--ap-control'] if a.ap_control else []),'guard.log')
        launch(h,['sudo','-n','timeout','-k','2','26','python3','tools/w1_counter_worker.py','--mode','observe','--seconds','21','--interval','.2','--out',folders[h]+'/radio.json'],'radio.log')
    launch('5',['timeout','-k','2','20','iperf3','-s','-1','-B','192.168.0.5','-p','55920','-J'] if a.origin=='sender' else ['timeout','-k','2','21','python3','tools/w1_gap_sink.py','--out',folders['5']+'/sink.json'],'server.json' if a.origin=='sender' else 'sink.log')
    time.sleep(3)
    if a.origin=='sender':
        args=['iperf3','-c','192.168.0.5','-B','192.168.0.4','-p','55920','--connect-timeout','2000','-u','-b',str(round(a.rate_mbps*1e6)),'-l','1400','-t','8','-J']
        client=c.python('4',"import json,subprocess,time;start=time.time()\ntry:\n q=subprocess.run("+repr(args)+",capture_output=True,text=True,timeout=14);r={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}\nexcept subprocess.TimeoutExpired as e:\n r={'rc':124,'stdout':(e.stdout or b'').decode() if isinstance(e.stdout,bytes) else (e.stdout or ''),'stderr':'main iperf control/data timeout; preserve failed capture'}\nr.update(start_wall=start,end_wall=time.time());print(json.dumps(r))")
    else:
        before=time.time();anchor=c.python('4',"import json,time;print(json.dumps({'wall':time.time()}))");after=time.time();offset=(before+after)/2-anchor['wall']
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('192.168.0.11',0));seq=0;timeline=[]
        start=time.time();due=time.perf_counter();end=due+8;period=32*1400*8/(a.rate_mbps*1e6)
        try:
            while time.perf_counter()<end:
                stamp=time.time()-offset
                for _ in range(32):sock.sendto(b'GAPPROBE'+struct.pack('<Q',seq)+bytes(1384),('192.168.0.5',55926));seq+=1
                timeline.append({'wall':stamp,'packets':32});due+=period;time.sleep(max(0,due-time.perf_counter()))
            for _ in range(3):sock.sendto(b'GAPEOF',('192.168.0.5',55926))
        finally:sock.close()
        client={'origin':'pc','rc':0,'start_wall':start-offset,'end_wall':time.time()-offset,'PC_minus_sender_wall_s':offset,'anchor_roundtrip_s':after-before,'sent_packets':seq,'sent_payload_bytes':seq*1400,'send_timeline':timeline,'qualification':'observer4 is not transmitting user data; coarse sender clock alignment only'}
    (local/'client.json').write_text(json.dumps(client,indent=2))
    time.sleep(12)
    for h in homes:
        dest=local/h;dest.mkdir()
        for name in ['air.pcap','air.state.json','air.pcap.capture.log','guard.log','radio.json','radio.log']+([('server.json' if a.origin=='sender' else 'sink.json')] if h=='5' else []):
            q=c.extra(h,'cat '+shlex.quote(folders[h]+'/'+name));assert q.returncode==0,q.stderr
            (dest/name).write_bytes(q.stdout)
        state=json.loads((dest/'air.state.json').read_text());assert state['monitor_removed'] and 'error' not in state,state
        print(json.dumps({'capture_host':h,'bytes':(dest/'air.pcap').stat().st_size,'monitor_removed':True}),flush=True)
    print(json.dumps({'run':a.run,'pilot_complete':True,'client_rc':client['rc']}),flush=True)
    if client['rc']!=0:raise RuntimeError('failed main traffic; capture archived, exclude from performance/model results')


if __name__=='__main__':main()
