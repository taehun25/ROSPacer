"""Same-link UDP baseline versus200Mbps HTB/fq, testing root attachment and bursts."""
import argparse,json,time,shlex
from pathlib import Path
from w1_calibrate import remote,launch,fetch
from deploy import ROOT,REMOTE,ssh

def measure(run,socket_bytes):
    base=ROOT/'runs'/run;local=base/'wifi_probe';local.mkdir(exist_ok=False)
    dirs={h:'/home/'+('csi2' if h=='12' else 'csi')+'/'+REMOTE+'/runs/'+run+'/wifi_probe' for h in ['12','10']}
    for h,d in dirs.items():remote(h,'from pathlib import Path;Path('+repr(d)+').mkdir(parents=True,exist_ok=True);print("{}")')
    results=[]
    for name,burst in [('baseline',None),('burst1500',1500),('burst65536',65536)]:
        print('WIFI_PROBE '+name,flush=True);started=time.monotonic()
        if burst:
            launch('12',['sudo','-n','timeout','-k','3','22','python3','-m','tools.w1_wifi_shaper','--burst',str(burst),'--out',dirs['12']+'/'+name+'_trace.jsonl'],'/home/csi2/'+REMOTE,dirs['12']+'/'+name+'_shaper.log');time.sleep(.6)
        launch('10',['timeout','-k','2','16','iperf3','-s','-1','-B','192.168.0.4','-p','55311','-J'],'/home/csi/'+REMOTE,dirs['10']+'/'+name+'_server.json');time.sleep(.3)
        argv=['iperf3','-c','192.168.0.4','-B','192.168.0.3','-p','55311','-u','-b','0','-l','1400','-t','10','-J']
        if socket_bytes:argv+=['-w',str(socket_bytes)]
        client=remote('12','import subprocess,json;from pathlib import Path\nq=subprocess.run('+repr(argv)+',capture_output=True,text=True,timeout=14);r={"rc":q.returncode,"stdout":q.stdout,"stderr":q.stderr};Path('+repr(dirs['12']+'/'+name+'_client.json')+').write_text(json.dumps(r));print(json.dumps(r))')
        (local/(name+'_client.json')).write_text(json.dumps(client,indent=2));time.sleep(max(0,18-(time.monotonic()-started)))
        server=fetch('10',dirs['10']+'/'+name+'_server.json');(local/(name+'_server.json')).write_text(server)
        if burst:
            for suffix in ['trace.jsonl','shaper.log']:(local/(name+'_'+suffix)).write_text(fetch('12',dirs['12']+'/'+name+'_'+suffix))
        obj=json.loads(server);streams=[r for it in obj['intervals'] for r in it['streams']];bytes_=sum(r['bytes'] for r in streams);seconds=sum(r['seconds'] for r in streams)
        qdisc=remote('12','import subprocess,json;print(json.dumps({"raw":subprocess.check_output(["tc","-j","qdisc","show","dev","wlo1"],text=True)}))')
        rate=None;drop=None
        if burst:
            points=[];drops=[]
            for line in (local/(name+'_trace.jsonl')).read_text().splitlines():
                row=json.loads(line)
                for c in json.loads(row['class']):
                    if c.get('handle')=='7ac0:10':points.append((row['mono'],c['bytes']))
                drops += [q.get('drops',0) for q in json.loads(row['qdisc']) if q.get('kind')=='fq']
            active=[p for i,p in enumerate(points) if i and p[1]>points[i-1][1]]
            steady=[p for p in points if active and active[0][0]+2<=p[0]<=active[-1][0]-1]
            if len(steady)>1:rate=8*(steady[-1][1]-steady[0][1])/(steady[-1][0]-steady[0][0])/1e6
            drop=max(drops,default=0)
        result={'name':name,'burst':burst,'C_receiver_Mbps':8*bytes_/seconds/1e6,'root_after':json.loads(qdisc['raw']),'HTB_cap_Mbps':200 if burst else None,
          'class_steady_Mbps':rate,'fq_drop_max':drop,'socket_bytes_requested':socket_bytes,
          'qualification':'10second physical WiFi diagnostic; packet-byte ceiling and UDP payload goodput differ; not DDS backpressure or statistical throughput guarantee'}
        results.append(result);(local/'summary.json').write_text(json.dumps(results,indent=2));print(json.dumps(result),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',default='w1_20261012_163000');p.add_argument('--socket-bytes',type=int);a=p.parse_args()
    if Path(a.run).name!=a.run:p.error('single folder name required')
    if a.socket_bytes and a.socket_bytes not in [1048576]:p.error('reviewed1MiB diagnostic only')
    old={}
    if a.socket_bytes:
        for h in ['12','10']:old[h]=remote(h,"import subprocess,json;print(json.dumps({k:int(subprocess.check_output(['sysctl','-n',k],text=True)) for k in ['net.core.rmem_max','net.core.wmem_max']}))")
    try:
        for h in old:
            q=ssh(h,shlex.join(['sudo','-n','/sbin/sysctl','-w','net.core.rmem_max=1048576','net.core.wmem_max=1048576']))
            if q.returncode:raise RuntimeError(q.stderr.decode())
        measure(a.run,a.socket_bytes)
    finally:
        result={}
        for h,values in old.items():
            q=ssh(h,shlex.join(['sudo','-n','/sbin/sysctl','-w']+[k+'='+str(v) for k,v in values.items()]))
            result[h]={'rc':q.returncode,'stderr':q.stderr.decode()}
        if old:
            (ROOT/'runs'/a.run/'wifi_probe_buffers_restoration.json').write_text(json.dumps({'original':old,'result':result},indent=2))
            if any(r['rc'] for r in result.values()):raise RuntimeError('buffer restore failed')

if __name__=='__main__':main()
