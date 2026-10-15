"""Unattended three-repeat W2 campaign; raw failures and scope gates retained."""
import argparse,hashlib,html,io,json,math,os,random,re,shlex,signal,subprocess,sys,tarfile,time,traceback,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deploy import ROOT,KEY
from w2_control import Lab,HOSTS,OTHER,SR2
from w2_protocol import matrix,topology,profile,topic_name,ScopeError,competition_schedule
from w2_failure_policy import TERMINAL,decide,summarize_record
from rospacer.model import synthesize
from rospacer.metrics import analyze_pair,percentile,recovery_metric
from rospacer.clock import qualify_pair
from rospacer.sender_minphy import require_qualification

def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.pending');tmp.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(p)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def unpack(blob,dest):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as tf:
        for m in tf:
            n=Path(m.name)
            if n.is_absolute() or '..' in n.parts:raise ValueError('artifact path')
            if m.isfile():q=dest/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(tf.extractfile(m).read())

class Runner:
    def __init__(self,base):
        self.base=Path(base).resolve();self.lab=Lab(self.base);self.lab.wired=True;self.sessions=json.loads((self.base/'sessions.json').read_text())
        self.pair_ap=json.loads((self.base/'pair_ap.json').read_text())['ap'] if (self.base/'pair_ap.json').exists() else None;self.jobs=[];self.results=[];self.active=None;self.active_artifact=None
        self.expected=json.loads((self.base/'runtime_manifest.json').read_text());self.failures=0;self.eta_hours=None;self.all_rows=[];self.current_row=None;self.last_status=0
    def folder(self,h,suffix=''):return self.lab.home(h)+'/runs/'+self.base.name+'/'+suffix
    def runpy(self,h,code,root=False,timeout=45):return self.lab.py(h,code,root=root,timeout=timeout)
    def put(self,h,path,data):self.lab.put(h,path,data)
    def get(self,h,path):return self.lab.ssh(h,'cat '+shlex.quote(str(path)))
    def archive(self,h,path,dest):
        unpack(self.lab.ssh(h,'tar -czf - -C '+shlex.quote(path)+' .',root=True,timeout=80),dest)
    def status(self,state,**fields):
        done={x['id'] for x in self.results if x.get('status') in TERMINAL}
        d={'state':state,'updated_UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'pid':os.getpid(),'active':self.active,'finished':len(self.results),'valid_measured':sum(x.get('status')=='measured' for x in self.results),'blocked_scope':sum(x.get('status')=='blocked_scope' for x in self.results),'skipped_failed':sum(x.get('status')=='skipped_failed' for x in self.results),'pending':sum(x['id'] not in done for x in self.all_rows) if self.all_rows else None,'estimated_remaining_hours':self.eta_hours,'failures':self.failures,**fields}
        if self.current_row:d.setdefault('row',self.current_row)
        self.last_status=time.monotonic()
        write(self.base/'progress.json',d);self.report(d)
    def report(self,state):
        rows=''
        for r in self.results:
            source=Path(r.get('source_artifacts_root',str(self.base/'trials'/r['id'])))
            link='<a href="'+html.escape((source/'summary.json').as_uri(),quote=True)+'">원자료</a>'
            rows+='<tr>'+''.join('<td>'+html.escape(str(r.get(k,'')))+'</td>' for k in ['id','status','published','received','goodput_Mbps','p99_ms','jitter_p99_ms','reason'])+'<td>'+link+'</td></tr>'
        continuation=''
        if (self.base/'continuation.json').exists():
            c=json.loads((self.base/'continuation.json').read_text(encoding='utf-8'))
            if c.get('T3_barrier_protocol'):
                continuation='<p><b>10/15 재개 구간:</b> 기존 원자료를 수정하지 않고 T1 E 33건을 재사용합니다. F 33건은 독립 포트·시작 일정, T3 27건은 양쪽 워밍업 완료 뒤 공통 측정 시각을 지정하는 절차로 다시 측정합니다. T3 Adaptive 6개는 보류입니다. 남은 P0 108건을 포함해 재개 시 실행 대상은 168건입니다. 바뀐 절차의 결과와 섞지 않기 위해 기존 F·T3 원자료를 별도로 보존합니다. 재시도는 운영 실패에만 최대 1회 추가하며 낮은 성능을 이유로 재시도하지 않습니다.</p>'
            else:continuation='<p><b>10/15 재개 준비 중:</b> 기존 원자료를 보존하고 수정한 토픽·경쟁 부하·측정 시작 경로를 시운전하고 있습니다. 정식 실행 대상은 보수 검증 후 확정합니다.</p>'
        notes='<details><summary>실험 범위와 해석</summary><p>T1: 송신 4 → 수신 5. T3: 송신 4·5가 각각 수신 12·10에 복사 전송합니다. 207개 계획 중 T3 Adaptive 6개는 독립 입력 검증 오차 약 33%로 보류하며, 나머지 201개를 실행 대상으로 둡니다. T3 Static/Fixed는 측정한 UDP 합산 용량을 사용하며, 실패한 적응형 예측기를 사용하지 않습니다.</p><p>Adaptive는 W1 최소 PHY 교정 모델의 실행 중 송신 측 관측 제어입니다. 초기 수신 PHY 교정은 포함됩니다. 원래 제안서의 전체 Drain Control 구현이나 보편적인 물리 airtime 모델의 완성을 뜻하지 않습니다. 현재 T1의 새 교정은 독립 Clean 검증을 통과했고, F·B2·C2에서의 실제 성능은 이번 실험으로 평가합니다.</p><p>시계 오차 상한이 1 ms를 넘는 구간의 종단 지연은 제외합니다. 특히 T3 수신기의 무선 시계 동기화는 이 기준을 충족하지 못할 수 있습니다. 수신 수는 T3에서 수신 단말별 복사 수를 합산하므로 발행 수의 최대 두 배입니다. 처리량과 도착 간격 지터는 원자료의 별도 정의를 확인하십시오.</p><p>Default에도 공통 QoS 및 Wi-Fi 인터페이스·발견 설정을 적용합니다. Vendor는 Fast DDS TCP 전송과 큰 버퍼, CycloneDDS 큰 버퍼 및 권장 커널 설정입니다. Vendor-FC는 Fast DDS의 비동기 FlowController 비교군입니다. Static은 계산한 XML, Fixed는 Static와 고정 HTB/fq 상한, Adaptive는 Static와 갱신 상한입니다. 기동·복원·시운전의 실패도 원자료에 보존합니다.</p></details>'
        body='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>W2 실험 진행 및 결과</title><style>body{font:15px/1.8 "Malgun Gothic",sans-serif;margin:35px;color:#25344a}table{border-collapse:collapse;font-size:12px}td,th{border:1px solid #ccd;padding:8px}th{background:#eef}pre{white-space:pre-wrap}h1{font-size:27px}</style><h1>W2 실험 진행 및 결과</h1><p>각 조건 3회. T1 E → T1 F → T3 E → 나머지 P0. 실패·적용 범위 부족은 성공으로 집계하지 않습니다.</p><p>3회는 탐색적 반복이며 성능 우위 확정이나 제안서의 5회 결정 게이트 충족을 뜻하지 않습니다.</p>'+continuation+notes+'<p><b>실패 처리 정책:</b> 케이스별 운영 실패는 최초 시도와 재시도 1회까지 기록합니다. 이후 네 장비의 프로세스 종료·Wi-Fi 연결·noqueue·커널 기준값·준비 감시 프로세스를 확인한 경우 skipped_failed로 남기고 다음 케이스로 넘어갑니다. 공통 환경이 두 차례 정리·확인 후에도 복구되지 않으면 전체 중단합니다. 낮은 성능은 유효한 측정 결과로 남기며 재시도하지 않습니다. skipped_failed는 완료된 성능 측정으로 집계하지 않습니다.</p><pre>'+html.escape(json.dumps(state,ensure_ascii=False,indent=2))+'</pre><p>상세 원자료: 이 파일 옆 trials 폴더. 이전 구간에서 재사용한 결과는 해당 원자료 링크를 확인합니다. 종료 후 restoration.json 확인.</p><table><tr>'+''.join('<th>'+s+'</th>' for s in ['조건','상태','발행','수신','유효 처리량 Mb/s','p99 지연 ms','도착 간격 지터 p99 ms','사유','근거'])+'</tr>'+rows+'</table></html>'
        (self.base/'W2 실험 진행 및 결과.html').write_text(body,encoding='utf-8')
        mirror=self.base.parents[2]/'html 파일 모음/결과/W2 실험결과/W2 실험 진행 및 결과_261014.html'
        mirror.parent.mkdir(parents=True,exist_ok=True)
        if (self.base/'dispatch_failure_history.json').exists():
            count=json.loads((self.base/'dispatch_failure_history.json').read_text())['count']
            body=body.replace('<h1>W2 실험 진행 및 결과</h1>','<h1>W2 실험 진행 및 결과</h1><p>DDS 측정 전에 발생한 관리 접속 실패 '+str(count)+'건은 dispatch_failures에 보존했습니다. 유선 관리 및 숨김 콘솔 SSH 입력 종료를 수정하고, 원래 환경 복원 확인 후 해당 계획 항목을 다시 실행합니다. 이 실패는 DDS 성능 결과로 집계하지 않습니다.</p>')
            (self.base/'W2 실험 진행 및 결과.html').write_text(body,encoding='utf-8')
        mirror.write_text(body.replace('상세 원자료: 이 파일 옆 trials 폴더.','상세 원자료: ROSPacer/runs/'+self.base.name+'/trials 폴더.'),encoding='utf-8')
    def freeze_sources(self):
        files=[p for folder in ['rospacer','tools'] for p in (ROOT/folder).glob('*.py')]
        blob=io.BytesIO()
        with tarfile.open(fileobj=blob,mode='w:gz') as tf:
            for p in files:tf.add(p,arcname=p.relative_to(ROOT))
        (self.base/'source_snapshot.tar.gz').write_bytes(blob.getvalue())
        write(self.base/'source_sha256.json',{str(p.relative_to(ROOT)):sha(p) for p in files})
    def deploy(self):
        self.lab.select(OTHER)
        public=Path(KEY+'.pub').read_text().strip();line='restrict '+public+' W2-temporary-PC'
        r=self.runpy('4','from pathlib import Path;import json;p=Path.home()/".ssh/authorized_keys";s=p.read_text();line='+repr(line)+';added='+repr(public.split()[1])+' not in s\nif added:p.write_text(s.rstrip()+"\\n"+line+"\\n")\nprint(json.dumps({"added":added,"line":line}))')
        if (self.base/'direct4.json').exists():
            previous=json.loads((self.base/'direct4.json').read_text())
            if previous.get('added'):r=previous
        write(self.base/'direct4.json',r);self.lab.direct4=True
        self.runpy('4','import json;print(json.dumps({"direct_ssh":True}))')
        files=[p for folder in ['rospacer','tools'] for p in (ROOT/folder).glob('*.py')]
        blob=io.BytesIO()
        with tarfile.open(fileobj=blob,mode='w:gz') as tf:
            for p in files:tf.add(p,arcname=p.relative_to(ROOT))
        (self.base/'source_snapshot.tar.gz').write_bytes(blob.getvalue());write(self.base/'source_sha256.json',{str(p.relative_to(ROOT)):sha(p) for p in files})
        for ap,hs in [(OTHER,['4','5']),(self.pair_ap if self.pair_ap in [OTHER,SR2] else SR2,['12','10'])]:
            self.lab.select(ap)
            for h in hs:
                home=self.lab.home(h);code='import sys,tarfile;from pathlib import Path;p=Path('+repr(home)+')\nwith tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz") as tf:\n for m in tf:\n  if not m.isfile() or len(Path(m.name).parts)!=2 or Path(m.name).parts[0] not in ["rospacer","tools"]:raise ValueError("source")\n  f=p/m.name;f.parent.mkdir(exist_ok=True);f.write_bytes(tf.extractfile(m).read())'
                self.lab.ssh(h,'python3 -c '+shlex.quote(code),blob.getvalue(),timeout=90)
        self.lab.select(OTHER)
        # Make the same closure available under runtime_w2 on the source as well.
        self.lab.ssh('4','test -e '+shlex.quote(self.lab.home('4')+'/runtime_w2')+' || ln -s runtime_w1_45 '+shlex.quote(self.lab.home('4')+'/runtime_w2'))
    def ap_pair(self,ap):
        if getattr(self,'peer_state_verified',False) and self.pair_ap==ap:
            self.lab.select(OTHER);return
        was_verified=getattr(self,'peer_state_verified',False)
        prior_ap=self.pair_ap
        self.peer_state_verified=False
        def probe(h):
            code='import json,subprocess;from pathlib import Path;print(json.dumps({"mac":Path("/sys/class/net/'+HOSTS[h][3]+'/address").read_text().strip(),"link":subprocess.check_output(["iw","dev",'+repr(HOSTS[h][3])+',"link"],text=True)}))'
            v=self.runpy(h,code,timeout=12)
            if v['mac']!=HOSTS[h][4]:raise RuntimeError('peer identity mismatch '+h)
            for candidate in [OTHER,SR2]:
                if 'SSID: '+candidate+'\n' in v['link']:return candidate
            raise RuntimeError('peer has no recognised AP '+h)
        states={h:prior_ap for h in ['12','10']} if was_verified and prior_ap in [OTHER,SR2] else {}
        # Inspect the actual association; a previous dispatch may have switched
        # one or both peers before its SSH verification timed out.
        for candidate in ([] if len(states)==2 else [ap,SR2 if ap==OTHER else OTHER]):
            self.lab.select(candidate)
            for h in ['12','10']:
                if h in states:continue
                for _ in range(2):
                    try:
                        actual=probe(h)
                        if actual==candidate:states[h]=actual;break
                    except (RuntimeError,subprocess.TimeoutExpired):time.sleep(.3)
            if len(states)==2:break
        if len(states)!=2:raise RuntimeError('cannot locate both competitor peers: '+str(states))
        for current in [OTHER,SR2]:
            moving=[h for h in ['12','10'] if states[h]==current and current!=ap]
            if not moving:continue
            self.lab.select(current)
            for h in moving:
                self.lab.put(h,self.sessions[h]['folder']+'/command.json',json.dumps({'id':time.time_ns(),'action':'ax' if ap==OTHER else 'sr2'}).encode(),root=True)
        self.lab.select(ap);deadline=time.monotonic()+55;verified=set();errors={}
        while time.monotonic()<deadline:
            for h in ['12','10']:
                if h in verified:continue
                try:
                    if probe(h)==ap:
                        self.lab.ssh(h,'iw dev '+HOSTS[h][3]+' set power_save off',root=True,timeout=12)
                        verified.add(h)
                except (RuntimeError,subprocess.TimeoutExpired) as e:errors[h]=str(e)
            if len(verified)==2:break
            self.status('preparing_AP',target_AP=ap,verified_peers=sorted(verified));time.sleep(.5)
        if len(verified)!=2:raise RuntimeError('AP transition verification timed out '+str(errors))
        self.pair_ap=ap;self.peer_state_verified=True
        write(self.base/'pair_ap.json',{'ap':ap,'verified_peers':sorted(verified),'verified_wall':time.time()})
        self.lab.select(OTHER)
        if ap==OTHER:self.peer_clocks()
    def peer_clocks(self):
        for h in ['12','10']:
            cfgpath=self.sessions[h]['folder']+'/baseline.json'
            code='from pathlib import Path;import json,subprocess;p=Path("/etc/chrony/conf.d/rospacer-w2.conf");b=Path('+repr(cfgpath)+');c=json.loads(b.read_text())\nif p.exists() and not c.get("owned_chrony"):raise ValueError("preserve existing clock config")\nif not c.get("owned_chrony"):\n p.write_text("server 192.168.0.5 iburst minpoll 0 maxpoll 2 prefer\\n");c["owned_chrony"]=True;b.write_text(json.dumps(c));subprocess.run(["systemctl","restart","chrony"],check=True)\nsubprocess.run(["chronyc","burst","4/4"],capture_output=True);print("{}")'
            self.runpy(h,code,root=True,timeout=85)
        time.sleep(4)
        for h in ['12','10']:self.lab.ssh(h,'chronyc makestep',root=True)
    def launch(self,h,kind,suffix,argv=None,root=False,**fields):
        folder=self.folder(h,suffix);task={'kind':kind,'folder':folder,'cwd':self.lab.home(h),'argv':argv,'timeout':fields.pop('timeout',170),**fields}
        self.put(h,folder+'/task.json',json.dumps(task).encode())
        args=['sudo','-n'] if root else []
        args+=['python3',self.lab.home(h)+'/tools/w2_worker.py','--task',folder+'/task.json']
        r=self.runpy(h,'import subprocess,json;from pathlib import Path;p=Path('+repr(folder)+');q=subprocess.Popen('+repr(args)+',stdin=subprocess.DEVNULL,stdout=open(p/"wrapper.log","w"),stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps({"pid":q.pid}))')
        self.jobs.append((h,folder,r['pid']));return folder
    def wait(self,h,folder,limit=190):
        end=time.monotonic()+limit
        while time.monotonic()<end:
            try:
                r=self.runpy(h,'import json;from pathlib import Path;p=Path('+repr(folder+'/done.json')+');print(p.read_text() if p.exists() else "null")')
                if r is not None:return r
            except (RuntimeError,subprocess.TimeoutExpired):pass
            if time.monotonic()-self.last_status>20:self.status('running_trial',waiting_host=h,waiting_job=folder.rsplit('/',1)[-1])
            time.sleep(2)
        raise RuntimeError('job did not finish '+h+' '+folder)
    def calibrate_t1(self):
        self.lab.select(OTHER)
        for h in ['4','5']:self.lab.ssh(h,'sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304',root=True)
        home=self.lab.home('4');bundle=self.folder('4','calibration_t1')
        args=['sudo','-n','python3','-m','rospacer','sender-calibrate','--dev','wlp2s0','--source','192.168.0.4','--peer','192.168.0.5','--peer-ssh','csi@fe80::4f91:cec0:78f5:cc75%wlp2s0','--ssh-key','/home/csilab/.ssh/id_ed25519_rospacer_cal','--known-hosts','/home/csilab/.ssh/rospacer_cal_known_hosts','--host-key-alias','192.168.0.5','--out',bundle,'--socket-bytes','1048576','--seconds','15','--hz','30']
        job=self.launch('4','command','calibration_job',args,timeout=130);done=self.wait('4',job,150)
        self.archive('4',job,self.base/'calibration_job')
        if done['rc']:raise RuntimeError('fresh calibration failed')
        self.archive('4',bundle,self.base/'calibration_t1')
        args=['sudo','-n','python3','-m','rospacer','sender-validate','--dev','wlp2s0','--source','192.168.0.4','--peer','192.168.0.5','--peer-ssh','csi@fe80::4f91:cec0:78f5:cc75%wlp2s0','--ssh-key','/home/csilab/.ssh/id_ed25519_rospacer_cal','--known-hosts','/home/csilab/.ssh/rospacer_cal_known_hosts','--host-key-alias','192.168.0.5','--out',self.folder('4','validation_t1_Clean'),'--bundle',bundle,'--condition','Clean','--socket-bytes','1048576','--seconds','15']
        job=self.launch('4','command','validation_job',args,timeout=70);done=self.wait('4',job,85);self.archive('4',job,self.base/'validation_job');self.archive('4',self.folder('4','validation_t1_Clean'),self.base/'validation_t1_Clean')
        if done['rc']:raise RuntimeError('fresh independent validation execution failed')
        require_qualification(self.base/'calibration_t1/profile.json',[self.base/'validation_t1_Clean/validation.json'])
        return json.loads((self.base/'calibration_t1/profile.json').read_text())
    def prepare_t3(self):
        from w2_multi_cal import calibrate
        self.ap_pair(OTHER);self.lab.select(OTHER);results={}
        for h in ['12','10']:
            cfgpath=self.sessions[h]['folder']+'/baseline.json'
            code='from pathlib import Path;import json,subprocess;p=Path("/etc/chrony/conf.d/rospacer-w2.conf");b=Path('+repr(cfgpath)+');c=json.loads(b.read_text())\nif p.exists() and not c.get("owned_chrony"):raise ValueError("preserve existing clock config")\np.write_text("server 192.168.0.5 iburst minpoll 0 maxpoll 2 prefer\\n");c["owned_chrony"]=True;b.write_text(json.dumps(c));subprocess.run(["systemctl","restart","chrony"],check=True);print("{}")'
            self.runpy(h,code,root=True)
        for h in ['4','5']:
            self.status('calibrating_T3',sender=h)
            try:results[h]=calibrate(self,h)
            except Exception as e:
                write(self.base/'T3_calibration.json',{'passed':False,'completed':results,'error':str(e),'no_refit_after_validation':True});raise
        qualified=all(x['independent_validation']['passed'] for x in results.values())
        write(self.base/'T3_calibration.json',{'collection_complete':True,'passed':qualified,'adaptive_qualified':qualified,'results':results,'role_mapping':{'senders':['4','5'],'receivers':['12','10']},'scope':'two-reader operating budget only; failed gates block Adaptive, not empirical Static/Fixed'})
    def endpoints(self,row):
        pubs,subs=topology(row['topology']);return pubs,subs
    def trial(self,row):
        self.active=row.get('planned_id',row['id']);self.active_artifact=row['id'];self.current_row=row;self.status('running_trial',row=row)
        condition=row['condition'];self.ap_pair(SR2 if condition=='B2' else OTHER if row['topology']=='T3' or condition in ['F','C2'] else SR2)
        self.lab.select(OTHER);pubs,subs=self.endpoints(row);allhosts=pubs+subs
        local=self.base/'trials'/row['id'];local.mkdir(parents=True,exist_ok=False)
        if row['topology']=='T3':
            from w2_multi_cal import dds_trial
            return dds_trial(self,row)
        cal=json.loads((self.base/'calibration_t1/profile.json').read_text());C0=cal['capacity_payload_Bps'];rtt=json.loads((self.base/'calibration_t1/rtt.json').read_text())['rtt_s']
        hz=row['rho']*C0/(row['payload']*len(subs));count=math.ceil(hz*row['seconds']);cfg=synthesize(row['payload'],hz,len(subs),C0,rtt,1)
        ips={'4':'192.168.0.4','5':'192.168.0.5','12':'192.168.0.12','10':'192.168.0.10'}
        topic=topic_name(row['id']);remote={};configs={};extra_delay=40 if condition=='B2' else 0;duration=row['seconds']+row['warmup']+row['drain']+58+extra_delay
        for h in allhosts:
            self.lab.ssh(h,'iw dev '+HOSTS[h][3]+' set power_save off',root=True)
            q=json.loads(self.lab.ssh(h,'tc -j qdisc show dev '+HOSTS[h][3]).decode())
            if not all(x['kind']=='noqueue' for x in q):raise RuntimeError('unrestored qdisc '+h)
            mode=row['mode'];maxrx=212992 if mode in ['default','static_minus_f4'] else 2147483647 if mode in ['vendor','vendor_fc'] and row['rmw']=='cyclonedds' else max(4194304,cfg['socket_rx_bytes'])
            maxtx=212992 if mode in ['default','static_minus_f4'] else max(4194304,cfg['socket_tx_bytes'])
            self.lab.ssh(h,f'sysctl -w net.core.rmem_max={maxrx} net.core.wmem_max={maxtx}',root=True)
            if mode in ['vendor','vendor_fc'] and row['rmw']=='cyclonedds':self.lab.ssh(h,'sysctl -w net.ipv4.ipfrag_time=3 net.ipv4.ipfrag_high_thresh=134217728',root=True)
            else:
                baseline=json.loads(self.get(h,self.sessions[h]['folder']+'/baseline.json'))
                self.lab.ssh(h,'sysctl -w '+' '.join(k+'='+str(v) for k,v in baseline['sysctl'].items() if k.startswith('net.ipv4.ipfrag')),root=True)
            pcfg={**cfg,'dev':HOSTS[h][3],'peers':[ips[s] for s in subs],'middleware':row['rmw'],'cap_packet_Bps':min(cfg['cap_packet_Bps'],cal['ceiling_packet_Bps'])}
            if h in pubs:
                bundle=self.folder(h,'trials/'+row['id']+'/bundle');self.put(h,bundle+'/governor.json',json.dumps(pcfg).encode())
                for name in ['profile.json','manifest.json']:self.put(h,bundle+'/'+name,(self.base/'calibration_t1'/name).read_bytes())
                self.put(h,bundle+'/validation.json',(self.base/'validation_t1_Clean/validation.json').read_bytes())
                configs[h]=bundle
            peers=[ips[x] for x in allhosts if x!=h];file=local/(h+'.xml');profile(pcfg,row['rmw'],mode,file,HOSTS[h][3],ips[h],peers,55620+int(h),[55620+int(x) for x in allhosts if x!=h])
            remote[h]=self.folder(h,'trials/'+row['id']);self.put(h,remote[h]+'/middleware.xml',file.read_bytes());self.put(h,remote[h]+'/config.json',json.dumps(pcfg).encode())
            self.launch(h,'sampler','trials/'+row['id']+'/telemetry',root=True,dev=HOSTS[h][3],duration=duration)
        reference_now=self.runpy('5','import json,time;print(json.dumps({"wall":time.time()}))')['wall']
        nominal=reference_now+40+extra_delay;measure=nominal+row['warmup'];measure_pc_monotonic=time.monotonic()+40+extra_delay+row['warmup'];govern={}
        for h in pubs:
            if row['mode'] in ['fixed','adaptive']:
                args=['sudo','-n','python3','-m','rospacer','sender-govern','--bundle',configs[h],'--validation',configs[h]+'/validation.json','--out',remote[h]+'/govern','--seconds',str(min(180,duration)),'--mode',row['mode']]
                govern[h]=self.launch(h,'command','trials/'+row['id']+'/govern_job',args,timeout=duration+10)
        for h in subs:
            self.endpoint(row,h,'sub',remote[h],hz,count,topic,nominal)
        time.sleep(1)
        impairment=None
        if condition in ['F','C2','B2']:
            if condition=='B2':self.lab.select(SR2)
            for h in ['12','10']:
                self.lab.ssh(h,'iw dev '+HOSTS[h][3]+' set power_save off',root=True)
                self.lab.ssh(h,'sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304',root=True)
            phases=competition_schedule(condition,row['seconds'])
            server=self.launch('10','iperf_server','trials/'+row['id']+'/competitor_server',source=ips['10'] if condition!='B2' else '192.168.0.4',ports=[p['port'] for p in phases if p['port'] is not None],duration=duration+12)
            ready_until=time.monotonic()+8
            while time.monotonic()<ready_until:
                ready=self.runpy('10','from pathlib import Path;import json;p=Path('+repr(server+'/ready.json')+');print(p.read_text() if p.exists() else "null")')
                if ready and ready.get('ready'):break
                time.sleep(.2)
            else:raise RuntimeError('competitor listeners did not become ready')
            target=measure
            if condition=='B2':
                # SR2 has no wire/NTP path to the reference; convert a remaining
                # delay using a bracketed source-clock anchor, never PC wall time.
                before=time.monotonic();anchor=self.runpy('12','import json,time;print(json.dumps({"wall":time.time()}))')['wall'];mid=(before+time.monotonic())/2;target=anchor+max(1,measure_pc_monotonic-mid)
            impairment=self.launch('12','impairment','trials/'+row['id']+'/impairment',root=False,condition=condition,start_wall=target,seconds=row['seconds'],dev='wlo1',source=ips['12'] if condition!='B2' else '192.168.0.3',peer=ips['10'] if condition!='B2' else '192.168.0.4',port=55944,C0=C0)
            self.lab.select(OTHER)
        elif condition=='D3':
            impairment=self.launch('5','impairment','trials/'+row['id']+'/impairment',root=True,condition='D3',start_wall=measure,seconds=row['seconds'],dev='wlp2s0',connection=self.sessions['5']['original_connection'])
        pub_jobs={h:self.endpoint(row,h,'pub',remote[h],hz,count,topic,nominal,len(subs)) for h in pubs}
        # Refresh status without agent activity while the finite endpoint jobs run.
        for h in pubs:
            done=self.wait(h,pub_jobs[h],duration+25)
            if done.get('rc')!=0:
                tail=self.get(h,pub_jobs[h]+'/job.log').decode(errors='replace')[-1600:]
                raise RuntimeError('publisher failed rc='+str(done.get('rc'))+': '+tail)
        for h in subs:
            done=self.wait(h,remote[h]+'/sub_job',duration+25)
            if done.get('rc')!=0:raise RuntimeError('subscriber job failed host'+h+'; raw logs retained')
        for h in allhosts:
            done=self.wait(h,remote[h]+'/telemetry',duration+25)
            if done.get('rc')!=0:raise RuntimeError('telemetry collection failed host'+h+'; raw logs retained')
        for h in pubs:
            if h in govern:self.wait(h,govern[h],duration+25)
        for h in allhosts:self.archive(h,remote[h],local/h)
        if impairment:
            if condition=='B2':self.lab.select(SR2)
            self.wait('5' if condition=='D3' else '12',impairment,20)
            self.archive('5' if condition=='D3' else '12',impairment,local/'impairment')
            if condition!='D3':
                server_done=self.wait('10',server,30);self.archive('10',server,local/'competitor_server')
                if server_done.get('rc')!=0:raise RuntimeError('competitor server lifecycle failed')
            self.lab.select(OTHER)
        pub=json.loads((local/'4/pub.json').read_text());sub=json.loads((local/'5/sub.json').read_text())
        clocks=[[json.loads(s) for s in (local/h/'telemetry/clock.jsonl').read_text().splitlines()] for h in ['4','5']]
        stamps=[v for r in sub['records'] for k,v in r.items() if k in ['publisher_wall_ns','arrival_wall_ns']]
        clock=qualify_pair(*clocks,min(stamps) if stamps else 0,max(stamps) if stamps else 0)
        metrics=analyze_pair(pub,sub,clock);libraries={}
        for h,role in [('4','pub'),('5','sub')]:
            metadata=json.loads((local/h/(role+'.metadata.json')).read_text());actual=metadata['libraries']
            valid=bool(actual) and all('/runtime_w2/'+row['rmw']+'/' in path or '/runtime_w1_45/'+row['rmw']+'/' in path for path in actual) and all(self.expected.get('runtime_w1_45/'+row['rmw']+'/'+Path(path).name)==digest for path,digest in actual.items())
            libraries[h]={'valid':valid,'actual':actual}
            if not valid:raise RuntimeError('runtime closure mismatch '+h)
        q=json.loads(self.lab.ssh('4','tc -j qdisc show dev wlp2s0').decode())
        if not all(x['kind']=='noqueue' for x in q):raise RuntimeError('shaper restoration failed')
        r={'id':row['id'],'status':'measured','row':row,'cfg':cfg,'clock':clock,'metrics':metrics,'libraries':libraries,'published':pub['succeeded'],'received':sub['unique_received'],'goodput_Mbps':(metrics['arrival_interval_goodput_Bps'] or 0)*8/1e6,'p99_ms':(metrics['end_to_end_latency_ms'] or {}).get('p99'),'jitter_p99_ms':metrics['arrival_jitter_ms']['p99'],'reason':'' if clock['validated'] else 'E2E latency excluded: clock gate','qdisc_restored':True,'C0_Mbps':C0*8/1e6,'requested_hz':hz,'normal_period_goodput_Mbps':None}
        start=json.loads((local/'4/pub.start.json').read_text());r['actual_start_offset_s']=start['wall_ns']/1e9-measure
        if abs(r['actual_start_offset_s'])>1:r['timing_gate']=False;r['status']='timing_unqualified';r['reason']='measurement start deviates >1s from impairment schedule'
        if clock['validated']:
            first=start['wall_ns'];last=first+round(row['seconds']*1e9);n=len({x['seq'] for x in sub['records'] if first<=x['arrival_wall_ns']<last});r['normal_period_goodput_Mbps']=n*row['payload']*8/row['seconds']/1e6
        if condition in ['F','C2','B2']:
            events=json.loads((local/'impairment/impairment.json').read_text());r['impairment_events']=events
            if any(x.get('rc') not in [None,0] for x in events):r['status']='impairment_unqualified';r['reason']='competitor client failed'
            clients=list((local/'impairment').glob('competition_*.json'));udp_started=False;phase_evidence={}
            for f in clients:
                try:
                    data=json.loads(f.read_text());proven=any(s.get('bytes',0)>10000 for interval in data.get('intervals',[]) for s in interval.get('streams',[]));udp_started|=proven;phase_evidence[f.stem.split('_')[-1]]=proven
                except ValueError:pass
            r['competitor_UDP_proven']=udp_started
            if not udp_started:r['status']='impairment_unqualified';r['reason']='no competitor UDP payload evidence'
            r['competitor_phase_evidence']=phase_evidence
            if any(not phase_evidence.get(str(p['offset'])) for p in competition_schedule(condition,row['seconds']) if p['factor']!=0):r['status']='impairment_unqualified';r['reason']='missing UDP payload evidence in a required competition phase'
            if any(abs(x['wall_ns']/1e9-(target+x['offset']))>1 for x in events):r['status']='timing_unqualified';r['reason']='competition dispatch deviates >1s from schedule'
            if condition=='F':
                from w2_analysis import f_windows
                r['F_phase_metrics']=f_windows(pub,sub,start['wall_ns'],clock_validated=clock['validated'])
        if condition=='D3':
            events=json.loads((local/'impairment/impairment.json').read_text());r['outage']=events
            if len(events)==2:r['recovery']=recovery_metric(sub,{'outage_started_monotonic_ns':events[0]['monotonic_ns'],'outage_ended_monotonic_ns':events[1]['monotonic_ns']},clock)
        for h in govern:
            r.setdefault('govern',{})[h]=json.loads((local/h/'govern/summary.json').read_text())
            trace=list(csv.DictReader((local/h/'govern/trace.csv').open()))
            if not trace or float(trace[0]['monotonic_s'])>pub['measurement_started_ns']/1e9 or float(trace[-1]['monotonic_s'])<pub['measurement_ended_ns']/1e9-.6:
                raise RuntimeError('HTB does not cover entire measurement')
            normal=[x for x in trace if pub['measurement_started_ns']/1e9<=float(x['monotonic_s'])<=pub['measurement_ended_ns']/1e9]
            r['govern'][h]['normal_update_fraction']=sum(x['status']=='updated' for x in normal)/len(normal) if normal and row['mode']=='adaptive' else None
            r['govern'][h]['normal_trace_samples']=len(normal)
            r['govern'][h]['cap_Mbps_range']=[min(float(x['cap_packet_Bps']) for x in trace)*8/1e6,max(float(x['cap_packet_Bps']) for x in trace)*8/1e6] if trace else None
            drops=[]
            for x in trace:
                for q in json.loads(x['qdisc_json']):
                    if q['kind']=='fq':drops.append(q.get('drops',0))
            r['govern'][h]['fq_drop_max']=max(drops,default=None)
            if not r['govern'][h]['restored'] or r['govern'][h]['error'] not in [None,'']:raise RuntimeError('governor lifecycle failed')
        write(local/'summary.json',r);return r
    def endpoint(self,row,h,role,folder,hz,count,topic,nominal,readers=1,prefix=None,barrier=False):
        home=self.lab.home(h);env='source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; unset CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML FASTDDS_BUILTIN_TRANSPORTS; '
        env+='export ROS_DOMAIN_ID=81 RMW_IMPLEMENTATION='+('rmw_fastrtps_cpp' if row['rmw']=='fastdds' else 'rmw_cyclonedds_cpp')+' LD_LIBRARY_PATH='+home+'/runtime_w2/'+row['rmw']+':$LD_LIBRARY_PATH; '
        xml=folder+'/middleware'+('_'+prefix if prefix else '')+'.xml';name=prefix or role
        env+=('export FASTRTPS_DEFAULT_PROFILES_FILE='+xml+' RMW_FASTRTPS_USE_QOS_FROM_XML=1; ' if row['rmw']=='fastdds' else 'export CYCLONEDDS_URI=file://'+xml+'; ')
        args=['python3','tools/w2_traffic.py',role,'--hz',str(hz),'--count',str(count),'--seconds',str(row['seconds']),'--out',folder+'/'+name+'.json','--bytes',str(row['payload']),'--topic',topic,'--start-wall',str(nominal),'--warmup-seconds',str(row['warmup']),'--drain-seconds',str(row['drain']),'--discovery-seconds','20','--min-readers',str(readers),'--continue-on-publish-error']
        if barrier:
            args+=['--start-marker',folder+'/measurement.go.json']
            if role=='pub':args+=['--ready-path',folder+'/pub.warmup_ready.json']
        host_wall=self.runpy(h,'import json,time;print(json.dumps({"wall":time.time()}))')['wall']
        timeout=max(row['seconds']+row['warmup']+row['drain']+45,math.ceil(nominal+row['warmup']+row['seconds']+row['drain']+15-host_wall))
        if barrier:timeout+=60
        return self.launch(h,'command','trials/'+row['id']+'/'+name+'_job',['bash','-c',env+'exec '+shlex.join(args)],timeout=timeout)
    def cleanup_trial(self):
        self.recovery_jobs=list(self.jobs)
        self.lab.select(OTHER)
        for h,folder,pid in self.jobs:
            try:
                if h in ['12','10'] and self.pair_ap==SR2:self.lab.select(SR2)
                else:self.lab.select(OTHER)
                code='import os,signal,json;from pathlib import Path;p='+str(pid)+';f=Path("/proc")/str(p)/"cmdline";owned=Path('+repr(folder+'/process.json')+')\nif f.exists() and "w2_worker.py" in f.read_text(errors="replace").replace("\\0"," "):\n if owned.exists():\n  c=json.loads(owned.read_text());stat=Path("/proc")/str(c["pid"])/"stat"\n  if stat.exists() and stat.read_text().split()[21]==c["start_token"]:\n   try:os.killpg(c["pid"],signal.SIGTERM)\n   except ProcessLookupError:pass\n os.killpg(p,signal.SIGTERM)\nprint("{}")'
                self.runpy(h,code,root=True)
            except Exception:pass
        # Keep partial logs for every owned job, including failed dispatches.
        if self.active:
            for h in sorted({x[0] for x in self.jobs}):
                try:
                    self.lab.select(SR2 if h in ['12','10'] and self.pair_ap==SR2 else OTHER)
                    artifact=self.active_artifact or self.active
                    self.archive(h,self.folder(h,'trials/'+artifact),self.base/'trials'/artifact/h)
                except Exception:pass
        self.jobs=[];self.lab.select(OTHER)
        for h in ['4','5']:
            try:self.lab.ssh(h,'tc qdisc del dev wlp2s0 root handle 7ac0:',root=True)
            except Exception:pass
    def verify_case_isolation(self):
        """No traffic generation: validate cleanup before retry/skip/next case."""
        evidence=[];jobs=list(getattr(self,'recovery_jobs',[]))
        for round_number in range(1,3):
            if round_number>1:
                self.jobs=list(jobs);self.cleanup_trial();time.sleep(2)
            self.status('checking_environment',recovery_round=round_number)
            hosts={}
            for ap,group in [(OTHER,['4','5']),(self.pair_ap if self.pair_ap in [OTHER,SR2] else SR2,['12','10'])]:
                for h in group:
                    try:
                        self.lab.select(ap)
                        code='import sys,json;sys.path.insert(0,'+repr(self.lab.home(h)+'/tools')+');from w2_case_health import audit;print(json.dumps(audit('+repr(HOSTS[h][3])+','+repr(HOSTS[h][4])+','+repr(ap)+','+repr(self.sessions[h]['folder'])+')))'
                        hosts[h]=self.runpy(h,code,root=True,timeout=35)
                    except Exception as e:hosts[h]={'passed':False,'error':str(e)}
            try:self.lab.select(OTHER)
            except Exception as e:hosts['control_AP']={'passed':False,'error':str(e)}
            passed=all(x.get('passed') for x in hosts.values()) and all(h in hosts for h in HOSTS)
            evidence.append({'round':round_number,'passed':passed,'hosts':hosts})
            if passed:break
        proof={'passed':passed,'checks':evidence}
        artifact=self.active_artifact or self.active or 'idle'
        write(self.base/'trials'/artifact/'case_isolation.json',proof)
        return proof
    def restore(self):
        self.cleanup_trial();record={}
        try:self.ap_pair(OTHER)
        except Exception:pass
        # Remove our temporary key while the wire is still present. The peer's
        # existing key remains available after restoration.
        try:
            access=json.loads((self.base/'direct4.json').read_text())
            if access['added']:self.runpy('4','from pathlib import Path;p=Path.home()/".ssh/authorized_keys";s=p.read_text().splitlines();p.write_text("\\n".join(x for x in s if x!='+repr(access['line'])+')+"\\n");print("{}")')
        except Exception as e:record['temporary_key_cleanup']={'error':str(e)}
        # A synchronous end command loses its reply when a guard changes AP
        # or removes the management address. Request then audit on baseline AP.
        for h in ['12','10','4','5']:
            try:
                self.lab.select(OTHER if h in ['4','5'] or self.pair_ap==OTHER else SR2)
                self.put(h,self.sessions[h]['folder']+'/end',b'') if h not in ['12','10'] else self.lab.put(h,self.sessions[h]['folder']+'/end',b'',root=True)
                # 4/5 folders are user-owned, so a marker needs no extra grant.
            except Exception as e:record[h]={'restored':False,'request_error':str(e)}
        time.sleep(12)
        self.lab.wired=False;self.lab.direct4=False
        for ap,hosts in [(SR2,['12','10']),(OTHER,['4','5'])]:
            self.lab.select(ap)
            for h in hosts:
                try:
                    code='from pathlib import Path;import time;p=Path('+repr(self.sessions[h]['folder']+'/restoration.json')+')\nfor _ in range(75):\n if p.exists():break\n time.sleep(1)\nprint(p.read_text())'
                    record[h]=self.runpy(h,code,root=True,timeout=85)
                except Exception as e:record[h]={**record.get(h,{}),'restored':False,'audit_error':str(e)}
        self.lab.select(OTHER);write(self.base/'restoration.json',record)
        return record

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','smoke','run','restore']);p.add_argument('--base',required=True);a=p.parse_args();r=Runner(a.base)
    if a.action=='prepare':
        r.status('preparing');r.deploy();cal=r.calibrate_t1();r.status('calibration_passed',C0_Mbps=cal['capacity_payload_Bps']*8/1e6);return
    if a.action=='restore':r.restore();return
    if a.action=='smoke':
        for rmw,mode in [('fastdds','static'),('cyclonedds','static'),('fastdds','adaptive'),('fastdds','vendor'),('fastdds','vendor_fc')]:
            row={'id':'smoke_v2_'+rmw+'_'+mode,'stage':'smoke','topology':'T1','condition':'E','rho':.2,'mode':mode,'rmw':rmw,'rep':0,'seconds':8,'warmup':2,'drain':3,'payload':1048576,'intent':'complete'}
            try:
                z=r.trial(row);r.results.append(z);r.status('smoke_running');print(json.dumps({k:z[k] for k in ['id','status','published','received','p99_ms']}),flush=True)
                if z['status']!='measured' or not z['received'] or not z['clock']['validated']:raise RuntimeError('smoke gate failed')
            finally:r.cleanup_trial()
        write(r.base/'smoke_ready.json',{'passed':True,'results':r.results,'wall':time.time()});return
    for marker in ['smoke_ready.json','extended_smoke_ready.json','final_paths_ready.json','prelaunch.json']:
        if not (r.base/marker).exists() or not json.loads((r.base/marker).read_text())['passed']:raise RuntimeError('validated smoke readiness required: '+marker)
    if (r.base/'continuation.json').exists() and (not (r.base/'resume_ready.json').exists() or not json.loads((r.base/'resume_ready.json').read_text())['passed']):raise RuntimeError('repaired-path smoke readiness required')
    if (r.base/'continuation.json').exists():
        c=json.loads((r.base/'continuation.json').read_text(encoding='utf-8'))
        if c.get('T3_barrier_protocol') and not json.loads((r.base/'resume_ready.json').read_text(encoding='utf-8')).get('T3_barrier_verified'):raise RuntimeError('new T3 common-start protocol must be verified first')
        ap_proof=r.base/'AP_transition_verified.json'
        if not ap_proof.exists() or not json.loads(ap_proof.read_text())['passed']:raise RuntimeError('both AP transition directions must be verified first')
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    # Windows kernel byte lock prevents two orchestrators from overlapping.
    import msvcrt
    hardware_lock=open(ROOT/'runs/w2_hardware.lock','a+b');hardware_lock.seek(0);hardware_lock.write(b'1');hardware_lock.flush();hardware_lock.seek(0);msvcrt.locking(hardware_lock.fileno(),msvcrt.LK_NBLCK,1)
    lock=open(r.base/'campaign.lock','a+b');lock.seek(0);lock.write(b'1');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    r.freeze_sources()
    rows=matrix(3);r.all_rows=rows;write(r.base/'matrix.json',rows);write(r.base/'runner_identity.json',{'pid':os.getpid(),'started_UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'independent_of_codex':True,'reps':3,'optional_reps_4_5':'not scheduled; human review required; selection is exploratory'})
    write(ROOT/'runs/w2_current.json',{'base':str(r.base),'pid':os.getpid(),'progress':str(r.base/'progress.json'),'report':str(r.base/'W2 실험 진행 및 결과.html')})
    records={}
    for row in rows:
        p=r.base/'trials'/row['id']/'summary.json'
        if p.exists():records[row['id']]=json.loads(p.read_text(encoding='utf-8'))
    r.results=[records[x['id']] for x in rows if x['id'] in records]
    pending=[x for x in rows if records.get(x['id'],{}).get('status') not in TERMINAL]
    r.eta_hours=len(pending)*205/3600
    started=time.monotonic()
    try:
        for i,row in enumerate(rows):
            if (r.base/'STOP').exists():raise RuntimeError('user STOP marker')
            file=r.base/'trials'/row['id']/'summary.json'
            if records.get(row['id'],{}).get('status') in TERMINAL:continue
            history_path=file.parent/'attempts.json';history=json.loads(history_path.read_text()) if history_path.exists() else []
            for retry in range(2):
                number=len(history)+1
                while (r.base/'trials'/(row['id']+'__a'+str(number).zfill(3))).exists():number+=1
                actual={**row,'id':row['id']+'__a'+str(number).zfill(3),'planned_id':row['id'],'attempt_number':number}
                trial_begin=time.monotonic();z=None
                try:
                    if row['topology']=='T3' and not (r.base/'T3_calibration.json').exists():r.prepare_t3()
                    z=r.trial(actual);r.failures=0 if z['status']=='measured' else r.failures+1
                except ScopeError as e:z={'id':row['id'],'status':'blocked_scope','reason':str(e),'row':actual}
                except Exception as e:
                    r.failures+=1;z={'id':row['id'],'status':'failed','reason':str(e),'traceback':traceback.format_exc(),'row':actual}
                finally:
                    try:r.cleanup_trial()
                    except Exception as cleanup_error:
                        z=z or {'status':'failed','reason':'trial did not produce a result'}
                        z['cleanup_error']=str(cleanup_error)
                isolation=r.verify_case_isolation()
                decision=decide(z['status'],isolation['passed'],retry+1)
                z.update(case_isolation_passed=isolation['passed'],failure_policy_action=decision)
                z.update(id=row['id'],artifact_id=actual['id'],source_artifacts_root=str(r.base/'trials'/actual['id']),executed_row=z.get('row'),row=row,attempt_number=number,orchestration_elapsed_s=time.monotonic()-trial_begin)
                write(file.parent/('attempt_'+str(number).zfill(3)+'_summary.json'),z);history.append({'attempt':number,'artifact_id':actual['id'],'status':z['status'],'reason':z.get('reason')});write(history_path,history)
                z=summarize_record(z,decision)
                write(file,z);records[row['id']]=z;r.results=[records[x['id']] for x in rows if x['id'] in records];write(r.base/'results.json',r.results)
                durations=[x['orchestration_elapsed_s'] for x in r.results if x.get('status')=='measured' and 'orchestration_elapsed_s' in x][-10:]
                remaining=sum(records.get(x['id'],{}).get('status') not in TERMINAL for x in rows)
                r.eta_hours=remaining*(sum(durations)/len(durations) if durations else 205)/3600
                r.status('running',next_index=i+1,total=len(rows),elapsed_hours=(time.monotonic()-started)/3600)
                if decision=='halt':raise RuntimeError('shared environment isolation failed; inspect case_isolation.json')
                if decision in ['continue','skip']:break
                if (r.base/'STOP').exists():raise RuntimeError('user STOP marker')
        r.active=None;r.current_row=None;r.status('restoring',total=len(rows));rest=r.restore();r.status(('finished_with_skipped_cases' if any(x.get('status')=='skipped_failed' for x in r.results) else 'finished') if all(x.get('status') in TERMINAL for x in r.results) else 'finished_with_invalid_rows',total=len(rows),restoration=rest)
    except BaseException as e:
        rest=r.restore();r.status('stopped',reason=str(e),restoration=rest);raise
    finally:lock.close();hardware_lock.close();ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
