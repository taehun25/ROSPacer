"""Physical200Mbps/burst check on the currently installed laptop4 kernel."""
import argparse
import json
import shlex
import time
from w1_radio45 import Pair
from w1_b2 import OTHER,SR2
from deploy import ROOT,REMOTE


def main():
    a=argparse.Namespace(run='w1_20261012_radio45',ip4='192.168.0.4',ip5='192.168.0.5',ssid=OTHER)
    pair=Pair(a,'wifi_probe');results=[]
    try:
        pair.c.connect(OTHER)
        source='import sys;from pathlib import Path;Path('+repr(pair.home['4']+'/'+REMOTE+'/tools/w1_wifi_shaper.py')+').write_bytes(sys.stdin.buffer.read())'
        q=pair.c.extra('4','python3 -c '+shlex.quote(source),(ROOT/'tools/w1_wifi_shaper.py').read_bytes());assert q.returncode==0,q.stderr
        for name,burst in [('baseline',None),('burst1500',1500),('burst65536',65536)]:
            print('PROBE '+name,flush=True);before=pair.check();started=time.monotonic()
            if burst:
                pair.launch('4',['sudo','-n','timeout','-k','3','22','python3','-m','tools.w1_wifi_shaper','--burst',str(burst),'--dev','wlp2s0','--peer',a.ip5,'--out',pair.base['4']+'/'+name+'_trace.jsonl'],name+'_shaper.log');time.sleep(.6)
            for h in pair.home:pair.launch(h,['sudo','-n','timeout','-k','2','24','python3','tools/telemetry.py','--dev','wlp2s0','--seconds','20','--interval','.2','--out',pair.base[h]+'/'+name+'_telemetry.jsonl'],name+'_telemetry.log')
            pair.launch('5',['timeout','-k','2','17','iperf3','-s','-1','-B',a.ip5,'-p','55311','-J'],name+'_server.json');time.sleep(.3)
            args=['iperf3','-c',a.ip5,'-B',a.ip4,'-p','55311','-u','-b','0','-l','1400','-w','1048576','-t','10','-J']
            client=pair.c.python('4','import subprocess,json,time;a=time.monotonic();q=subprocess.run('+repr(args)+',capture_output=True,text=True,timeout=15);print(json.dumps({"rc":q.returncode,"stdout":q.stdout,"stderr":q.stderr,"start_mono":a,"end_mono":time.monotonic()}))')
            (pair.out/(name+'_client.json')).write_text(json.dumps(client,indent=2))
            while time.monotonic()-started<25:time.sleep(1)
            server=json.loads(pair.fetch('5',name+'_server.json'));rows=[r for it in server.get('intervals',[]) for r in it.get('streams',[])];elapsed=sum(r['seconds'] for r in rows);bps=8*sum(r['bytes'] for r in rows)/elapsed if elapsed else None
            result={'name':name,'burst':burst,'receiver_Mbps':bps/1e6 if bps else None,'class_steady_Mbps':None,'fq_drop_max':None,'before':before,'scope':'10s UDP diagnostic; extra classification limited to port55311; RTPS classifier and DDS path separately verified'}
            for h in pair.home:pair.fetch(h,name+'_telemetry.jsonl');pair.fetch(h,name+'_telemetry.log')
            if burst:
                trace=[json.loads(s) for s in pair.fetch('4',name+'_trace.jsonl').splitlines()];pair.fetch('4',name+'_shaper.log');points=[];drops=[]
                for r in trace:
                    for cl in json.loads(r['class']):
                        if cl.get('handle')=='7ac0:10' and client['start_mono']+2<r['mono']<client['end_mono']-1:points.append((r['mono'],cl['bytes']))
                    drops.extend(q.get('drops',0) for q in json.loads(r['qdisc']) if q['kind']=='fq')
                if len(points)>1:result['class_steady_Mbps']=8*(points[-1][1]-points[0][1])/(points[-1][0]-points[0][0])/1e6
                result['fq_drop_max']=max(drops,default=0)
            result['qdisc_after']=pair.check()['4']['qdisc'];results.append(result);(pair.out/'summary.json').write_text(json.dumps(results,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ['before','qdisc_after']}),flush=True)
    finally:pair.c.connect(SR2)


if __name__=='__main__':main()
