"""Coordinate the explicitly started laptop10 monitor with main4/5 probes.

Requires the local operator to start the reviewed bounded root capture guard.
Does not grant privileges or alter the capture laptop's stored profiles.
"""
import argparse
import json
import time
from deploy import ROOT,REMOTE,ssh
from w1_b2 import OTHER,SR2,Control
from w1_radio45 import Pair


def ten(code):
    q=ssh('10','python3 -',code.encode())
    if q.returncode:raise RuntimeError(q.stderr.decode())
    return json.loads(q.stdout)


def main():
    run='w1_20261012_radio45';remote10='/home/csi/'+REMOTE+'/runs/'+run+'/independent10'
    ready=ten('import json;from pathlib import Path;p=Path('+repr(remote10+'/air.state.json')+');print(json.dumps(json.loads(p.read_text()) if p.exists() else {}))')
    if not ready.get('waiting_for_start') or ready.get('monitor_removed'):raise RuntimeError('operator capture is not ready; no measurement started')
    a=argparse.Namespace(run=run,ip4='192.168.0.4',ip5='192.168.0.5',ssid=OTHER);pair=Pair(a,'independent10_main');results={}
    try:
        pair.c.connect(OTHER)
        # Reestablish a fresh bounded preparation, irrespective of phase2 expiry.
        for h,home in pair.home.items():
            folder=home+'/'+REMOTE+'/runs/'+run
            q=pair.c.extra(h,'sudo -n python3 '+home+'/'+REMOTE+'/tools/w1_session.py end --folder '+folder+'/session_phase2 --dev wlp2s0');assert q.returncode==0,q.stderr
        time.sleep(3)
        for h,home in pair.home.items():
            folder=home+'/'+REMOTE+'/runs/'+run+'/session_independent10'
            q=pair.c.extra(h,'sudo -n python3 '+home+'/'+REMOTE+'/tools/w1_session.py begin --folder '+folder+' --dev wlp2s0');assert q.returncode==0,q.stderr
            q=pair.c.extra(h,'sudo -n sysctl -w net.core.rmem_max=1048576 net.core.wmem_max=1048576');assert q.returncode==0,q.stderr
        pair.check();pair.c.connect(SR2)
        anchor=ten('import time,json;print(json.dumps({"wall_ns":time.time_ns(),"monotonic_s":time.monotonic()}))')
        ten('from pathlib import Path;Path('+repr(remote10+'/air.start')+').write_text("start authorised paired measurement");print("{}")')
        pair.c.connect(OTHER)
        for name in ['idle','ap_only','relay']:
            if name=='relay':pair.launch('5',['timeout','-k','2','14','iperf3','-s','-1','-B',a.ip5,'-p','55315','-J'],name+'_server.json');time.sleep(.3)
            code="import json,time,socket,subprocess,sys;sys.path.insert(0,"+repr(pair.home['4']+'/'+REMOTE)+");from rospacer.linux import observe;before=observe('wlp2s0');start=time.time_ns();tx=0\n"
            if name=='idle':code+='time.sleep(6)\n'
            elif name=='ap_only':code+="s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('192.168.0.4',0));s.settimeout(.1);payload=b'W1AP'+bytes(1396);deadline=time.monotonic()+8;due=time.monotonic()\nwhile time.monotonic()<deadline:\n for i in range(9):\n  try:s.sendto(payload,('192.168.0.1',55315));tx+=1\n  except OSError:pass\n due+=.001;time.sleep(max(0,due-time.monotonic()))\ns.close()\n"
            else:code+="q=subprocess.run(['iperf3','-c','192.168.0.5','-B','192.168.0.4','-p','55315','-u','-b','100000000','-l','1400','-w','1048576','-t','8','-J'],capture_output=True,text=True,timeout=12)\n"
            code+="end=time.time_ns();after=observe('wlp2s0');r={'before':before,'after':after,'start_wall_ns':start,'end_wall_ns':end,'sent_datagrams':tx,'delta':{k:after[k]-before[k] for k in ['active_s','busy_s','tx_s','bytes','packets','retries']}}\n"
            if name=='relay':code+="r.update(client_rc=q.returncode,client_stdout=q.stdout,client_stderr=q.stderr)\n"
            code+='print(json.dumps(r))';q=pair.c.extra('4','sudo -n python3 -',code.encode());assert q.returncode==0,q.stderr;r=json.loads(q.stdout);results[name]=r;(pair.out/(name+'.json')).write_bytes(q.stdout);print(json.dumps({'phase':name,'delta':r['delta']}),flush=True)
        pair.c.connect(SR2)
        ten("import json,time;from pathlib import Path;p=Path("+repr(remote10+'/air.state.json')+");end=time.monotonic()+20\nwhile not json.loads(p.read_text()).get('monitor_removed') and time.monotonic()<end:time.sleep(.5)\nassert json.loads(p.read_text()).get('monitor_removed'),'capture guard not finished';print('{}')")
        out=ROOT/'runs'/run/'independent10';out.mkdir(exist_ok=True)
        for name in ['air.pcap','air.pcap.capture.log','air.state.json']:
            q=ssh('10','cat '+remote10+'/'+name);assert q.returncode==0,q.stderr;(out/name).write_bytes(q.stdout)
        fields=ten("import subprocess,json;q=subprocess.run(['tshark','-G','fields'],capture_output=True,text=True,timeout=15);selected=[s for s in q.stdout.splitlines() if any(k in s for k in ['radiotap.he.','radiotap.ampdu.reference','wlan_radio.duration','wlan_radio.data_rate','wlan.qos.amsdupresent'])];print(json.dumps({'rc':q.returncode,'fields':selected}))")
        (out/'available_phy_fields.json').write_text(json.dumps(fields,indent=2));results['observer_anchor']=anchor;results['observer_state']=json.loads((out/'air.state.json').read_text());results['clock_scope']='coarse overlap; laptop10 clock is not E2E qualified';(pair.out/'summary.json').write_text(json.dumps(results,indent=2))
    finally:pair.c.connect(SR2)


if __name__=='__main__':main()
