"""Build a self-contained W1 report from preserved evidence, including blockers."""
import base64,csv,hashlib,html,json,statistics,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
from deploy import ROOT

BASE=ROOT/'runs/w1_20261012_163000'
OUT=ROOT.parent/'html 파일 모음/결과/W1 구현 전제 검증_261012.html'

def read(path,default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def esc(x):return html.escape(str(x))
def num(v,d=2):return '미측정' if v is None else f'{v:,.{d}f}'
def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def link(path,label):
    import os
    return '<a href="'+Path(os.path.relpath(path,OUT.parent)).as_posix()+'">'+esc(label)+'</a>'

def figures(rows):
    sys.path.insert(0,str(ROOT.parent/'tmp/w1_plotdeps'))
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt,font_manager
    font=Path('C:/Windows/Fonts/malgun.ttf')
    if font.exists():font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams['axes.unicode_minus']=False
    bp=[r for r in rows if r['label'].startswith('bp_')]
    # Prefer corrected capture-qualified Cyclone runs when available.
    selected=[]
    for mw in ['fastdds','cyclonedds']:
        for label in ['bp_default100','bp_design']:
            options=[r for r in bp if r['rmw']==mw and r['label']==label]
            if options:selected.append(sorted(options,key=lambda r:'fragfix' in r['name'])[-1])
    if not selected:return ''
    fig,axes=plt.subplots(1,2,figsize=(11,4.2),layout='constrained')
    names=[('Fast' if r['rmw']=='fastdds' else 'Cyclone')+'\n'+('100' if 'default100' in r['label'] else '설계') for r in selected]
    x=list(range(len(selected)));colors=['#3973b9' if r['rmw']=='fastdds' else '#208070' for r in selected]
    axes[0].bar(x,[r['metrics']['delivery_requested']*100 for r in selected],color=colors)
    axes[0].set_xticks(x,names);axes[0].set_ylim(0,100);axes[0].set_ylabel('요청 기준 전달률 (%)');axes[0].set_title('미생성·발행 실패도 분모에 포함')
    axes[1].bar(x,[r['metrics']['publish_duration_ms']['p50'] for r in selected],color=colors)
    axes[1].set_xticks(x,names);axes[1].set_ylabel('publish() p50 (ms)');axes[1].set_title('동일 요청 부하·HTB 상한의 W1 관측')
    for ax in axes:ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    png=BASE/'backpressure_summary.png';fig.savefig(png,dpi=170);fig.savefig(BASE/'backpressure_summary.svg');plt.close(fig)
    return '<figure><img alt="W1 요청 기준 전달률과 publish 호출시간" src="data:image/png;base64,'+base64.b64encode(png.read_bytes()).decode()+'"><figcaption>각 조건 1회 예비 검증. 성능 순위·개선률의 통계적 근거로 사용하지 않는다. 원본 PNG·SVG는 run 폴더에 저장했다.</figcaption></figure>'

def main():
    rows=[read(p) for p in sorted(BASE.glob('*/summary.json')) if isinstance(read(p),dict) and read(p).get('rmw')]
    evidence=read(BASE/'evidence.json',{});cal=read(BASE/'calibration_ready/summary.json',{})
    packets=read(BASE/'packet_evidence.json',{});end=read(BASE/'end_receipt.json',{})
    kernel=read(BASE/'kernel_probe/12/summary.json',read(BASE/'kernel_probe/summary.json'))
    competition=read(BASE/'competition/summary.json',[])
    wifi_probe=read(BASE/'wifi_probe/summary.json',[])
    restored=bool(end) and all(r.get('rc')==0 and read_inline(r.get('stdout','{}')).get('restored') for r in end.values())
    bp=[r for r in rows if r['label'].startswith('bp_')]
    smokes=[r for r in rows if r['label'] in ['default','vendor','static','fixed'] and 'outage' not in r['name']]
    complete_smoke={r['rmw']+'/'+r['label'] for r in smokes if r['metrics']['delivery_requested']==1}
    checks=[
      ('환경·장비 신원','확인','12/10 및 4/5의 저장된 SSH 키, Ubuntu22.04.5, Humble, 커널·NIC·드라이버 기록. 관리·ROS 모두 Wi-Fi이므로 관리 트래픽 완전 분리는 미달성.'),
      ('실행 DDS 고정','확인','Fast DDS2.6.11·RMW6.2.10·Fast CDR1.0.29의 라이브러리16개를 W1 폴더에서 양쪽 동일 SHA로 로드. 시스템 패키지 자체는 다르며 변경하지 않음. Cyclone 실제 libddsc0.10.5 로드 확인.'),
      ('시간 동기·지연','미달성','10번 chrony 미동기화. 12번은 오래된 기준시각·큰 root dispersion. 유선 관리망 없음. 지연 p50/p95/p99를 만들지 않음.'),
      ('무선 active/busy/tx','차단','12/10 모두 root iw survey dump가 빈 출력. duration0도 유효 airtime이라고 취급하지 않음. 지원 관측 경로 필요.'),
      ('기본 링크 교정','수행','UDP30초×3, TCP30초, ping200, 동시 station/survey 기록. 외부 채널 점유율은 검증 못함. C0는 UDP수신 구간 byte 처리량의 중앙값.'),
      ('고정 비용 O','조건부','iperf UDP1400B로 맞춘 유효 O 약'+num(evidence.get('conditional_O_s',0)*1e6)+'µs. NIC의 순수 프리앰블/ACK 고정 비용으로 식별한 것은 아니며 적응형 교정 완료도 아님.'),
      ('plan·golden·XML','수행','golden 추가, 링크 용량 null 및 governor 실행 차단. 스키마 검사·실제 파서 시험은 각각 분리. Fast 원본 XSD 결함의 검증용 수정 사본 사용.'),
      ('손계산 대조','수정 필요','C=200Mb/s·1MiB·10Hz에서 alpha=0.9를 적용한 회복 상한은12,014,240B→11MiB. proposal13MiB 예제와 차이. prototype 수신 버퍼 하한·fq 여유도 별도 가정.'),
      ('W1 역압','관측 확보','HTB0.5C0, 요청0.8C0,1MiB,KEEP_ALL,30초,flow_limit100/설계. socket t가 tb근처, 큐 적체·publish 대기 관측. Fast 발행 오류는 완전 전달 가정의 반례이며 UDP 오류0만으로 기다림만 존재한다고 판정하지 않음.'),
      ('HTB·fq·큐 한도','부분 확인','실제 Wi-Fi의11.27Mb/s 상한은 class전송량으로 확인. 두 한도 모두drop0이므로 큰 한도의 우월성 미입증. 200Mb/s는 별도 veth 진단이며 실제 Wi-Fi 검증은 미달성.'),
      ('RTPS 소켓·단편화','수정·재검증','DATA/DATA_FRAG 캡처에서 사용자 송신 소스포트1개 확인. fq는 미연결 UDP의 목적지 hash로 흐름을 나눌 수 있어 소켓 수=flow 수라고 일반화하지 않음. 기존 Cyclone1408B에서 샘플당 첫 패킷 IP단편화 발견→1404B로 축소 후 Static/fixed 캡처에서 IP단편화0 확인.'),
      ('AP 중계·자기 부하0.2~0.8','차단','busy/active/tx 결측으로 beta_oth·중계 포함 여부를 판정할 수 없음. relay 항을 임의 선택하지 않음.'),
      ('B2·C2 모델 오차','일부 수행' if competition else '대기','C2 처리량 관측'+(' 확보' if competition else ' 준비')+'. airtime 추정값이 없어20% 오차 판정은 불가. B2는 다른 AP 채널·연결 구성 필요.'),
      ('비교군 시운전','수행 중' if len(complete_smoke)<8 else '확인',f'완전 수신한 arm {len(complete_smoke)}/8. Default/Vendor/Static/Static+fixed. 전체 ROSPacer adaptive는 차단. Vendor 초기 XML·메모리 정책 오류 기록 보존.'),
      ('종료·복원','확인' if restored else '확인 대기','qdisc,sysctl,Wi-Fi 절전,CPU governor 복원 영수증'+(' 확보' if restored else ' 미확보. 원격 접속 복구 후 확인 필요. 독립 복원 감시자1시간 제한.')),
      ('Zenoh 운영점','후속 단계','사용자 지정 개발 순서에 따라 Fast/Cyclone 검증 이후 진행. W1에서 수행했다고 표시하지 않음.')]
    title='W1 구현 전제 검증 · 2026-10-12'
    body='<header><span class="eyebrow">ROSPacer · Ubuntu22.04 / ROS2 Humble</span><h1>'+title+'</h1><p>전체 W1 완료 아님. 측정한 항목·구현 전제의 반례·추가 장비가 필요한 항목을 구분한 진행 보고서.</p><p class="small">갱신 '+datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M KST')+' · 원자료 '+link(BASE/'evidence.json','evidence.json')+'</p></header>'
    body+='<nav><a href="#gates">W1 판정</a><a href="#cal">링크 교정</a><a href="#bp">역압</a><a href="#smoke">비교군</a><a href="#rest">복원·재현</a></nav>'
    body+='<section id="gates"><h2>W1 항목별 답변</h2>'+table(['항목','현재 판정','근거와 한계'],[(esc(a),'<span class="badge">'+esc(b)+'</span>',esc(c)) for a,b,c in checks])+'</section>'
    body+='<section id="cal"><h2>링크 교정값</h2>'+table(['조건','수신 처리량(Mb/s)','방법'],[(esc(t['name']),num(t.get('receiver_bps',0)/1e6),esc('UDP1400B·30초' if t['name'].startswith('udp') else 'TCP30초')) for t in cal.get('trials',[])])
    body+='<p>C0 = <strong>'+num(cal.get('C0_UDP_receiver_median_bps',0)/1e6)+' Mb/s</strong>. iperf3 3.9의 server end-summary byte가0으로 기록되어 수신 interval byte/seconds로 계산했다. 원문 end-summary와 client/server JSON을 모두 보존했다.</p><details><summary>ping200회 원문</summary><pre>'+esc(cal.get('ping',{}).get('stdout',''))+'</pre></details>'
    body+='<p><strong>B2 미수행 사유:</strong> SR2는36번·80MHz이며 다른 AP(iptime5GAX1500)는149번이다. 사용자 확인상 관리자 계정 정보가 없어 채널 변경을 완료하지 못했다.36이라는 번호 자체보다 두 AP의 채널 대역을 겹치는 것이 필요하다. C2는같은 AP에서의 혼잡 실험이므로 B2를대체하지 않는다.</p>'
    if competition:body+='<h3>C2 혼잡 교정</h3>'+table(['조건','12→10 수신(Mb/s)','5→4 요청 부하(Mb/s)','추정 오차'],[(esc(r['trial']),num(r['receiver_bps']/1e6),num(r['contender_requested_bps']/1e6),'계수기 결측으로 미판정') for r in competition])
    body+='</section><section id="bp"><h2>동일 run의 역압 관측</h2>'+figures(rows)
    body+=table(['run','요청/성공/수신','publish p50(ms)','실제 발행(Hz)','송신UDP오류/fq drop','HTB 실측(Mb/s)'],[(link(BASE/r['name']/'summary.json',r['name']),f"{r['metrics']['requested']}/{r['metrics']['publish_succeeded']}/{r['metrics']['unique_received']}",num(r['metrics']['publish_duration_ms']['p50']),num(r['metrics']['actual_publish_hz']),f"{r['telemetry']['12']['udp_delta'].get('SndbufErrors')}/{r['telemetry']['12']['fq_drop_max']}",num(evidence.get('backpressure',{}).get(r['name'],{}).get('steady_HTB_class_Mbps'))) for r in bp])
    body+='<p>requested는30초 동안 예정된 샘플 수, 성공은publish 반환 성공, 수신은고유 seq 기준이다. 발행 대기가 긴 경우 예정 샘플을 모두 생성하지 못할 수 있다. 발행 실패·미생성을 전달률의 분모에서 제거하지 않았다. 0.1초 sampler의 실제 간격과 최대 수집시간도 각 run에 저장했다.</p>'
    body+='<h3>커널200Mb/s 진단</h3>'+(table(['조건','UDP수신 payload(Mb/s)'],[(esc(r['name']),num(r['receiver_udp_payload_Mbps'])) for r in kernel['trials']])+'<p>'+esc(kernel['scope'])+'</p>' if kernel else '<p>12번에서 실행 완료. 원격 파일 회수 대기.</p>')+'</section>'
    if wifi_probe:body+='<section><h2>실제 Wi-Fi의 HTB 부착·burst 진단</h2>'+table(['조건','UDP수신 payload(Mb/s)','상한(Mb/s)','종료 qdisc'],[(esc(r['name']),num(r['C_receiver_Mbps']),num(r['HTB_cap_Mbps']),esc(','.join(q['kind'] for q in r['root_after']))) for r in wifi_probe])+'<p>각10초의 단기 진단.200Mb/s 상한보다 낮은 링크에서 root 부착에 따른 처리량 손실을 비교한다.200Mb/s 실제 무선 상한 정확도의 증거로 해석하지 않는다. 별도 iperf UDP 포트만 테스트 class로 추가 분류했다.</p></section>'
    body+='<section id="smoke"><h2>비교군 시운전 · 요청 약0.538Hz ·1MiB</h2>'+table(['run','성공/요청','수신/요청','도착 간격 표준편차(ms)','종료 사유'],[(link(BASE/r['name']/'summary.json',r['name']),f"{r['metrics']['publish_succeeded']}/{r['metrics']['requested']}",f"{r['metrics']['unique_received']}/{r['metrics']['requested']}",num(r['metrics']['arrival_interval_ms']['stdev']),esc(r['metrics']['publisher_exit_reason'])) for r in smokes])
    body+='<p>지터는 고유 수신의 연속 도착 간격 표준편차로 계산했다. 지연 표준편차와 다르며, 유실·역압에 따른 간격 변화도 포함한다. 각 arm 1회·낮은 부하 시운전이므로 논문용 비교나 개선률로 사용하지 않는다. Vendor 재시도는 초기 오류 기록을 덮어쓰지 않는다. Cyclone Vendor는 fragmentation·WHC·소켓 버퍼를 적용한 범위이며 proposal의 전체 IP fragment 커널 튜닝은 수행하지 않았다.</p>'
    body+='<p>Fast Vendor의후속 시작 실패는 XMLQoS 플래그를켜고 endpoint 메모리 정책을명시하지 않아 PREALLOCATED가적용된 조건이었다. Vendor에서는 RMW 기본 메모리 정책을유지하도록 수정한뒤17/17 수신과 실제 TCP 사용자 데이터 경로를확인했다. Golden도양쪽 실제 노드·publisher 생성에성공했다.</p>'
    body+='<h3>캡처로 확인한 사용자 데이터 경로</h3>'+table(['run','사용자UDP 소스포트 수','DATA_FRAG 조각 크기(B)','사용자IP단편화 첫 패킷 수','TCPpayload 경로 수'],[(esc(name),str(len(r.get('user_udp_source_ports',{}))),esc(', '.join(r.get('user_fragment_sizes',{}))),str(r.get('user_IP_fragment_first_packets','미확인')),str(len(r.get('tcp_payload_endpoints',{})))) for name,r in packets.items()])
    outages=[r for r in rows if r.get('outage')]
    if outages:body+='<h3>단절·복구 지표 시운전</h3>'+table(['run','실제 UDP차단(s)','복원 후 첫 도착(s)','수신/요청','규칙 복원'],[(esc(r['name']),num(r['outage']['actual_outage_seconds'],3),num(r['outage']['first_arrival_after_restore_s'],3),f"{r['metrics']['unique_received']}/{r['metrics']['requested']}",str(r['outage']['events']['restored'])) for r in outages])+'<p>수신 단말의 단조 시계에서 계산한첫 도착 시간이며 전체 backlog가 비워진 회복시간과 다르다. SSH를유지하기 위해 지정 peer의UDP만 차단했다.</p>'
    body+='</section><section id="rest"><h2>복원·소스·재현성</h2><p>20개 자동 검사 통과. 교정·역압 첫 구현755d87e, 비교군 첫 시운전4aaef25, XML수정6de674e, 단절 준비5abaeb3. 이후 수정 commit과 run 연결은최종 manifest에 기록한다. 같은 실험 안에서 사용하는 소스를고정했으며 단계별 수정으로 재시도는별도 run이다.</p>'
    body+='<p>Fast 원본XSD2.6.10/2.6.11이동일 SHA이고 원본 검증 오류가 있어 문서화한 수정 사본으로 검사했다. 실제 노드 파서·로드 라이브러리·소켓 적용값은별도 검증한다. 측정기는RPBench가 아닌별도 rclpy 하네스이며 UInt8MultiArray를 사용했다. proposal의Image 하네스를완전히 대체했다고 주장하지 않는다.</p><details><summary>종료·복원 영수증</summary><pre>'+esc(json.dumps(end,indent=2,ensure_ascii=False))+'</pre></details>'
    body+='<p>'+link(BASE/'final_manifest.json','최종 코드·원자료 SHA manifest')+' · '+link(BASE/'run_provenance.json','실행 라이브러리·commit 근거')+' · '+link(BASE/'runtime_check.json','실제 로드 검사')+' · '+link(BASE/'source_audit/manifest.json','공식 소스 URL·SHA')+' · '+link(BASE/'packet_evidence.json','패킷 집계')+' · '+link(BASE/'final_audit.json','최종 장비 조회·Golden 파서')+'</p><h3>공식 소스 대조</h3>'
    sources=read(BASE/'source_audit/manifest.json',[])
    body+='<ul>'+''.join('<li><a href="'+esc(s['url'])+'">'+esc(s['file'])+'</a></li>' for s in sources if not s.get('error'))+'</ul></section>'
    style='body{font-family:Segoe UI,Malgun Gothic,sans-serif;background:#f4f6f9;color:#172538;margin:0;line-height:1.65}main{max-width:1180px;margin:auto;padding:32px 22px}header{background:#173552;color:white;padding:32px;border-radius:16px}h1{font-size:30px;margin:10px 0}h2{font-size:23px;margin:0 0 16px}h3{margin-top:26px}section{background:white;margin:24px 0;padding:26px;border-radius:14px;border:1px solid #dce3eb}nav{display:flex;gap:18px;flex-wrap:wrap;padding:22px 6px}a{color:#2167a1}header a{color:#c7e5ff}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:11px 13px;border-bottom:1px solid #dde4ed;text-align:left;vertical-align:top}th{background:#ecf2f8;white-space:nowrap}.scroll{overflow:auto}.badge{background:#eef2f8;padding:3px 9px;border-radius:15px;white-space:nowrap}.small,figcaption{font-size:13px;color:#708198}header .small{color:#d5e4ef}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f0f4f8;padding:16px;border-radius:8px}img{width:100%;height:auto}figure{margin:16px 0}details{margin:16px 0}.eyebrow{font-size:12px;letter-spacing:1px}footer{padding:15px;color:#65758a}@media(max-width:600px){main{padding:12px}section,header{padding:18px}h1{font-size:25px}}'
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>'+style+'</style><main>'+body+'<footer>원자료 기반 W1 진행 보고서 · 미수행 항목을완료로 표시하지 않음</footer></main></html>',encoding='utf-8')
    state={'generated_at_kst':datetime.now(timezone(timedelta(hours=9))).isoformat(),'report':str(OUT),'w1_complete':False,'backpressure_runs':len(bp),'successful_smoke_arms':sorted(complete_smoke),'restoration_verified':restored,'run_names':[r['name'] for r in rows]}
    (BASE/'report_state.json').write_text(json.dumps(state,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(state,ensure_ascii=False))

def read_inline(s):
    try:return json.loads(s)
    except Exception:return {}

if __name__=='__main__':main()
