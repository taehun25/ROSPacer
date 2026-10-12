"""Proposal's quiet-link UDP 30s x3, TCP 30s and ping 200 on SR2 only."""
import argparse,json,shlex,time,statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from deploy import ROOT,REMOTE,ssh

def remote(host,code):
    q=ssh(host,'python3 -',code.encode())
    if q.returncode:raise RuntimeError(q.stderr.decode()+' '+q.stdout.decode())
    return json.loads(q.stdout)

def fetch(host,path):
    q=ssh(host,'cat '+shlex.quote(str(path)))
    if q.returncode:raise RuntimeError(q.stderr.decode())
    return q.stdout.decode()

def launch(host,argv,cwd,log):
    return remote(host,'import subprocess,json\np=subprocess.Popen('+repr(argv)+',cwd='+repr(cwd)+',stdin=subprocess.DEVNULL,stdout=open('+repr(log)+',"w"),stderr=subprocess.STDOUT,start_new_session=True)\nprint(json.dumps({"pid":p.pid}))')

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--label',default='calibration_ready');a=p.parse_args()
    local=ROOT/'runs'/a.run/a.label;local.mkdir(parents=True,exist_ok=True)
    homes={'12':'/home/csi2','10':'/home/csi'}
    bases={h:homes[h]+'/'+REMOTE+'/runs/'+a.run+'/'+a.label for h in homes}
    for h,b in bases.items():remote(h,'from pathlib import Path;import json;Path('+repr(b)+').mkdir(parents=True,exist_ok=True);print("{}")')
    trials=[]
    for name,udp in [('udp1',True),('udp2',True),('udp3',True),('tcp',False)]:
        print('START '+name,flush=True)
        trial={'name':name}
        for h,dev in [('12','wlo1'),('10','wlp2s0')]:
            b=bases[h]
            argv=['timeout','-k','3','42','python3','tools/telemetry.py','--dev',dev,'--seconds','37','--interval','0.5','--out',b+'/'+name+'_telemetry.jsonl']
            if h=='12':argv=['sudo','-n']+argv
            trial['telemetry_pid'+h]=launch(h,argv,homes[h]+'/'+REMOTE,b+'/'+name+'_telemetry.log')['pid']
        b=bases['10'];trial['server_pid']=launch('10',['timeout','-k','3','40','iperf3','-s','-1','-B','192.168.0.4','-p','55231','-J'],homes['10']+'/'+REMOTE,b+'/'+name+'_server.json')['pid']
        time.sleep(.5)
        argv=['iperf3','-c','192.168.0.4','-B','192.168.0.3','-p','55231','-t','30','-J']
        if udp:argv+=['-u','-b','0','-l','1400']
        result=remote('12','import subprocess,json,time\nq=subprocess.run('+repr(argv)+',capture_output=True,text=True,timeout=36)\nfrom pathlib import Path\nr={"rc":q.returncode,"stdout":q.stdout,"stderr":q.stderr};Path('+repr(bases['12']+'/'+name+'_client.json')+').write_text(json.dumps(r));print(json.dumps(r))')
        (local/(name+'_client.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
        trial['client_rc']=result['rc']
        time.sleep(7)
        for h in homes:
            for suffix in ['telemetry.jsonl','telemetry.log']:
                (local/(name+'_'+h+'_'+suffix)).write_text(fetch(h,bases[h]+'/'+name+'_'+suffix),encoding='utf-8')
        server=fetch('10',bases['10']+'/'+name+'_server.json');(local/(name+'_server.json')).write_text(server,encoding='utf-8')
        try:
            client=json.loads(result['stdout']);srv=json.loads(server)
            if udp:
                intervals=srv.get('intervals',[])
                streams=[item for interval in intervals for item in interval.get('streams',[]) if 'bytes' in item]
                # Some installed iperf3 server end summaries incorrectly report zero.
                total=sum(row['bytes'] for row in streams);seconds=sum(row['seconds'] for row in streams)
                trial.update(receiver_interval_bytes=total,receiver_interval_seconds=seconds,receiver_bps=8*total/seconds if seconds else None,
                  receiver_end=srv.get('end'),client_end=client.get('end'))
            else:trial['receiver_bps']=client['end']['sum_received']['bits_per_second']
        except Exception as e:trial['parse_error']=str(e)
        trials.append(trial);(local/'progress.json').write_text(json.dumps(trials,indent=2))
        print(json.dumps({'DONE':name,'receiver_bps':trial.get('receiver_bps'),'client_rc':result['rc']}),flush=True)
    ping=remote('12','import subprocess,json\nq=subprocess.run(["ping","-n","-I","192.168.0.3","-c","200","-i","0.05","-W","1","192.168.0.4"],capture_output=True,text=True,timeout=35)\nprint(json.dumps({"rc":q.returncode,"stdout":q.stdout,"stderr":q.stderr}))')
    (local/'ping.json').write_text(json.dumps(ping,indent=2))
    rates=[t['receiver_bps'] for t in trials[:3] if t.get('receiver_bps')]
    summary={'trials':trials,'ping':ping,'C0_UDP_receiver_median_bps':statistics.median(rates) if len(rates)==3 else None,
      'C0_definition':'median of three receiver interval-byte rates; iperf3 UDP 1400B/30s; includes loss; application UDP payload, not DDS goodput',
      'quiet_link_control':'No intentional interference; survey missing so external occupancy not verified','adaptive_calibration_complete':False}
    (local/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
