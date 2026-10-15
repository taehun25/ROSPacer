"""Sender-local finite W1 comparator harness, not a receiver telemetry agent.

Receiver runs its pre-existing ROS smoke subscriber. Bench-only SSH is used to
launch/read the measurement, never inside sender-govern. Production ROSPacer
does not require this harness or the benchmark key.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shlex
import subprocess
import sys
import time
import os
import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rospacer import profiles
from rospacer.metrics import analyze_pair


def main():
    p = argparse.ArgumentParser(); p.add_argument('--bundle', required=True); p.add_argument('--out', required=True)
    p.add_argument('--validation', action='append', required=True); p.add_argument('--rmw', choices=['fastdds','cyclonedds','both'], required=True)
    p.add_argument('--key', required=True); p.add_argument('--condition', required=True); p.add_argument('--seconds', type=int, default=15)
    p.add_argument('--reps', type=int, default=2); p.add_argument('--mode', choices=['static','fixed','adaptive'])
    a = p.parse_args()
    if a.rmw == 'both':
        for rmw in ['fastdds','cyclonedds']:
            argv=[sys.executable,str(Path(__file__).resolve()),'--bundle',a.bundle,'--out',str(Path(a.out)/rmw),
                  '--rmw',rmw,'--key',a.key,'--condition',a.condition,'--seconds',str(a.seconds),'--reps',str(a.reps)]
            for v in a.validation:argv+=['--validation',v]
            if a.mode:argv+=['--mode',a.mode]
            subprocess.run(argv,check=True)
        return
    bundle = Path(a.bundle); folder = Path(a.out); folder.mkdir(parents=True, exist_ok=False)
    cfg = json.loads((bundle/'governor.json').read_text()); cfg['middleware'] = a.rmw
    peer_base = Path('/home/csi/ros2_ws/src/large_data_1009/ROSPacer'); base = Path(__file__).resolve().parents[1]
    ssh = ['ssh','-6','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','HostKeyAlias=192.168.0.5',
           '-o','UserKnownHostsFile=/home/csilab/.ssh/rospacer_cal_known_hosts','-o','IPQoS=none','-o','ConnectTimeout=5',
           '-o','IdentitiesOnly=yes','-i',a.key,'csi@fe80::4f91:cec0:78f5:cc75%wlp2s0']
    def remote(command, data=None, timeout=15):
        q = subprocess.run(ssh+[command], input=data, capture_output=True, timeout=timeout)
        if q.returncode: raise RuntimeError(q.stderr.decode())
        return q.stdout
    planned = math.ceil(30*a.seconds); results = []
    orders = [['static','adaptive','fixed'],['fixed','adaptive','static']]
    manifest = dict(sender_host=os.uname().nodename, calibration_host=json.loads((bundle/'manifest.json').read_text())['calculation_host'],
                    profile_sha256=hashlib.sha256((bundle/'profile.json').read_bytes()).hexdigest(), seconds=a.seconds, hz=30,
                    planned=planned, payload=1048576, rmw=a.rmw, condition=a.condition, reps=a.reps,
                    comparison_order=orders, receiver_program='pre-existing tools/traffic.py measurement subscriber',
                    operational_receiver_feedback=False, finite_W1_smoke=True, formal_W2_performance=False)
    (folder/'protocol.json').write_text(json.dumps(manifest, indent=2))
    for rep in range(a.reps):
        for mode in ([a.mode] if a.mode else orders[rep%2]):
            name=f'{a.rmw}_{mode}_r{rep+1}'; out=folder/name; out.mkdir(); rx=peer_base/'runs'/folder.relative_to(base/'runs')/name
            roots=json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev','wlp2s0']))
            if not all(q['kind']=='noqueue' for q in roots): raise RuntimeError('unexpected sender shaper')
            remote('mkdir -p '+shlex.quote(str(rx)))
            for endpoint, address in [('pub','192.168.0.4'),('sub','192.168.0.5')]:
                xml=out/(endpoint+'.xml')
                if a.rmw=='fastdds': profiles.fastdds(cfg,xml,address)
                else: profiles.cyclone(cfg,xml,'wlp2s0',['192.168.0.5'] if endpoint=='pub' else ['192.168.0.4'])
            remote('cat > '+shlex.quote(str(rx/'middleware.xml')), (out/'sub.xml').read_bytes())
            def command(role):
                home=base if role=='pub' else peer_base; target=out if role=='pub' else rx
                xml=out/'pub.xml' if role=='pub' else rx/'middleware.xml'
                env='source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; '
                env+='unset CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML FASTDDS_BUILTIN_TRANSPORTS; '
                env+='export ROS_DOMAIN_ID=76 RMW_IMPLEMENTATION='+('rmw_fastrtps_cpp' if a.rmw=='fastdds' else 'rmw_cyclonedds_cpp')+'; '
                env+='export LD_LIBRARY_PATH='+str(home/'runtime_w1_45'/a.rmw)+':$LD_LIBRARY_PATH; '
                if a.rmw=='fastdds': env+='export FASTRTPS_DEFAULT_PROFILES_FILE='+str(xml)+' RMW_FASTRTPS_USE_QOS_FROM_XML=1; '
                else: env+='export CYCLONEDDS_URI=file://'+str(xml)+'; '
                args=['timeout','-k','2',str(a.seconds+20),'python3','tools/traffic.py',role,'--seconds',str(a.seconds if role=='pub' else a.seconds+13),
                      '--hz','30','--count',str(planned),'--out',str(target/(role+'.json'))]
                if role=='pub': args+=['--discovery-seconds','8','--drain-seconds','3','--continue-on-publish-error']
                return env+'cd '+shlex.quote(str(home))+'; exec '+shlex.join(args)
            observer = None
            if mode!='static':
                argv=['python3','-m','rospacer','sender-govern','--bundle',str(bundle),'--out',str(out/'govern'),
                      '--mode',mode,'--seconds',str(a.seconds+15)]
                for v in a.validation: argv+=['--validation',v]
                observer=subprocess.Popen(argv,cwd=base,stdout=open(out/'govern.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
                time.sleep(.8)
                if observer.poll() is not None: raise RuntimeError('governor startup failed')
            subscriber=subprocess.Popen(ssh+[shlex.join(['bash','-c',command('sub')])],stdout=open(out/'sub.log','w'),stderr=subprocess.STDOUT,start_new_session=True)
            time.sleep(.7)
            print('START '+a.condition+' '+name,flush=True)
            try:
                pub=subprocess.run(['bash','-c',command('pub')],cwd=base,stdout=open(out/'pub.log','w'),stderr=subprocess.STDOUT,timeout=a.seconds+25)
                subscriber.wait(timeout=a.seconds+20)
                if observer: observer.wait(timeout=a.seconds+20)
            finally:
                for q in (subscriber,observer):
                    if q and q.poll() is None:
                        os.killpg(q.pid,signal.SIGTERM);q.wait(timeout=5)
            for suffix in ['json','metadata.json','events.jsonl']:
                (out/('sub.'+suffix)).write_bytes(remote('cat '+shlex.quote(str(rx/('sub.'+suffix)))))
            pub_data=json.loads((out/'pub.json').read_text());sub_data=json.loads((out/'sub.json').read_text());metrics=analyze_pair(pub_data,sub_data)
            (out/'metrics.json').write_text(json.dumps(metrics,indent=2))
            r=dict(name=name,mode=mode,rep=rep+1,condition=a.condition,rmw=a.rmw,planned=planned,published=pub_data.get('succeeded'),
                   received=sub_data.get('unique_received'),publish_rc=pub.returncode,subscriber_rc=subscriber.returncode,
                   metrics={k:v for k,v in metrics.items() if k!='missing_requested'},
                   qdisc_restored=all(q['kind']=='noqueue' for q in json.loads(subprocess.check_output(['tc','-j','qdisc','show','dev','wlp2s0']))))
            r['library_metadata']={role:json.loads((out/(role+'.metadata.json')).read_text())['libraries'] for role in ['pub','sub']}
            if observer:
                r['govern']=json.loads((out/'govern/summary.json').read_text())
                rows=list(csv.DictReader((out/'govern/trace.csv').open()));drops=[];caps=[]
                for row in rows:
                    caps.append(float(row['cap_packet_Bps'])*8/1e6)
                    for q in json.loads(row['qdisc_json']):
                        if q['kind']=='fq':drops.append(q.get('drops',0))
                r.update(fq_drops=max(drops,default=0),cap_Mbps_range=[min(caps),max(caps)])
                normal=[row for row in rows if pub_data['measurement_started_ns']/1e9 <= float(row['monotonic_s']) <= pub_data['measurement_ended_ns']/1e9]
                r['normal_update_fraction']=sum(row['status']=='updated' for row in normal)/len(normal) if normal and mode=='adaptive' else None
            results.append(r);(folder/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps({k:r[k] for k in ['name','published','received','qdisc_restored']}),flush=True)
    print('DONE sender-local W1 '+a.condition,flush=True)


if __name__=='__main__':main()
