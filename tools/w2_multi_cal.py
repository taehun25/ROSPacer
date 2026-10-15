"""W2 two-reader calibration using the unchanged W1 effective-cost fitter.

Two standard UDP flows emulate two unicast receiver copies. This is an
additional topology-specific operating-budget qualification, not airtime proof.
"""
import json,re,time,math
from pathlib import Path
from rospacer.sender_minphy import fit_profile,evaluate,identity,digest,interval_rate
from rospacer.model import synthesize
from rospacer.metrics import analyze_pair

def clock_pair(source,receiver,lo,hi):
    out={'validated':False,'relative_error_bound_ms':None,'errors':[],'method':'chrony system correction + root delay/2 + dispersion; selected local reference'};bounds=[]
    for label,rows in [('sender',source),('receiver',receiver)]:
        if not rows or min(x['wall_ns'] for x in rows)>lo or max(x['wall_ns'] for x in rows)<hi:out['errors'].append(label+' samples do not cover data')
        if any(b['wall_ns']-a['wall_ns']>2e9 or b['wall_ns']<=a['wall_ns'] for a,b in zip(rows,rows[1:])):out['errors'].append(label+' clock gap/discontinuity')
        bs=[]
        for row in rows:
            text=row['tracking']['stdout']
            try:
                vs=[float(re.search(k+r'\s*:\s*([+-]?[0-9.]+)',text)[1]) for k in ['System time','Root delay','Root dispersion']]
                if 'Leap status     : Normal' not in text:raise ValueError()
                if 'Reference ID    : 7F7F0101' not in text and not re.search(r'^\^\*\s+192\.168\.(?:0\.5|50\.1)\s',row['sources']['stdout'],re.M):raise ValueError()
                bs.append((abs(vs[0])+vs[1]/2+vs[2])*1000)
            except Exception:out['errors'].append(label+' unqualified NTP reference')
        bounds.append(max(bs,default=float('inf')))
    out['relative_error_bound_ms']=sum(bounds);out['validated']=not out['errors'] and out['relative_error_bound_ms']<=1.;out['errors']=sorted(set(out['errors']));return out

