"""Run bounded W1 counter probes and restore power/CPU/sysctl in finally."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time
import statistics
from deploy import ROOT,REMOTE
from w1_b2 import Control


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--bind',default='192.168.0.11')
    p.add_argument('--stage',choices=['polling','semantics','calibration','training','validation','burst_validation','ack_reference','aggregation_training'],default='polling')
    p.add_argument('--capacity-mbps',type=float);p.add_argument('--ip4',default='192.168.0.4');p.add_argument('--ip5',default='192.168.0.5')
    p.add_argument('--management4');p.add_argument('--ssid',default='iptime5GAX1500');a=p.parse_args()
    if Path(a.run).name!=a.run:p.error('single folder name required')
    out=ROOT/'runs'/a.run/a.stage;out.mkdir(parents=True,exist_ok=False)
    c=Control(a.management4 or a.ip4,a.ip5,'Wi-Fi 2',out);c.bind=a.bind;ips={'4':a.ip4,'5':a.ip5}
    home={'4':'/home/csilab','5':'/home/csi'};base={h:home[h]+'/'+REMOTE+'/runs/'+a.run+'/'+a.stage for h in home}
    sessions=[];results=[]
    provenance={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'hashes':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['tools/w1_counter_worker.py','tools/w1_counter_campaign.py','tools/w1_session.py']}}
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2))
    def root(h,args):
        q=c.extra(h,shlex.join(['sudo','-n',*args]))
        if q.returncode:raise RuntimeError(q.stderr.decode())
        return json.loads(q.stdout)
    def fetch(h,file):
        q=c.extra(h,'cat '+shlex.quote(base[h]+'/'+file))
        if q.returncode:raise RuntimeError(q.stderr.decode())
        (out/(h+'_'+file)).write_bytes(q.stdout);return json.loads(q.stdout)
    try:
        for h in home:
            pre=c.python(h,"import subprocess,json;print(json.dumps({k:subprocess.run(v,capture_output=True,text=True,timeout=6).stdout for k,v in {'link':['iw','dev','wlp2s0','link'],'qdisc':['tc','-j','qdisc','show','dev','wlp2s0'],'workers':['pgrep','-af',r'[i]perf3|[r]un_sweep|[r]un_campaign|[t]raffic.py']}.items()}))")
            if 'SSID: '+a.ssid+'\n' not in pre['link'] or pre['workers'].strip():raise RuntimeError('unexpected association or active traffic')
            if any(x.get('root') and x['kind']!='noqueue' for x in json.loads(pre['qdisc'])):raise RuntimeError('preserve existing shaper')
            (out/('pre_'+h+'.json')).write_text(json.dumps(pre,indent=2))
            path=home[h]+'/'+REMOTE+'/tools/w1_counter_worker.py'
            q=c.extra(h,'python3 -c '+shlex.quote('import sys;from pathlib import Path;Path('+repr(path)+').write_bytes(sys.stdin.buffer.read())'),(ROOT/'tools/w1_counter_worker.py').read_bytes())
            if q.returncode:raise RuntimeError(q.stderr.decode())
            c.python(h,'from pathlib import Path;import json;Path('+repr(base[h])+').mkdir(parents=True,exist_ok=True);print("{}")')
            r=root(h,['python3',home[h]+'/'+REMOTE+'/tools/w1_session.py','begin','--folder',base[h]+'/session','--dev','wlp2s0']);sessions.append(h)
            (out/('session_begin_'+h+'.json')).write_text(json.dumps(r,indent=2))
            q=c.extra(h,'sudo -n sysctl -w net.core.rmem_max=1048576 net.core.wmem_max=1048576')
            if q.returncode:raise RuntimeError(q.stderr.decode())
        if a.stage=='polling':
            trials=[('idle',x,'4') for x in [.05,.2,1,0]]+[('relay',x,'4') for x in [0,.05,.2,1,2,.2]]+[('relay',.2,'5')]
        elif a.stage=='semantics':trials=[(mode,.2,'4') for mode in ['idle','ap_only','relay','ap_only','relay','idle']]
        elif a.stage=='calibration':trials=[('relay',.2,'4',0,30) for _ in range(3)]
        elif a.stage=='ack_reference':
            trials=[('idle',.2,'4',0,8)]+[('ap_only',.2,'4',rate,20) for rate in [100000000,200000000,300000000]]+[('idle',.2,'4',0,8)]
        else:
            if not a.capacity_mbps or a.capacity_mbps<=0:raise ValueError('positive measured capacity required')
            loads=[.8,.2,.6,.4] if a.stage=='training' else [.3,.7,.5,.3,.5,.7]
            if a.stage=='aggregation_training':
                trials=[('idle',.2,'4',0,8)]+[('relay',.2,'4',round(a.capacity_mbps*1e6*rho),20,pace) for pace in [1000,100000] for rho in [.2,.4,.6,.8]]+[('idle',.2,'4',0,8)]
            else:trials=[('idle',.2,'4',0,8)]+[('relay',.2,'4',round(a.capacity_mbps*1e6*rho),20) for rho in loads]+[('idle',.2,'4',0,8)]
        for i,entry in enumerate(trials):
            mode,interval,sender=entry[:3];rate,seconds=entry[3:5] if len(entry)>=5 else (100000000,8 if mode=='idle' else 10);pacing=entry[5] if len(entry)==6 else (100000 if a.stage=='burst_validation' else 1000)
            receiver='5' if sender=='4' else '4';name=f'{i:02d}_{mode}_p{interval}_tx{sender}_r{rate}'
            print('START '+name,flush=True)
            if mode=='relay':
                args=['timeout','-k','2',str(seconds+12),'iperf3','-s','-1','-B',ips[receiver],'-p','55479','-J']
                launch=c.python(receiver,"import subprocess,json;from pathlib import Path;p=Path("+repr(base[receiver])+");p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen("+repr(args)+",stdin=subprocess.DEVNULL,stdout=open(p/"+repr(name+'_server.json')+",'w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))")
                time.sleep(.3)
            args=['sudo','-n','timeout','-k','2',str(seconds+10),'python3',home[receiver]+'/'+REMOTE+'/tools/w1_counter_worker.py','--out',base[receiver]+'/'+name+'.json','--mode','observe','--seconds',str(seconds+4),'--interval',str(interval)]
            c.python(receiver,"import subprocess,json;from pathlib import Path;p=Path("+repr(base[receiver])+");p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen("+repr(args)+",stdin=subprocess.DEVNULL,stdout=open(p/"+repr(name+'.log')+",'w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))")
            peer='192.168.0.1' if mode=='ap_only' else ips[receiver]
            args=['timeout','-k','2',str(seconds+10),'python3',home[sender]+'/'+REMOTE+'/tools/w1_counter_worker.py','--out',base[sender]+'/'+name+'.json','--mode',mode,'--seconds',str(seconds),'--interval',str(interval),'--peer',peer,'--bind',ips[sender],'--rate',str(rate),'--pacing-us',str(pacing)]
            r=root(sender,args);time.sleep(3)
            raw={h:fetch(h,name+'.json') for h in home}
            rec={'name':name,'sender':sender,'mode':mode,'interval_s':interval,'requested_bps':rate,'seconds':seconds,'pacing_us':pacing,'worker':r,'receiver_Mbps':None}
            if mode=='relay':
                srv=fetch(receiver,name+'_server.json');rows=[s for x in srv.get('intervals',[]) for s in x.get('streams',[])]
                duration=sum(x['seconds'] for x in rows);rec['receiver_Mbps']=8*sum(x['bytes'] for x in rows)/duration/1e6 if duration else None
                rec['receiver_error']=srv.get('error')
            rec['deltas']={}
            for h in home:
                first,last=raw[h]['rows'][0]['counters'],raw[h]['rows'][-1]['counters']
                d={k:last[k]-first[k] for k in first if k in last and not k.endswith('bps')}
                rec['deltas'][h]=d
            results.append(rec);(out/'progress.json').write_text(json.dumps(results,indent=2))
            print(json.dumps({'DONE':name,'receiver_Mbps':rec['receiver_Mbps'],'deltas':{h:{k:v for k,v in d.items() if k in ['active_s','busy_s','tx_s','rx_s']} for h,d in rec['deltas'].items()}}),flush=True)
        summary={'trials':results,'provenance':provenance,'scope':'raw survey semantics; no latency qualification; no normal adaptive gate change'}
        if a.stage=='calibration':summary['C0_receiver_median_bps']=statistics.median(x['receiver_Mbps']*1e6 for x in results)
        (out/'summary.json').write_text(json.dumps(summary,indent=2))
    finally:
        restoration={}
        for h in reversed(sessions):
            try:restoration[h]=root(h,['python3',home[h]+'/'+REMOTE+'/tools/w1_session.py','end','--folder',base[h]+'/session','--dev','wlp2s0'])
            except Exception as e:restoration[h]={'error':str(e)}
        (out/'restoration.json').write_text(json.dumps(restoration,indent=2))
        print(json.dumps({'RESTORED':{h:r.get('restored',False) for h,r in restoration.items()}}),flush=True)


if __name__=='__main__':main()
