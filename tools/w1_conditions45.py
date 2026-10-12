"""Counter-capable B2/C2 trials with finite 12->10 background traffic."""
import argparse
import json
import os
from pathlib import Path
import shlex
import statistics
import subprocess
import time

from deploy import ROOT,REMOTE,ssh
from w1_b2 import Control,OTHER,SR2,pair_check
from w1_radio45 import Pair


def remote(h,source):
    q=ssh(h,'python3 -',source.encode())
    if q.returncode:raise RuntimeError(q.stderr.decode())
    return json.loads(q.stdout)


def start(h,args,folder,log):
    return remote(h,'import subprocess,json;from pathlib import Path;p=Path('+repr(folder)+');p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen('+repr(args)+',stdin=subprocess.DEVNULL,stdout=open(p/'+repr(log)+',"w"),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({"pid":q.pid}))')


def read(h,path):
    q=ssh(h,'cat '+shlex.quote(path))
    if q.returncode:raise RuntimeError(q.stderr.decode())
    return q.stdout.decode()


def migrate(c,ssid,label,run,ip5):
    folders={h:home+'/'+REMOTE+'/runs/'+run+'/moves/'+label for h,home in [('4','/home/csilab'),('5','/home/csi')]}
    c.ip4='192.168.50.2'  # preserve management through the direct wire
    for h in ['4','5']:
        home='/home/csilab' if h=='4' else '/home/csi'
        script='import sys;from pathlib import Path;Path('+repr(home+'/'+REMOTE+'/tools/w1_move45.py')+').write_bytes(sys.stdin.buffer.read())'
        q=c.extra(h,'python3 -c '+shlex.quote(script),(ROOT/'tools/w1_move45.py').read_bytes());assert q.returncode==0,q.stderr
        q=c.extra(h,'sudo -n python3 '+home+'/'+REMOTE+'/tools/w1_move45.py begin --ssid '+ssid+' --folder '+folders[h]);assert q.returncode==0,q.stderr
    c.connect(ssid);c.ip5=ip5
    deadline=time.monotonic()+90
    while True:
        try:
            addresses={}
            for h in ['5','4']:
                r=c.python(h,"import subprocess,json;print(json.dumps({'link':subprocess.check_output(['iw','dev','wlp2s0','link'],text=True),'addresses':json.loads(subprocess.check_output(['ip','-j','addr','show','dev','wlp2s0'],text=True))}))")
                if 'SSID: '+ssid+'\n' not in r['link']:raise RuntimeError('AP not switched')
                addresses[h]=next(v['local'] for dev in r['addresses'] for v in dev['addr_info'] if v['family']=='inet')
            break
        except Exception:
            if time.monotonic()>deadline:raise
            time.sleep(3)
    for h in ['4','5']:
        q=c.extra(h,"sudo -n python3 -c "+shlex.quote("from pathlib import Path;Path("+repr(folders[h]+'/confirmed')+").write_text('verified host identity, AP and address')"));assert q.returncode==0,q.stderr
        q=c.extra(h,'sudo -n iw dev wlp2s0 set power_save off');assert q.returncode==0,q.stderr
    (c.out/(label+'_addresses.json')).write_text(json.dumps(addresses,indent=2))
    print(json.dumps({'MOVED':ssid,'addresses':addresses}),flush=True)
    return addresses


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['b2','c2']);p.add_argument('--run',required=True);a=p.parse_args()
    homes={'12':'/home/csi2','10':'/home/csi'};bg={h:home+'/'+REMOTE+'/runs/'+a.run+'/'+a.mode+'_background' for h,home in homes.items()}
    args=argparse.Namespace(run=a.run,ip4='192.168.0.4',ip5='192.168.0.5',ssid=OTHER)
    pair=Pair(args,a.mode);c=pair.c;c.ip4='192.168.50.2'
    workers={};moved=False;old={};trials=[]
    try:
        if a.mode=='c2':
            c.connect(OTHER);ips=migrate(c,SR2,'to_sr2',a.run,'192.168.0.6');moved=True
            pair.ip=ips;pair.ssid=SR2
        else:
            c.connect(OTHER);trials.append(pair.trial('clean_otherAP_idle'))
            c.connect(SR2)
        checks=pair_check();(pair.out/'background_preflight.json').write_text(json.dumps(checks,indent=2))
        for h in homes:
            procs=remote(h,"import subprocess,json;q=subprocess.run(['pgrep','-af','[i]perf3|[t]raffic.py|[r]un_sweep|[r]un_campaign'],capture_output=True,text=True);print(json.dumps({'rc':q.returncode,'stdout':q.stdout}))")
            if procs['rc']!=1:raise RuntimeError('preserve active background laptop experiment')
            old[h]=remote(h,"import subprocess,json;print(json.dumps({k:int(subprocess.check_output(['sysctl','-n','net.core.'+k],text=True)) for k in ['rmem_max','wmem_max']}))")
            q=ssh(h,'sudo -n /sbin/sysctl -w net.core.rmem_max=1048576 net.core.wmem_max=1048576')
            if q.returncode:raise RuntimeError(q.stderr.decode())
        if a.mode=='b2':
            script='import sys;from pathlib import Path;p=Path('+repr(homes['12']+'/'+REMOTE+'/tools/w1_b2_worker.py')+');p.write_bytes(sys.stdin.buffer.read())'
            q=ssh('12','python3 -c '+shlex.quote(script),(ROOT/'tools/w1_b2_worker.py').read_bytes());assert q.returncode==0,q.stderr
            workers['server']=start('10',['timeout','-k','2','205','iperf3','-s','-B','192.168.0.4','-p','55461','-J'],bg['10'],'server.jsonl')
            workers['worker']=start('12',['timeout','-k','2','200','python3',homes['12']+'/'+REMOTE+'/tools/w1_b2_worker.py','--ssid',SR2,'--dev','wlo1','--bind','192.168.0.3','--peer','192.168.0.4','--port','55461','--seconds','175','--delay','20','--out',bg['12'],'--source-commit',subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()],bg['12'],'worker.log')
            tick=time.monotonic();anchor=remote('12',"import time,json;print(json.dumps({'wall_ns':time.time_ns(),'mono':time.monotonic()}))");ended=time.monotonic();anchor.update(pc_midpoint_s=(tick+ended)/2,roundtrip_s=ended-tick)
            (pair.out/'background_start.json').write_text(json.dumps({'workers':workers,'anchor':anchor},indent=2))
            c.connect(OTHER);time.sleep(13)
            for n in ['B2_1','B2_2','B2_3']:
                trials.append(pair.trial(n));(pair.out/'progress.json').write_text(json.dumps(trials,indent=2))
            c.connect(SR2)
            remote('12','from pathlib import Path;Path('+repr(bg['12']+'/stop')+').write_text("stop");print("{}")')
            for i in range(20):
                status=remote('12','import json;from pathlib import Path;print(json.dumps({"done":Path('+repr(bg['12']+'/summary.json')+').exists()}))')
                if status['done']:break
                time.sleep(.5)
            summary=json.loads(read('12',bg['12']+'/summary.json'))
            offset=anchor['pc_midpoint_s']-anchor['mono']
            for r in trials:
                r['successful_background_bursts_overlapping_call']=sum(b['start_monotonic_s']+offset<r['pc_call_end_s'] and b['end_monotonic_s']+offset>r['pc_call_start_s'] for b in summary['bursts'] if b.get('rc')==0 and not b.get('error'))
                r['overlap_qualification']='coarse SSH midpoint, not a qualified cross-host latency clock'
            (pair.out/'background_summary.json').write_text(json.dumps(summary,indent=2))
            (pair.out/'background_server.jsonl').write_text(read('10',bg['10']+'/server.jsonl'))
            if not any(b.get('rc')==0 and not b.get('error') for b in summary['bursts']):raise RuntimeError('no successful B2 bursts')
        else:
            for n in ['quiet1','quiet2','quiet3']:trials.append(pair.trial(n))
            capacity=statistics.median(r['receiver_bps'] for r in trials)
            for n in ['C2_1','C2_2','C2_3']:
                workers['server']=start('10',['timeout','-k','2','47','iperf3','-s','-1','-B','192.168.0.4','-p','55461','-J'],bg['10'],n+'_server.json')
                workers['client']=start('12',['timeout','-k','2','45','iperf3','-c','192.168.0.4','-B','192.168.0.3','-p','55461','-u','-b',str(round(.9*capacity)),'-l','1400','-w','1048576','-t','38','-J'],bg['12'],n+'_client.json')
                r=pair.trial(n);trials.append(r);time.sleep(3)
                client=json.loads(read('12',bg['12']+'/'+n+'_client.json'));server=json.loads(read('10',bg['10']+'/'+n+'_server.json'))
                if client.get('error') or server.get('error'):raise RuntimeError('C2 background failed')
                (pair.out/(n+'_background_client.json')).write_text(json.dumps(client,indent=2));(pair.out/(n+'_background_server.json')).write_text(json.dumps(server,indent=2))
                (pair.out/'progress.json').write_text(json.dumps(trials,indent=2))
        (pair.out/'summary.json').write_text(json.dumps({'trials':trials,'main_pair':pair.ip,'main_AP':pair.ssid,'background_pair':'12->10 on SR2','qualified_model_prediction':False,'reason':'self-load semantics rejected; raw observations retained'},indent=2))
    finally:
        c.connect(SR2)
        for h,key in [('12','worker'),('12','client'),('10','server')]:
            if key not in workers:continue
            pid=workers[key]['pid']
            remote(h,"import os,signal,json;from pathlib import Path;p=Path('/proc')/str("+str(pid)+")/'cmdline';r={'pid':"+str(pid)+",'already_exited':not p.exists()}\nif p.exists():\n cmd=p.read_bytes();assert b'55461' in cmd and (b'iperf3' in cmd or b'w1_b2_worker.py' in cmd);assert os.getpgid("+str(pid)+")=="+str(pid)+";os.killpg("+str(pid)+",signal.SIGTERM);r['signalled']=True\nprint(json.dumps(r))")
        for h,vals in old.items():
            q=ssh(h,'sudo -n /sbin/sysctl -w '+shlex.join(['net.core.'+k+'='+str(v) for k,v in vals.items()]));assert q.returncode==0,q.stderr
        if moved:
            c.ip5=pair.ip['5'];migrate(c,OTHER,'back_to_ax',a.run,'192.168.0.5')
        c.connect(SR2)


if __name__=='__main__':main()
