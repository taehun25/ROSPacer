"""Same-link UDP baseline versus200Mbps HTB/fq, testing root attachment and bursts."""
import json,time
from pathlib import Path
from w1_calibrate import remote,launch,fetch
from deploy import ROOT,REMOTE

def main():
    base=ROOT/'runs/w1_20261012_163000';local=base/'wifi_probe';local.mkdir(exist_ok=True)
    dirs={h:'/home/'+('csi2' if h=='12' else 'csi')+'/'+REMOTE+'/runs/w1_20261012_163000/wifi_probe' for h in ['12','10']}
    for h,d in dirs.items():remote(h,'from pathlib import Path;Path('+repr(d)+').mkdir(parents=True,exist_ok=True);print("{}")')
    results=[]
    for name,burst in [('baseline',None),('burst1500',1500),('burst65536',65536)]:
        print('WIFI_PROBE '+name,flush=True);started=time.monotonic()
        if burst:
            launch('12',['sudo','-n','timeout','-k','3','22','python3','-m','tools.w1_wifi_shaper','--burst',str(burst),'--out',dirs['12']+'/'+name+'_trace.jsonl'],'/home/csi2/'+REMOTE,dirs['12']+'/'+name+'_shaper.log');time.sleep(.6)
        launch('10',['timeout','-k','2','16','iperf3','-s','-1','-B','192.168.0.4','-p','55311','-J'],'/home/csi/'+REMOTE,dirs['10']+'/'+name+'_server.json');time.sleep(.3)
        client=remote('12','import subprocess,json;from pathlib import Path\nq=subprocess.run(["iperf3","-c","192.168.0.4","-B","192.168.0.3","-p","55311","-u","-b","0","-l","1400","-t","10","-J"],capture_output=True,text=True,timeout=14);r={"rc":q.returncode,"stdout":q.stdout,"stderr":q.stderr};Path('+repr(dirs['12']+'/'+name+'_client.json')+').write_text(json.dumps(r));print(json.dumps(r))')
        (local/(name+'_client.json')).write_text(json.dumps(client,indent=2));time.sleep(max(0,18-(time.monotonic()-started)))
        server=fetch('10',dirs['10']+'/'+name+'_server.json');(local/(name+'_server.json')).write_text(server)
        if burst:
            for suffix in ['trace.jsonl','shaper.log']:(local/(name+'_'+suffix)).write_text(fetch('12',dirs['12']+'/'+name+'_'+suffix))
        obj=json.loads(server);streams=[r for it in obj['intervals'] for r in it['streams']];bytes_=sum(r['bytes'] for r in streams);seconds=sum(r['seconds'] for r in streams)
        qdisc=remote('12','import subprocess,json;print(json.dumps({"raw":subprocess.check_output(["tc","-j","qdisc","show","dev","wlo1"],text=True)}))')
        result={'name':name,'burst':burst,'C_receiver_Mbps':8*bytes_/seconds/1e6,'root_after':json.loads(qdisc['raw']),'HTB_cap_Mbps':200 if burst else None,
          'qualification':'This link is below200Mbps: assesses throughput loss from attachment/burst; does not establish an active200Mbps wireless ceiling'}
        results.append(result);(local/'summary.json').write_text(json.dumps(results,indent=2));print(json.dumps(result),flush=True)

if __name__=='__main__':main()
