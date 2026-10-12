"""Additional explicitly authorised SR2 pair for C2; strict saved host identities."""
import json,subprocess,argparse,shlex,time
from pathlib import Path, PurePosixPath
from deploy import ROOT,KEY

HOSTS={'4':('192.168.0.4','csilab@192.168.0.5'),'5':('192.168.0.5','csi@192.168.0.6')}

def ssh_extra(host,command,data=None):
    if host=='4':
        # Existing large-data harness authorises host5 -> host4. Preserve that
        # saved-key route rather than replacing keys or requesting a password.
        command=shlex.join(['ssh','-o','HostKeyAlias=192.168.0.4','-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ConnectTimeout=5','csilab@192.168.0.5',command])
        host='5'
    alias,account=HOSTS[host]
    return subprocess.run(['ssh','-b','192.168.0.2','-i',KEY,'-o','HostKeyAlias='+alias,'-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ConnectTimeout=5',account,command],input=data,capture_output=True,timeout=60)

def inventory():
    source=r'''
import subprocess,json
commands={'hostname':['hostnamectl'],'links':['iw','dev'],'addresses':['ip','-j','addr'],'qdisc':['tc','-j','qdisc','show'],'processes':['pgrep','-af',r'[r]un_sweep|[r]un_campaign|[i]perf3|[r]ospacer govern|[t]raffic.py'],'tools':['bash','-c','command -v iperf3; command -v iw'],'cpu':['cat','/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor']}
r={}
for k,v in commands.items():
 q=subprocess.run(v,capture_output=True,text=True,timeout=8);r[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
print(json.dumps(r))
'''
    result={}
    for h in HOSTS:
        q=ssh_extra(h,'python3 -',source.encode())
        result[h]={'rc':q.returncode,'report':json.loads(q.stdout) if q.returncode==0 else None,'stderr':q.stderr.decode()}
    base=ROOT/'runs/w1_20261012_163000';(base/'competition_inventory.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({h:{'rc':r['rc'],'identity':r['report']['hostname']['stdout'] if r['report'] else None,'processes':r['report']['processes'] if r['report'] else None,'stderr':r['stderr']} for h,r in result.items()},indent=2))

def remote_extra(host,source):
    q=ssh_extra(host,'python3 -',source.encode())
    if q.returncode:raise RuntimeError(q.stderr.decode())
    return json.loads(q.stdout)

def launch_extra(host,argv,log):
    source='import subprocess,json;from pathlib import Path\np=Path.home()/"ros2_ws/src/large_data_1009/ROSPacer/runs/w1_20261012_163000/competition";p.mkdir(parents=True,exist_ok=True)\nf=open(p/'+repr(log)+',"w");q=subprocess.Popen('+repr(argv)+',stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({"pid":q.pid,"path":str(p)}))'
    return remote_extra(host,source)

def competition():
    from w1_calibrate import remote,launch,fetch
    from deploy import REMOTE
    base=ROOT/'runs/w1_20261012_163000';out=base/'competition';out.mkdir(exist_ok=True)
    C0=json.loads((base/'calibration_ready/summary.json').read_text())['C0_UDP_receiver_median_bps']
    # Repeat clean-link UDP after the two additional stations joined, then C2.
    results=[]
    for trial in ['clean4stations','C2_1','C2_2','C2_3']:
        check=json.loads((base/'competition_inventory.json').read_text())
        if any(v['rc'] or v['report']['processes']['rc']!=1 for v in check.values()):raise RuntimeError('additional pair not idle')
        print('START '+trial,flush=True)
        extra=[]
        if trial!='clean4stations':
            extra.append(launch_extra('4',['timeout','-k','2','44','iperf3','-s','-1','-B','192.168.0.5','-p','55301','-J'],trial+'_server.json'))
            time.sleep(.4)
            extra.append(launch_extra('5',['timeout','-k','2','42','iperf3','-c','192.168.0.5','-B','192.168.0.6','-p','55301','-u','-b',str(round(.9*C0)),'-l','1400','-t','38','-J'],trial+'_client.json'))
        bases={h:'/home/'+('csi2' if h=='12' else 'csi')+'/'+REMOTE+'/runs/w1_20261012_163000/competition' for h in ['12','10']}
        for h in bases:
            remote(h,'from pathlib import Path;Path('+repr(bases[h])+').mkdir(parents=True,exist_ok=True);print("{}")')
            argv=['timeout','-k','2','43','python3','tools/telemetry.py','--dev','wlo1' if h=='12' else 'wlp2s0','--seconds','38','--interval','.5','--out',bases[h]+'/'+trial+'_telemetry.jsonl']
            if h=='12':argv=['sudo','-n']+argv
            launch(h,argv,str(PurePosixPath(bases[h]).parents[2]),bases[h]+'/'+trial+'_telemetry.log')
        launch('10',['timeout','-k','2','39','iperf3','-s','-1','-B','192.168.0.4','-p','55302','-J'],str(PurePosixPath(bases['10']).parents[2]),bases['10']+'/'+trial+'_server.json');time.sleep(.5)
        client=remote('12','import subprocess,json;from pathlib import Path\nq=subprocess.run(["iperf3","-c","192.168.0.4","-B","192.168.0.3","-p","55302","-u","-b","0","-l","1400","-t","30","-J"],capture_output=True,text=True,timeout=36);r={"rc":q.returncode,"stdout":q.stdout,"stderr":q.stderr};Path('+repr(bases['12']+'/'+trial+'_client.json')+').write_text(json.dumps(r));print(json.dumps(r))')
        (out/(trial+'_12_client.json')).write_text(json.dumps(client,indent=2))
        time.sleep(9)
        for h in bases:
            for suffix in ['telemetry.jsonl','telemetry.log']:(out/(trial+'_'+h+'_'+suffix)).write_text(fetch(h,bases[h]+'/'+trial+'_'+suffix),encoding='utf-8')
        server=fetch('10',bases['10']+'/'+trial+'_server.json');(out/(trial+'_10_server.json')).write_text(server)
        srv=json.loads(server);streams=[r for interval in srv['intervals'] for r in interval['streams']];bytes_=sum(r['bytes'] for r in streams);seconds=sum(r['seconds'] for r in streams)
        result={'trial':trial,'receiver_bps':8*bytes_/seconds,'contender_requested_bps':.9*C0 if extra else 0,'controller_wifi_management':True,
          'adaptive_estimate':None,'estimate_error':None,'reason':'No survey airtime counters; throughput response only, no20percent model validation'}
        if extra:
            for h,suffix in [('4','server'),('5','client')]:
                raw=remote_extra(h,'import json;from pathlib import Path\np=Path.home()/"ros2_ws/src/large_data_1009/ROSPacer/runs/w1_20261012_163000/competition";print(json.dumps({"text":(p/'+repr(trial+'_'+suffix+'.json')+').read_text()}))')['text']
                (out/(trial+'_'+h+'_'+suffix+'.json')).write_text(raw)
            contender=json.loads((out/(trial+'_5_client.json')).read_text());result['contender_client_end']=contender.get('end');result['contender_error']=contender.get('error')
        results.append(result);(out/'summary.json').write_text(json.dumps(results,indent=2));print(json.dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--measure',action='store_true');a=p.parse_args()
    competition() if a.measure else inventory()
