"""Prepare all workers before RF load; collect after finite background ends."""
import argparse
import hashlib
import json
import shlex
import time
from deploy import ROOT,REMOTE,ssh
from w1_b2 import OTHER,SR2
from w1_radio45 import Pair
from w1_conditions45 import migrate,remote,start,read


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['b2','c2']);p.add_argument('--run',required=True);p.add_argument('--capacity-mbps',type=float,required=True);p.add_argument('--label');p.add_argument('--skip-quiet',action='store_true');a=p.parse_args()
    pair=Pair(argparse.Namespace(run=a.run,ip4='192.168.0.4',ip5='192.168.0.5',ssid=OTHER),a.label or a.mode+'_scheduled');c=pair.c;c.ip4='192.168.50.2';moved=False;results=[];backgrounds=[]
    def anchor(h,bg=False):
        before=time.time_ns();value=(remote if bg else c.python)(h,'import time,json;print(json.dumps({"wall_ns":time.time_ns(),"mono_s":time.monotonic()}))');after=time.time_ns()
        return {'offset_ns':value['wall_ns']-(before+after)//2,'bound_ns':(after-before)//2,'remote':value}
    def write(h,path,data):
        q=c.extra(h,'python3 -c '+shlex.quote('import sys;from pathlib import Path;Path('+repr(path)+').write_bytes(sys.stdin.buffer.read())'),data)
        if q.returncode:raise RuntimeError(q.stderr.decode())
    def check_background():
        for h,dev in [('12','wlo1'),('10','wlp2s0')]:
            r=remote(h,"import subprocess,json;print(json.dumps({'link':subprocess.check_output(['iw','dev',"+repr(dev)+",'link'],text=True),'workers':subprocess.run(['pgrep','-af','[i]perf3|[w]1_background_udp.py|[r]un_sweep'],capture_output=True,text=True).stdout}))")
            if r['workers'].strip() or 'SSID: '+SR2+'\n' not in r['link']:raise RuntimeError('background pair must be idle on SR2')
    try:
        c.connect(OTHER)
        for h in pair.home:write(h,pair.home[h]+'/'+REMOTE+'/tools/w1_counter_worker.py',(ROOT/'tools/w1_counter_worker.py').read_bytes())
        if a.mode=='c2':
            ips=migrate(c,SR2,'to_sr2_scheduled',a.run,'192.168.0.6');moved=True;pair.ip=ips;pair.ssid=SR2
        for i in range(1 if a.skip_quiet else 0,4):
            name='quiet' if i==0 else a.mode.upper()+'scheduled_'+str(i);competing=i>0
            if a.mode=='b2':c.connect(OTHER)
            else:c.connect(SR2)
            pair.check()
            clocks={h:anchor(h) for h in ['4','5']};target=time.time_ns()+90_000_000_000;launched={};bgfolder={}
            print('SCHEDULE '+name+' (prepare before load)',flush=True)
            if competing:
                if a.mode=='b2':c.connect(SR2)
                check_background()
                for h in ['12','10']:clocks[h]=anchor(h,True)
                for h,home in [('12','/home/csi2'),('10','/home/csi')]:
                    path=home+'/'+REMOTE+'/tools/w1_background_udp.py'
                    q=ssh(h,'python3 -c '+shlex.quote('import sys;from pathlib import Path;Path('+repr(path)+').write_bytes(sys.stdin.buffer.read())'),(ROOT/'tools/w1_background_udp.py').read_bytes())
                    if q.returncode:raise RuntimeError(q.stderr.decode())
                    bgfolder[h]=home+'/'+REMOTE+'/runs/'+a.run+'/'+pair.out.name+'_background/'+name
                for h,role,bind,peer,offset,seconds in [('10','sink','192.168.0.4','192.168.0.3',2,37),('12','source','192.168.0.3','192.168.0.4',4,30)]:
                    argv=['timeout','-k','2','200','python3',('/home/csi2' if h=='12' else '/home/csi')+'/'+REMOTE+'/tools/w1_background_udp.py',role,'--bind',bind,'--peer',peer,'--out',bgfolder[h],'--seconds',str(seconds),'--start-wall-ns',str(target+offset*1_000_000_000+clocks[h]['offset_ns']),'--rate',str(round(.9*a.capacity_mbps*1e6) if a.mode=='c2' else 0),'--on-seconds',str(30 if a.mode=='c2' else 2),'--off-seconds',str(0 if a.mode=='c2' else 2)]
                    launched[h]=start(h,argv,bgfolder[h],'worker.log');backgrounds.append((h,bgfolder[h]))
                if a.mode=='b2':c.connect(OTHER)
            if time.time_ns()>target-5_000_000_000:raise RuntimeError('insufficient preparation margin; finite workers will expire')
            launched['server']=pair.launch('5',['timeout','-k','2','170','iperf3','-s','-1','-B',pair.ip['5'],'-p','55479','-J'],name+'_server.json')
            launched['observe']=pair.launch('5',['sudo','-n','timeout','-k','2','200','python3','tools/w1_counter_worker.py','--out',pair.base['5']+'/'+name+'.json','--mode','observe','--seconds','40','--interval','.2','--start-wall-ns',str(target-2_000_000_000+clocks['5']['offset_ns'])],name+'_observer.log')
            launched['main']=pair.launch('4',['sudo','-n','timeout','-k','2','200','python3','tools/w1_counter_worker.py','--out',pair.base['4']+'/'+name+'.json','--mode','relay','--seconds','30','--interval','.2','--peer',pair.ip['5'],'--bind',pair.ip['4'],'--rate','0','--start-wall-ns',str(target+clocks['4']['offset_ns'])],name+'_main.log')
            (pair.out/(name+'_launch.json')).write_text(json.dumps({'target_wall_ns_PC':target,'clock_mappings':clocks,'launches':launched,'capacity_for_background_Mbps':a.capacity_mbps},indent=2))
            while time.time_ns()<target+44_000_000_000:time.sleep(min(2,max(0,(target+44_000_000_000-time.time_ns())/1e9)))
            raw={h:json.loads(pair.fetch(h,name+'.json')) for h in pair.home};server=json.loads(pair.fetch('5',name+'_server.json'))
            pair.fetch('4',name+'_main.log');pair.fetch('5',name+'_observer.log')
            intervals=[r for row in server.get('intervals',[]) for r in row.get('streams',[])];steady=[r for r in intervals if r['start']>=3 and r['end']<=27]
            duration=sum(r['seconds'] for r in intervals);window=sum(r['seconds'] for r in steady);rc=raw['4']['traffic'].get('rc')
            result={'name':name,'sender':'4','mode':'relay','interval_s':.2,'requested_bps':0,'seconds':30,'receiver_Mbps':8*sum(r['bytes'] for r in steady)/window/1e6 if window else None,
                    'receiver_full_Mbps':8*sum(r['bytes'] for r in intervals)/duration/1e6 if duration else None,'receiver_duration_s':duration,'steady_window_s':window,'client_rc':rc,
                    'protocol_valid':rc==0 and 29.7<=duration<=30.5 and window>=22,'intentional_competition':competing,'server_error':server.get('error'),
                    'scope':'UDP1400B iperf30s, mean capacity in middle interval3..27s; counter analysis uses middle sender window; no PC commands during radio load'}
            if competing:
                if a.mode=='b2':c.connect(SR2)
                for h in ['12','10']:
                    data=json.loads(read(h,bgfolder[h]+'/summary.json'));(pair.out/(h+'_'+name+'_background.json')).write_text(json.dumps(data,indent=2));result['background_restored_'+h]=data['restoration']['restored']
                if a.mode=='b2':c.connect(OTHER)
            results.append(result);(pair.out/'progress.json').write_text(json.dumps(results,indent=2));print(json.dumps({'DONE':name,**result}),flush=True)
        (pair.out/'summary.json').write_text(json.dumps({'trials':results,'sources_sha256':{n:hashlib.sha256((ROOT/'tools'/n).read_bytes()).hexdigest() for n in ['w1_scheduled_radio.py','w1_counter_worker.py','w1_background_udp.py']},'main_ip':pair.ip,'normal_adaptive_qualified':False},indent=2))
    finally:
        c.connect(SR2)
        for h,folder in backgrounds:
            try:remote(h,'from pathlib import Path;Path('+repr(folder+'/stop')+').write_text("stop");print("{}")')
            except Exception:pass
        if moved:
            c.ip5=pair.ip['5'];migrate(c,OTHER,'back_to_ax_scheduled',a.run,'192.168.0.5')
        c.connect(OTHER)


if __name__=='__main__':main()