def dds_trial(r,row):
    from w2_protocol import profile,ScopeError,topic_name
    from w2_control import HOSTS
    from w2_runner import write
    pubs=['4','5'];subs=['12','10'];hosts=pubs+subs;local=r.base/'trials'/row['id'];ips={h:'192.168.0.'+h for h in hosts};configs={};hz={};count={};cals={}
    if row['mode']=='adaptive':
        for h in pubs:
            v=json.loads((r.base/('calibration_t3_'+h)/'validation.json').read_text())
            if not v['receiver_phy_calibrated']['passed']:raise ScopeError('T3 Adaptive blocked: independent budget error exceeds20% on sender'+h)
    remote={h:r.folder(h,'trials/'+row['id']) for h in hosts};duration=row['seconds']+row['warmup']+row['drain']+130
    for h in hosts:
        r.lab.ssh(h,'iw dev '+HOSTS[h][3]+' set power_save off',root=True)
        q=json.loads(r.lab.ssh(h,'tc -j qdisc show dev '+HOSTS[h][3]).decode())
        if not all(x['kind']=='noqueue' for x in q):raise RuntimeError('T3 unexpected shaper')
        maxrx=212992 if row['mode']=='default' else 2147483647 if row['mode'] in ['vendor','vendor_fc'] and row['rmw']=='cyclonedds' else 16777216
        r.lab.ssh(h,f'sysctl -w net.core.rmem_max={maxrx} net.core.wmem_max={212992 if row["mode"]=="default" else 4194304}',root=True)
        baseline=json.loads(r.get(h,r.sessions[h]['folder']+'/baseline.json'))
        if row['mode'] in ['vendor','vendor_fc'] and row['rmw']=='cyclonedds':
            r.lab.ssh(h,'sysctl -w net.ipv4.ipfrag_time=3 net.ipv4.ipfrag_high_thresh=134217728',root=True)
        else:
            r.lab.ssh(h,'sysctl -w '+' '.join(k+'='+str(v) for k,v in baseline['sysctl'].items() if k.startswith('net.ipv4.ipfrag')),root=True)
        r.launch(h,'sampler','trials/'+row['id']+'/telemetry',root=True,dev=HOSTS[h][3],duration=duration)
    for sender in pubs:
        calroot=r.base/('calibration_t3_'+sender)
        if not (calroot/'validation.json').exists():raise ScopeError('two-reader calibration absent '+sender)
        cal=json.loads((calroot/'profile.json').read_text());cals[sender]=cal
        if row['mode']=='adaptive' and not json.loads((calroot/'validation.json').read_text())['receiver_phy_calibrated']['passed']:raise ScopeError('two-reader independent capacity gate failed '+sender)
        hz[sender]=row['rho']*cal['capacity_payload_Bps']/(row['payload']*2);count[sender]=math.ceil(hz[sender]*row['seconds'])
        cfg=synthesize(row['payload'],hz[sender],2,cal['capacity_payload_Bps'],json.loads((calroot/'rtt.json').read_text())['rtt_s'],1)
        cfg.update(dev='wlp2s0',peers=[ips[h] for h in subs],middleware=row['rmw'],cap_packet_Bps=min(cfg['cap_packet_Bps'],cal['ceiling_packet_Bps']))
        bundle=remote[sender]+'/bundle';configs[sender]=bundle
        for f in ['profile.json','manifest.json','validation.json']:r.put(sender,bundle+'/'+f,(calroot/f).read_bytes())
        r.put(sender,bundle+'/governor.json',json.dumps(cfg).encode())
        for h in [sender]+subs:
            prefix='pub' if h==sender else 'sub_from'+sender;port=55620+int(h)+int(sender)*100;others=subs if h==sender else [sender]
            f=local/(h+'_'+prefix+'.xml');profile(cfg,row['rmw'],row['mode'],f,HOSTS[h][3],ips[h],[ips[x] for x in others],port,[55620+int(x)+int(sender)*100 for x in others])
            r.put(h,remote[h]+'/middleware_'+prefix+'.xml',f.read_bytes())
    nominal=r.runpy('5','import json,time;print(json.dumps({"wall":time.time()}))')['wall']+45;jobs=[]
    for sender in pubs:
        topic=topic_name(row['id'],sender)
        if row['mode'] in ['fixed','adaptive']:
            argv=['sudo','-n','python3','-m','rospacer','sender-govern','--bundle',configs[sender],'--validation',configs[sender]+'/validation.json','--out',remote[sender]+'/govern','--seconds',str(min(180,duration)),'--mode',row['mode']]
            if row['mode']=='fixed':
                # Fixed uses measured aggregate C0; it does not consume the
                # failed dynamic estimator or weaken Adaptive's input gate.
                argv=['sudo','-n','python3','-m','rospacer','govern','--mode','fixed','--config',remote[sender]+'/bundle/governor.json','--seconds',str(duration),'--trace',remote[sender]+'/fixed_govern.csv']
            jobs.append((sender,r.launch(sender,'command','trials/'+row['id']+'/govern_job',argv,timeout=duration+10)))
        for h in subs:jobs.append((h,r.endpoint(row,h,'sub',remote[h],hz[sender],count[sender],topic,nominal,prefix='sub_from'+sender,barrier=True)))
    for sender in pubs:jobs.append((sender,r.endpoint(row,sender,'pub',remote[sender],hz[sender],count[sender],topic_name(row['id'],sender),nominal,2,prefix='pub',barrier=True)))
    ready={};deadline=time.monotonic()+85
    while time.monotonic()<deadline:
        for sender in pubs:
            if sender not in ready:
                v=r.runpy(sender,'from pathlib import Path;import json;p=Path('+repr(remote[sender]+'/pub.warmup_ready.json')+');print(p.read_text() if p.exists() else "null")')
                if v:ready[sender]=v
        if len(ready)==len(pubs):break
        r.status('running_trial',phase='waiting for both T3 warmups');time.sleep(.3)
    else:raise RuntimeError('T3 publishers did not complete warmup barrier')
    go_wall=r.runpy('5','import time,json;print(json.dumps({"wall":time.time()}))')['wall']+5
    for h in hosts:r.put(h,remote[h]+'/measurement.go.json',json.dumps({'start_wall':go_wall}).encode())
    for h,f in jobs:
        done=r.wait(h,f,duration+35)
        if done.get('rc')!=0:raise RuntimeError('T3 endpoint/controller job failed host'+h+'; raw logs retained')
    for h in hosts:
        done=r.wait(h,remote[h]+'/telemetry',duration+35)
        if done.get('rc')!=0:raise RuntimeError('T3 telemetry failed host'+h)
        r.archive(h,remote[h],local/h)
    pairs=[];total_pub=total_rx=0
    for sender in pubs:
        pub=json.loads((local/sender/'pub.json').read_text());total_pub+=pub['succeeded']
        if row['mode']=='fixed':
            import csv
            trace=list(csv.DictReader((local/sender/'fixed_govern.csv').open()))
            if not trace or float(trace[0]['monotonic_s'])>pub['measurement_started_ns']/1e9 or float(trace[-1]['monotonic_s'])<pub['measurement_ended_ns']/1e9-.6:
                raise RuntimeError('fixed HTB does not cover entire T3 measurement')
        for receiver in subs:
            sub=json.loads((local/receiver/('sub_from'+sender+'.json')).read_text());total_rx+=sub['unique_received'];stamps=[v for x in sub['records'] for k,v in x.items() if k in ['publisher_wall_ns','arrival_wall_ns']]
            clocks=[[json.loads(s) for s in (local/h/'telemetry/clock.jsonl').read_text().splitlines()] for h in [sender,receiver]]
            clock=clock_pair(*clocks,min(stamps) if stamps else 0,max(stamps) if stamps else 0);metrics=analyze_pair(pub,sub,clock)
            pairs.append({'sender':sender,'receiver':receiver,'clock':clock,'metrics':metrics})
    libraries={}
    for h in hosts:
        for f in (local/h).glob('*.metadata.json'):
            data=json.loads(f.read_text())['libraries'];valid=bool(data) and all(r.expected.get('runtime_w1_45/'+row['rmw']+'/'+Path(p).name)==s for p,s in data.items())
            libraries[h+'/'+f.name]={'valid':valid,'actual':data}
            if not valid:raise RuntimeError('T3 runtime hash mismatch')
    restored=all(all(x['kind']=='noqueue' for x in json.loads(r.lab.ssh(h,'tc -j qdisc show dev wlp2s0').decode())) for h in pubs)
    if not restored:raise RuntimeError('T3 qdisc not restored')
    gp=sum((x['metrics']['arrival_interval_goodput_Bps'] or 0)*8/1e6 for x in pairs);per_sender=[sum((x['metrics']['arrival_interval_goodput_Bps'] or 0) for x in pairs if x['sender']==h) for h in pubs]
    result={'id':row['id'],'status':'measured','row':row,'topology_roles':{'publishers':pubs,'receivers':subs},'role_reason':'both MT7921 devices publish so W1 counter semantics apply; Intel/Realtek endpoints receive','pairs':pairs,'published':total_pub,'received':total_rx,'goodput_Mbps':gp,'p99_ms':max((x['metrics']['end_to_end_latency_ms']['p99'] for x in pairs if x['metrics']['end_to_end_latency_ms']),default=None),'jitter_p99_ms':max((x['metrics']['arrival_jitter_ms']['p99'] for x in pairs if x['metrics']['arrival_jitter_ms']['p99'] is not None),default=None),'reason':'T3 latency excluded per pair if Wi-Fi clock bound >1ms','C0_Mbps':{h:cals[h]['capacity_payload_Bps']*8/1e6 for h in pubs},'requested_hz':hz,'Jain_fairness':sum(per_sender)**2/(2*sum(x*x for x in per_sender)) if sum(per_sender) else None,'qdisc_restored':True,'two_reader_budget':'empirical aggregate UDP C0; dynamic predictor failed independent Clean gate; physical airtime and universal model unqualified'}
    result['warmup_barrier']={'enabled':True,'ready':ready,'measurement_start_wall':go_wall,'protocol':'10s warmup; wait for both calls to finish; quiet shared 5s start lead; 60s common measurement'}
    result['actual_start_offset_s']={h:json.loads((local/h/'pub.start.json').read_text())['wall_ns']/1e9-go_wall for h in pubs}
    if any(abs(x)>1 for x in result['actual_start_offset_s'].values()):
        result.update(status='timing_unqualified',reason='T3 publisher start deviates >1s from common schedule')
    write(local/'summary.json',result);return result

