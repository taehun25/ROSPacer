"""Bounded paired W1 runs; preserves failed publishes, sockets, qdisc and sources."""
import argparse,io,json,math,shlex,statistics,tarfile,time
from pathlib import Path
from deploy import ROOT,REMOTE,ssh
from w1_calibrate import remote,launch,fetch
import sys
sys.path.insert(0,str(ROOT))
from rospacer.model import synthesize,golden_profile
from rospacer import profiles
from rospacer.metrics import analyze_pair
from rospacer.linux import parse_class_stats

HOMES={'12':'/home/csi2','10':'/home/csi'}
DEVS={'12':'wlo1','10':'wlp2s0'}
IPS={'12':'192.168.0.3','10':'192.168.0.4'}

def shell(h,script,check=True):
    q=ssh(h,'bash -c '+shlex.quote(script))
    if check and q.returncode:raise RuntimeError(q.stderr.decode()+' '+q.stdout.decode())
    return {'rc':q.returncode,'stdout':q.stdout.decode(),'stderr':q.stderr.decode()}

def setup(rmw,h):
    script='source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; '
    script+='export ROS_DOMAIN_ID=74 RMW_IMPLEMENTATION='+{'fastdds':'rmw_fastrtps_cpp','cyclonedds':'rmw_cyclonedds_cpp'}[rmw]+'; '
    script+='unset CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML FASTDDS_BUILTIN_TRANSPORTS; '
    if rmw=='fastdds':script+='export LD_LIBRARY_PATH='+HOMES[h]+'/'+REMOTE+'/runtime_fastdds_w1:$LD_LIBRARY_PATH; '
    return script

def archive_run(host,run,name,local):
    code='import sys,tarfile; from pathlib import Path\np=Path('+repr(HOMES[host]+'/'+REMOTE+'/runs/'+run+'/'+name)+')\nwith tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz") as tf:\n for f in p.iterdir():\n  if f.is_file():tf.add(f,arcname=f.name)'
    q=ssh(host,'python3 -',code.encode())
    if q.returncode:raise RuntimeError(q.stderr.decode())
    dest=local/host;dest.mkdir(parents=True,exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(q.stdout),mode='r:gz') as tf:
        for m in tf:
            if '/' in m.name or not m.isfile():raise RuntimeError('unexpected run archive member')
            (dest/m.name).write_bytes(tf.extractfile(m).read())

def write_remote(h,path,contents):
    return remote(h,'from pathlib import Path;import json\np=Path('+repr(path)+');p.parent.mkdir(parents=True,exist_ok=True);p.write_text('+repr(contents)+');print("{}")')

