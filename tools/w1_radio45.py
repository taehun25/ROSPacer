"""Bounded W1 radio calibration on the counter-capable 4/5 pair.

Uses the existing SSH identities and AP profiles. Traffic is explicitly bound
to WiFi IPs. All remote workers have independent timeouts. Power/sysctl session
guards must be prepared before calling this controller.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import statistics
import subprocess
import time

from deploy import ROOT, REMOTE
from w1_b2 import Control, OTHER, SR2


class Pair:
    def __init__(self, args, label):
        self.out = ROOT/'runs'/args.run/label
        self.out.mkdir(parents=True, exist_ok=False)
        self.c = Control(args.ip4,args.ip5,'Wi-Fi 2',self.out)
        self.ip = {'4':args.ip4,'5':args.ip5}
        self.home = {'4':'/home/csilab','5':'/home/csi'}
        self.base = {h:self.home[h]+'/'+REMOTE+'/runs/'+args.run+'/'+label for h in self.home}
        self.ssid = args.ssid
        provenance = {'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                      'source_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
                       ['tools/w1_radio45.py','tools/w1_b2.py','tools/telemetry.py','rospacer/linux.py','rospacer/model.py']}}
        (self.out/'provenance.json').write_text(json.dumps(provenance,indent=2))

    def check(self):
        reports = {}
        for h in self.home:
            r = self.c.python(h,"import subprocess,json;from pathlib import Path\nr={}\nfor k,a in {'link':['iw','dev','wlp2s0','link'],'info':['iw','dev','wlp2s0','info'],'qdisc':['tc','-j','qdisc','show','dev','wlp2s0'],'clock':['chronyc','-n','tracking'],'clock_sources':['chronyc','-n','sources']}.items():\n q=subprocess.run(a,capture_output=True,text=True,timeout=8);r[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}\nprint(json.dumps(r))")
            if 'SSID: '+self.ssid+'\n' not in r['link']['stdout'] or 'channel 149 ' not in r['info']['stdout']:
                raise ValueError('unexpected WiFi association')
            if any(q.get('root') and q['kind']!='noqueue' for q in json.loads(r['qdisc']['stdout'])):
                raise ValueError('unexpected shaper')
            reports[h] = r
        return reports

    def launch(self,h,args,log):
        return self.c.python(h,"import subprocess,json;from pathlib import Path;p=Path("+repr(self.base[h])+");p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen("+repr(args)+",cwd="+repr(self.home[h]+'/'+REMOTE)+",stdin=subprocess.DEVNULL,stdout=open(p/"+repr(log)+",'w'),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({'pid':q.pid}))")

    def fetch(self,h,name):
        q = self.c.extra(h,'cat '+shlex.quote(self.base[h]+'/'+name))
        if q.returncode:
            raise RuntimeError(q.stderr.decode())
        raw = q.stdout.decode()
        (self.out/(h+'_'+name)).write_text(raw,encoding='utf-8')
        return raw

    def trial(self,name,seconds=30,rate=None,udp=True):
        print('START '+name,flush=True)
        before = self.check()
        launches = {}
        for h in self.home:
            launches[h] = self.launch(h,['sudo','-n','timeout','-k','2',str(seconds+9),'python3','tools/telemetry.py',
                '--dev','wlp2s0','--seconds',str(seconds+5),'--interval','.2','--out',self.base[h]+'/'+name+'_telemetry.jsonl'],name+'_telemetry.log')
        server = self.launch('5',['timeout','-k','2',str(seconds+8),'iperf3','-s','-1','-B',self.ip['5'],'-p','55460','-J'],name+'_server.json')
        time.sleep(.5)
        args = ['iperf3','-c',self.ip['5'],'-B',self.ip['4'],'-p','55460','-t',str(seconds),'-w','1048576','-J']
        if udp:
            args += ['-u','-b',str(rate or 0),'-l','1400']
        result = self.c.python('4',"import subprocess,json,time\na=time.monotonic();q=subprocess.run("+repr(args)+",capture_output=True,text=True,timeout="+str(seconds+6)+");print(json.dumps({'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr,'start_mono':a,'end_mono':time.monotonic()}))")
        (self.out/(name+'_client.json')).write_text(json.dumps(result,indent=2))
        time.sleep(6)
        telemetry = {}
        for h in self.home:
            telemetry[h] = [json.loads(s) for s in self.fetch(h,name+'_telemetry.jsonl').splitlines()]
            self.fetch(h,name+'_telemetry.log')
        srv = json.loads(self.fetch('5',name+'_server.json'))
        cli = json.loads(result['stdout']) if result['stdout'].strip() else {}
        intervals = [row for interval in srv.get('intervals',[]) for row in interval.get('streams',[]) if 'bytes' in row]
        elapsed = sum(r['seconds'] for r in intervals)
        bytes_received = sum(r['bytes'] for r in intervals)
        summary = {'name':name,'udp':udp,'requested_bps':rate,'client_rc':result['rc'],
                   'client_error':cli.get('error'),'server_error':srv.get('error'),
                   'receiver_interval_bytes':bytes_received,'receiver_interval_seconds':elapsed,
                   'receiver_bps':8*bytes_received/elapsed if elapsed else None,'before':before,
                   'telemetry_launches':launches,'server_launch':server,
                   'loss_percent':srv.get('end',{}).get('sum',{}).get('lost_percent'),
                   'clock_latency_qualified':False,'scope':'radio calibration only; not DDS end-to-end latency'}
        for h in self.home:
            rows = telemetry[h]
            if rows:
                summary['udp_error_delta_'+h] = {k:rows[-1]['udp_global'].get(k,0)-rows[0]['udp_global'].get(k,0) for k in ['RcvbufErrors','SndbufErrors','InErrors']}
        (self.out/(name+'_summary.json')).write_text(json.dumps(summary,indent=2))
        print(json.dumps({'DONE':name,'receiver_Mbps':summary['receiver_bps']/1e6 if summary['receiver_bps'] else None,'errors':summary.get('udp_error_delta_5'),'client_rc':result['rc']}),flush=True)
        return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['calibrate','selfload'])
    p.add_argument('--run',required=True)
    p.add_argument('--ip4',default='192.168.0.4')
    p.add_argument('--ip5',default='192.168.0.5')
    p.add_argument('--ssid',default=OTHER)
    p.add_argument('--capacity-bps',type=float)
    a = p.parse_args()
    if Path(a.run).name != a.run:
        p.error('single run folder required')
    if a.mode=='selfload' and not (a.capacity_bps and a.capacity_bps>0):
        p.error('measured capacity required')
    pair = Pair(a,'calibration' if a.mode=='calibrate' else 'selfload')
    results = []
    try:
        pair.c.connect(a.ssid)
        if a.mode=='calibrate':
            for name,udp in [('udp1',True),('udp2',True),('udp3',True),('tcp',False)]:
                results.append(pair.trial(name,udp=udp))
                (pair.out/'progress.json').write_text(json.dumps(results,indent=2))
            ping = pair.c.python('4',"import subprocess,json;q=subprocess.run(['ping','-n','-I',"+repr(a.ip4)+",'-c','200','-i','.05','-W','1',"+repr(a.ip5)+"],capture_output=True,text=True,timeout=35);print(json.dumps({'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}))")
            (pair.out/'ping.json').write_text(json.dumps(ping,indent=2))
            rates = [r['receiver_bps'] for r in results[:3] if r['receiver_bps']]
            summary = {'trials':results,'C0_receiver_median_bps':statistics.median(rates) if len(rates)==3 else None,
                       'definition':'UDP1400-byte payload,30s x3,explicit1MiB sockets; no intentional other traffic','socket_bytes':1048576}
        else:
            for rho in [.2,.4,.6,.8]:
                results.append(pair.trial('rho'+str(rho),seconds=15,rate=round(a.capacity_bps*rho)))
                (pair.out/'progress.json').write_text(json.dumps(results,indent=2))
            summary = {'trials':results,'calibration_C0_bps':a.capacity_bps,'purpose':'busy self-TX inclusion and AP relay residual; analyse unclipped residuals, not just clipped beta'}
        (pair.out/'summary.json').write_text(json.dumps(summary,indent=2))
        print(json.dumps({'SUMMARY':summary.get('C0_receiver_median_bps'),'trials':len(results)}),flush=True)
    finally:
        pair.c.connect(SR2)


if __name__=='__main__':
    main()