def trial(r,sender,name,mbps,seconds):
    suffix='calibration_t3_'+sender+'/'+name;source='192.168.0.'+sender;subips={'12':'192.168.0.12','10':'192.168.0.10'}
    servers={}
    if mbps:
        for h in subips:
            servers[h]=r.launch(h,'command',suffix+'/server'+h,['timeout','-k','2',str(seconds+35),'iperf3','-s','-1','-B',subips[h],'-p','55971','-J','-i','.2'],timeout=seconds+40)
        for h in subips:
            for attempt in range(8):
                listeners=r.lab.ssh(h,'ss -H -lnt').decode()
                if ':55971 ' in listeners:break
                time.sleep(.5)
            else:raise RuntimeError('two-reader listener not ready '+h)
        # Resolve each Wi-Fi neighbour before TCP control handshakes.
        r.lab.ssh(sender,'ping -I wlp2s0 -c 2 -W 2 192.168.0.12',timeout=10)
        r.lab.ssh(sender,'ping -I wlp2s0 -c 2 -W 2 192.168.0.10',timeout=10)
    args=[['iperf3','-c',ip,'-B',source,'-p','55971','-u','-b',str(round(mbps*1e6/2)),'-l','1400','-w','1048576','--connect-timeout','8000','-t',str(seconds),'-J'] for ip in subips.values()] if mbps else []
    code='''import time,subprocess,json,os,signal
import sys
sys.path.insert(0,SOURCE_ROOT)
from pathlib import Path
from rospacer.sender_minphy import sample,identity
folder=Path(FOLDER);folder.mkdir(parents=True,exist_ok=True)
ps=[subprocess.Popen(a,stdout=open(folder/('client'+str(i)+'.json'),'w'),stderr=open(folder/('client'+str(i)+'.stderr'),'w'),start_new_session=True) for i,a in enumerate(ARGS)]
rows=[];errors=[];start=time.monotonic()
try:
 while time.monotonic()<start+SECONDS:
  tick=time.monotonic()
  try:rows.append(sample('wlp2s0'))
  except Exception as e:errors.append(str(e))
  time.sleep(max(0,.2-(time.monotonic()-tick)))
 for p in ps:
  if p.wait(timeout=8):raise RuntimeError('UDP client failed')
finally:
 for p in ps:
  if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
result={'rows':rows,'errors':errors,'start_monotonic':start,'end_monotonic':time.monotonic(),'rate_mbps':MBPS,'scope':identity('wlp2s0')}
(folder/'source.json').write_text(json.dumps(result));print(json.dumps(result))
'''.replace('SOURCE_ROOT',repr(r.lab.home(sender))).replace('FOLDER',repr(r.folder(sender,suffix))).replace('ARGS',repr(args)).replace('SECONDS',str(seconds)).replace('MBPS',str(mbps))
    # Use a quoted python command so source imports come from the sender checkout.
    import shlex
    result=json.loads(r.lab.ssh(sender,'python3 -c '+shlex.quote(code),root=True,timeout=seconds+30))
    if result['errors']:raise RuntimeError('two-reader counter collection incomplete')
    if mbps:
        capacity=0
        for h,folder in servers.items():
            done=r.wait(h,folder,20);r.archive(h,folder,r.base/suffix/('receiver'+h))
            data=json.loads((r.base/suffix/('receiver'+h)/'job.log').read_text())
            if done['rc']:raise RuntimeError('two-reader server failed')
            capacity+=interval_rate(data)
        result['receiver_payload_Bps']=capacity
    r.archive(sender,r.folder(sender,suffix),r.base/suffix/'sender')
    return result