def analyze_telemetry(path):
    rows=[json.loads(s) for s in path.read_text().splitlines()]
    result={'samples':len(rows),'collection_max_s':max((r['collection_duration_s'] for r in rows),default=None)}
    ticks=[r['monotonic_s'] for r in rows];intervals=[b-a for a,b in zip(ticks,ticks[1:])]
    result['sample_interval_s']={'median':statistics.median(intervals) if intervals else None,'max':max(intervals,default=None)}
    result['udp_delta']={k:rows[-1]['udp_global'].get(k,0)-rows[0]['udp_global'].get(k,0) for k in rows[0]['udp_global']} if rows else {}
    import re
    vals={k:[] for k in ['w','t','tb','rb','d']};socket_endpoints=set()
    for r in rows:
        raw=r['sockets']['stdout']
        for block in raw.split('UNCONN')[1:]:
            if '"python3"' not in block:continue
            endpoint=re.search(r'(?:192\.168\.0\.[34]|0\.0\.0\.0):\d+',block)
            if endpoint:socket_endpoints.add(endpoint.group())
            for k in vals:
                m=re.search(r'\b'+k+r'(\d+)',block)
                if m:vals[k].append(int(m[1]))
    result['python_udp_endpoints']=sorted(socket_endpoints)
    result['skmem_max']={k:max(v,default=None) for k,v in vals.items()}
    drops=[];backlogs=[]
    for r in rows:
        try:qs=json.loads(r['qdisc']['stdout'])
        except ValueError:continue
        drops.extend(q.get('drops',0) for q in qs if q.get('kind')=='fq')
        backlogs.extend(q.get('backlog',0) for q in qs if q.get('kind')=='fq')
    result.update(fq_drop_max=max(drops,default=0),fq_backlog_max=max(backlogs,default=0))
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--mode',choices=['backpressure','smoke'],default='backpressure');p.add_argument('--middleware',choices=['fastdds','cyclonedds']);a=p.parse_args()
    base=ROOT/'runs'/a.run
    cal=json.loads((base/'calibration_ready/summary.json').read_text())
    C0=cal['C0_UDP_receiver_median_bps']/8
    import re
    match=re.search(r'= ([0-9.]+)/([0-9.]+)/',cal['ping']['stdout']);rtt=float(match[2])/1000 if match else None
    if not C0 or not rtt:raise RuntimeError('measured C0 and RTT required')
    selected=[a.middleware] if a.middleware else ['fastdds','cyclonedds']
    old_buffers={h:{k:int(shell(h,'cat /proc/sys/net/core/'+k)['stdout']) for k in ['rmem_max','wmem_max']} for h in HOMES}
    specs=[]
    for rmw in selected:
        if a.mode=='backpressure':
            specs += [(rmw,'bp_default100',.8,100),(rmw,'bp_design',.8,None)]
        else:specs += [(rmw,label,.2,None) for label in ['default','vendor','static','fixed']]
    summaries=[]
    try:
        for index,(rmw,label,loadratio,flow) in enumerate(specs):
            name=rmw+'_'+label
            local=base/name
            if (local/'summary.json').exists():
                print('SKIP existing '+name,flush=True);continue
            hz=loadratio*C0/1048576;count=math.ceil(30*hz)
            cfg=synthesize(1048576,hz,1,C0,rtt,1)
            cfg.update(dev='wlo1',peers=['192.168.0.4'],middleware=rmw,interval_s=.2,relay_in_survey=None,airtime_overhead_s=None,classifier='rtps_ipv4_no_options')
            cfg['cap_packet_Bps']=(.5 if a.mode=='backpressure' else .9)*C0
            cfg['cap_application_Bps']=cfg['cap_packet_Bps']/cfg['packet_factor']
            cfg['experiment_cap_definition']='HTB rate/ceil is exactly the stated fraction of measured UDP C0; qdisc packet bytes, not inferred DDS application throughput'
            if flow is not None:cfg['fq_flow_limit']=flow
            local.mkdir(parents=True,exist_ok=True)
            shaped=a.mode=='backpressure' or label=='fixed'
            profiled=label not in ['default','vendor']
            # Vendor here is explicitly UDP buffer tuning supported in 2.6.11,
            # not the unsupported LARGE_DATA environment mode from newer releases.
            if label=='vendor':
                cfg['socket_tx_bytes']=1048576;cfg['socket_rx_bytes']=4194304
            for h in HOMES:
                remote_base=HOMES[h]+'/'+REMOTE+'/runs/'+a.run+'/'+name
                remote(h,'from pathlib import Path;import json;Path('+repr(remote_base)+').mkdir(parents=True,exist_ok=True);print("{}")')
                write_remote(h,remote_base+'/config.json',json.dumps(dict(cfg,dev=DEVS[h],peers=[IPS['10' if h=='12' else '12']]),indent=2))
                if profiled or label=='vendor':
                    profile=local/('profile'+h+'.xml')
                    if rmw=='fastdds':profiles.fastdds(cfg,profile,IPS[h])
                    else:profiles.cyclone(cfg,profile,DEVS[h],IPS['10' if h=='12' else '12'])
                    if label=='vendor':
                        # Keep native fragmentation/heartbeat/history behavior for vendor buffer-only arm.
                        import xml.etree.ElementTree as E
                        tree=E.parse(profile);root=tree.getroot()
                        if rmw=='fastdds':
                            ns={'d':'http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles'}
                            coll=root.find('d:profiles',ns)
                            for endpoint in list(coll):
                                if endpoint.tag.split('}')[-1] in ['publisher','subscriber']:coll.remove(endpoint)
                            tr=coll.find('d:transport_descriptors/d:transport_descriptor',ns)
                            for field in list(tr):
                                if field.tag.split('}')[-1]=='maxMessageSize':field.text='65000'
                        else:
                            ns={'d':'https://cdds.io/config'};d=root.find('d:Domain',ns);g=d.find('d:General',ns);inn=d.find('d:Internal',ns)
                            for field in list(g):
                                if field.tag.split('}')[-1] in ['MaxMessageSize','FragmentSize']:g.remove(field)
                            for field in list(inn):
                                if field.tag.split('}')[-1] not in ['SocketSendBufferSize','SocketReceiveBufferSize']:inn.remove(field)
                        tree.write(profile,encoding='utf-8',xml_declaration=True)
                    profiles.validate(profile,ROOT/'reference'/('fastdds-2.6.10-local-validation.xsd' if rmw=='fastdds' else 'cyclonedds-0.10.5.xsd'))
                    write_remote(h,remote_base+'/middleware.xml',profile.read_text())
                rx=max(old_buffers[h]['rmem_max'],cfg['socket_rx_bytes']) if profiled or label=='vendor' else old_buffers[h]['rmem_max']
                tx=max(old_buffers[h]['wmem_max'],cfg['socket_tx_bytes']) if profiled or label=='vendor' else old_buffers[h]['wmem_max']
                shell(h,'sudo -n /sbin/sysctl -w net.core.rmem_max='+str(rx)+' net.core.wmem_max='+str(tx))
            print(json.dumps({'START':name,'requested_hz':hz,'C0_Mbps':C0*8/1e6,'HTB_Mbps':cfg['cap_packet_Bps']*8/1e6 if shaped else None,'flow_limit':cfg['fq_flow_limit'] if shaped else None}),flush=True)
            started=time.monotonic();pids={}
            for h in HOMES:
                b=HOMES[h]+'/'+REMOTE+'/runs/'+a.run+'/'+name
                argv=['timeout','-k','3','58','python3','tools/telemetry.py','--dev',DEVS[h],'--seconds','53','--interval','0.1','--out',b+'/telemetry.jsonl']
                if h=='12':argv=['sudo','-n']+argv
                pids['telemetry'+h]=launch(h,argv,HOMES[h]+'/'+REMOTE,b+'/telemetry.log')['pid']
            if shaped:
                b=HOMES['12']+'/'+REMOTE+'/runs/'+a.run+'/'+name
                pids['govern']=launch('12',['sudo','-n','timeout','-k','3','52','python3','-m','rospacer','govern','--mode','fixed','--seconds','47','--config',b+'/config.json','--trace',b+'/govern.csv'],HOMES['12']+'/'+REMOTE,b+'/govern.log')['pid']
                time.sleep(.7)
            b=HOMES['10']+'/'+REMOTE+'/runs/'+a.run+'/'+name
            env=setup(rmw,'10')
            if profiled or label=='vendor':env+=('export FASTRTPS_DEFAULT_PROFILES_FILE='+b+'/middleware.xml RMW_FASTRTPS_USE_QOS_FROM_XML=1; ' if rmw=='fastdds' else 'export CYCLONEDDS_URI=file://'+b+'/middleware.xml; ')
            subcmd=env+'cd '+HOMES['10']+'/'+REMOTE+'; exec timeout -k 3 48 python3 tools/traffic.py sub --count '+str(count)+' --hz '+str(hz)+' --seconds 43 --out '+b+'/sub.json'
            pids['sub']=launch('10',['bash','-c',subcmd],HOMES['10']+'/'+REMOTE,b+'/sub.log')['pid']
            time.sleep(.5)
            b=HOMES['12']+'/'+REMOTE+'/runs/'+a.run+'/'+name
            env=setup(rmw,'12')
            if profiled or label=='vendor':env+=('export FASTRTPS_DEFAULT_PROFILES_FILE='+b+'/middleware.xml RMW_FASTRTPS_USE_QOS_FROM_XML=1; ' if rmw=='fastdds' else 'export CYCLONEDDS_URI=file://'+b+'/middleware.xml; ')
            cmd=env+'cd '+HOMES['12']+'/'+REMOTE+'; timeout -k 3 46 python3 tools/traffic.py pub --count '+str(count)+' --hz '+str(hz)+' --seconds 30 --discovery-seconds 8 --drain-seconds 5 --continue-on-publish-error --out '+b+'/pub.json > '+b+'/pub.log 2>&1'
            pubresult=shell('12',cmd,False)
            # Complete all bounded samplers and governor before collecting/restoring.
            remaining=54-(time.monotonic()-started)
            if remaining>0:time.sleep(remaining)
            for h in HOMES:archive_run(h,a.run,name,local)
            pub=json.loads((local/'12/pub.json').read_text());sub=json.loads((local/'10/sub.json').read_text())
            metrics=analyze_pair(pub,sub)
            summary={'name':name,'rmw':rmw,'label':label,'requested_load_ratio':loadratio,'C0_Bps':C0,'config':cfg,'shaped':shaped,'requested_count':count,'requested_hz':hz,'publisher_command':pubresult,'pids':pids,'metrics':metrics,'telemetry':{h:analyze_telemetry(local/h/'telemetry.jsonl') for h in HOMES},
                'clock_validated':False,'latency_excluded_reason':'No independent wired clock reference; host10 unsynchronised in preflight',
                'vendor_definition':'buffer-only UDP tuning with native fragment/history timing; LARGE_DATA availability checked separately' if label=='vendor' else None}
            summary['qdisc_after']=json.loads(shell('12','tc -j qdisc show dev wlo1')['stdout'])
            (local/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');summaries.append(summary)
            print(json.dumps({'DONE':name,'metrics':metrics,'telemetry':summary['telemetry']}),flush=True)
            for h in HOMES:shell(h,'sudo -n /sbin/sysctl -w net.core.rmem_max='+str(old_buffers[h]['rmem_max'])+' net.core.wmem_max='+str(old_buffers[h]['wmem_max']))
    finally:
        errors=[]
        for h in HOMES:
            try:shell(h,'sudo -n /sbin/sysctl -w net.core.rmem_max='+str(old_buffers[h]['rmem_max'])+' net.core.wmem_max='+str(old_buffers[h]['wmem_max']))
            except Exception as e:errors.append(str(e))
        (base/(a.mode+'_restoration.json')).write_text(json.dumps({'buffer_restore_errors':errors,'original':old_buffers},indent=2))
        if errors:raise RuntimeError('; '.join(errors))

if __name__=='__main__':main()