def calibrate(r,sender,tag='v3_'):
    for h in [sender,'12','10']:
        r.lab.ssh(h,'iw dev '+('wlo1' if h=='12' else 'wlp2s0')+' set power_save off',root=True)
        r.lab.ssh(h,'sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304',root=True)
    phys=[]
    for h in ['12','10']:
        text=r.lab.ssh(h,'iw dev '+('wlo1' if h=='12' else 'wlp2s0')+' link').decode();m=re.search(r'rx bitrate:\s*([0-9.]+) MBit/s',text)
        if not m:raise RuntimeError('two-reader receive PHY unavailable')
        phys.append(float(m[1])*125000)
    phy=2/sum(1/x for x in phys)
    trials=[trial(r,sender,tag+n,b,s) for n,b,s in [('idle',0,8),('load50',50,15),('load150',150,15),('capacity',600,15)]]
    p=fit_profile(trials,phy,trials[-1]['scope']);p.update(source_IP='192.168.0.'+sender,peer_IP='192.168.0.12',receiver_count=2,receiver_PHY_Bps=phys,peer_PHY_combination='equal-copy harmonic mean',scope='W2 two-reader aggregate UDP operating-budget fit; not physical beta/O',calibration_socket_bytes=1048576)
    local=r.base/('calibration_t3_'+sender);local.mkdir(exist_ok=True)
    for f in ['profile.json','validation.json','manifest.json']:
        if (local/f).exists() and not (local/('previous_'+f)).exists():(local/('previous_'+f)).write_bytes((local/f).read_bytes())
    (local/'profile.json').write_text(json.dumps(p,indent=2))
    held=trial(r,sender,tag+'independent_Clean',600,15);v=evaluate(p,held);v.update(condition='Clean',profile_sha256=digest(local/'profile.json'),sender_host=sender,refit_after_validation=False)
    (local/'validation.json').write_text(json.dumps(v,indent=2));(local/'manifest.json').write_text(json.dumps({'calculation_host':'control-PC topology extension','receiver_access':'initial standard iw and iperf only; none during govern','profile_sha256':digest(local/'profile.json'),'production_approved':False}))
    ping=r.lab.ssh(sender,'ping -I wlp2s0 -c 10 -i .2 -W 2 192.168.0.12').decode();m=re.search(r'= [0-9.]+/([0-9.]+)/',ping)
    if not m:raise RuntimeError('two-reader RTT absent')
    (local/'rtt.json').write_text(json.dumps({'rtt_s':float(m[1])/1000,'raw':ping}))
    return {'sender':sender,'C0_Mbps':p['capacity_payload_Bps']*8/1e6,'independent_validation':v['receiver_phy_calibrated']}
