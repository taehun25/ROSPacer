"""Frozen, local-only final W2 report. Does not access experimental equipment."""
import collections,csv,datetime,hashlib,html,json,math,statistics
from pathlib import Path
from w2_interim_report_261015 import table,esc,num,link

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runs/w2_20261015_resume1'
DEST=ROOT.parent/'html 파일 모음/결과/W2 실험결과'
OUT=DEST/'W2 실험 최종 결과 보고서_261015.html'
MODES=['default','vendor','vendor_fc','static','fixed','adaptive','static_minus_f4']
STAGES=['T1_E','T1_F','T3_E','P0_low_0.6','P0_low_1.0','P0_Clean','P0_C2','P0_D3','P0_D3_adaptive','P0_C2_F4','P0_B2']
LABELS={'T1_E':'T1 E · 1:1 과부하','T1_F':'T1 F · 경쟁 부하 변화','T3_E':'T3 E · 다중 송수신 과부하','P0_low_0.6':'P0 · 부하 0.6','P0_low_1.0':'P0 · 부하 1.0','P0_Clean':'P0 · Clean','P0_C2':'P0 · 같은 AP 경쟁 C2','P0_D3':'P0 · 단절 D3','P0_D3_adaptive':'P0 · D3 Adaptive 추가','P0_C2_F4':'P0 · 소켓 버퍼 설정 제거','P0_B2':'P0 · 다른 AP 간섭 B2'}

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def median(v):return statistics.median(v) if v else None
def stats(v):return {'median':median(v),'min':min(v) if v else None,'max':max(v) if v else None,'values':v}
def group(rows,stage):
    output=[]
    for rmw in ['fastdds','cyclonedds']:
        for mode in MODES:
            a=[r for r in rows if r['row']['stage']==stage and r['row']['rmw']==rmw and r['row']['mode']==mode and r['status']=='measured']
            if not a:continue
            item={'rmw':rmw,'mode':mode,'n':len(a),'ids':[r['id'] for r in a]}
            for key in ['normal_period_goodput_Mbps','p99_ms','jitter_p99_ms','published','received']:
                v=[r[key] for r in a if isinstance(r.get(key),(int,float))]
                item[key]=stats(v) if v else None
            item['delivery_successful_publish_pct']=[100*r['metrics']['delivery_successful_publish'] for r in a]
            item['delivery_requested_pct']=[100*r['metrics']['delivery_requested'] for r in a]
            output.append(item)
    return output
def span(v,d=2):
    return num(median(v),d)+' ['+num(min(v),d)+'–'+num(max(v),d)+']' if v else '—'
def detail(title,body):return '<details><summary>'+esc(title)+'</summary>'+body+'</details>'
def p(s):return '<p>'+s+'</p>'
def section(identifier,title,body):return '<section id="'+identifier+'"><h2>'+title+'</h2>'+body+'</section>'
def metric_table(groups):
    return table(['DDS','설정','n','측정창 처리량 Mb/s 중앙값 [범위]','p99 지연 ms 중앙값','지터 p99 ms 중앙값','발행 대비 수신율 % 중앙값 [범위]','요청 대비 수신율 % 중앙값'],[
        [x['rmw'],x['mode'],x['n'],span(x['normal_period_goodput_Mbps']['values']),num(x['p99_ms']['median']) if x['p99_ms'] else '제외',num(x['jitter_p99_ms']['median']),span(x['delivery_successful_publish_pct']),num(median(x['delivery_requested_pct']))] for x in groups])

def main():
    progress=read(BASE/'progress.json');restoration=read(BASE/'restoration.json');rows=read(BASE/'results.json');matrix=read(BASE/'matrix.json')
    assert progress['state'] in ['finished','finished_with_skipped_cases','finished_with_invalid_rows'] and progress['pending']==0,'Campaign is not finished; do not create a final report'
    assert len(rows)==len(matrix)==207
    assert all(restoration.get(h,{}).get('restored') for h in ['4','5','12','10'])
    counts=collections.Counter(r['status'] for r in rows)
    assert counts=={'measured':198,'blocked_scope':6,'skipped_failed':3},counts
    now=datetime.datetime.now().astimezone();ended=datetime.datetime.fromisoformat(progress['updated_UTC'].replace('Z','+00:00')).astimezone()
    grouped={stage:group(rows,stage) for stage in STAGES if stage!='T3_E'}
    for stage,groups in grouped.items():
        for g in groups:
            selected=[r for r in rows if r['id'] in g['ids']]
            for field in ['normal_period_goodput_Mbps','p99_ms','jitter_p99_ms','published','received']:
                values=[r[field] for r in selected if isinstance(r.get(field),(int,float))]
                g[field]=stats(values) if values else None
    def change(stage,rmw,mode,reference):
        a=next(g for g in grouped[stage] if g['rmw']==rmw and g['mode']==mode)
        b=next(g for g in grouped[stage] if g['rmw']==rmw and g['mode']==reference)
        return {key:100*(a[key]['median']/b[key]['median']-1) for key in ['normal_period_goodput_Mbps','p99_ms','jitter_p99_ms']}
    differences={stage:{rmw:change(stage,rmw,'static','default') for rmw in ['fastdds','cyclonedds']} for stage in ['T1_E','T1_F','P0_C2','P0_B2','P0_Clean']}
    phases=[];caps=[]
    for rmw in ['fastdds','cyclonedds']:
        for mode in MODES:
            selected=[r for r in rows if r['row']['stage']=='T1_F' and r['row']['rmw']==rmw and r['row']['mode']==mode]
            if not selected:continue
            phases.append({'rmw':rmw,'mode':mode,'goodput':[stats([r['F_phase_metrics'][i]['arrival_window_goodput_Mbps'] for r in selected]) for i in range(4)],'p99':[stats([r['F_phase_metrics'][i]['p99_latency_of_messages_originating_in_phase_ms'] for r in selected]) for i in range(4)]})
            if mode=='adaptive':
                run_caps=[]
                for r in selected:
                    artifact=Path(r['source_artifacts_root']);pub=read(artifact/'4/pub.json');start=pub['measurement_started_ns']/1e9
                    with (artifact/'4/govern/trace.csv').open() as stream:trace=list(csv.DictReader(stream))
                    run_caps.append([median([float(t['cap_packet_Bps'])*8/1e6 for t in trace if start+20*i<=float(t['monotonic_s'])<start+20*(i+1)]) for i in range(4)])
                caps.append({'rmw':rmw,'phase_cap_Mbps':[median([v[i] for v in run_caps]) for i in range(4)],'per_run':run_caps})
    t3=[]
    for rmw in ['fastdds','cyclonedds']:
        for mode in MODES:
            a=[r for r in rows if r['row']['stage']=='T3_E' and r['row']['rmw']==rmw and r['row']['mode']==mode and r['status']=='measured']
            if not a:continue
            requested=[sum(math.ceil(hz*60) for hz in r['requested_hz'].values()) for r in a]
            t3.append({'rmw':rmw,'mode':mode,'n':len(a),'ids':[r['id'] for r in a],'published':stats([r['published'] for r in a]),'received':stats([r['received'] for r in a]),'delivery_pct':stats([r['received']/(2*r['published'])*100 for r in a]),'requested_copy_delivery_pct':stats([r['received']/(2*n)*100 for r,n in zip(a,requested)]),'max_start_offset_ms':max(abs(v)*1000 for r in a for v in r['actual_start_offset_s'].values())})
    recovery=[]
    for rmw in ['fastdds','cyclonedds']:
        for mode in ['default','vendor','static','adaptive']:
            a=[r for r in rows if r['row']['condition']=='D3' and r['row']['rmw']==rmw and r['row']['mode']==mode and r['status']=='measured']
            good=[r['recovery']['recovery_s'] for r in a if r.get('recovery',{}).get('recovery_s') is not None]
            recovery.append({'rmw':rmw,'mode':mode,'ids':[r['id'] for r in a],'n':len(a),'recovered':len(good),'recovery_values':[r.get('recovery',{}).get('recovery_s') for r in a],'recovery_median_among_recovered':median(good),'first_arrival':stats([r['recovery']['first_arrival_after_restore_s'] for r in a if r['recovery'].get('first_arrival_after_restore_s') is not None]),'delivery_pct':stats([r['received']/r['published']*100 for r in a]),'p99':stats([r['p99_ms'] for r in a]),'goodput':stats([r['normal_period_goodput_Mbps'] for r in a])})
    evidence=BASE/'final_analysis_261015';evidence.mkdir(exist_ok=True)
    inputs=[BASE/n for n in ['results.json','progress.json','restoration.json','source_sha256.json','continuation.json','failure_policy.json','capacity_continuity.json']]
    manifest={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}
    analysis={'generated_at':now.isoformat(),'ended_at':ended.isoformat(),'status_counts':dict(counts),'grouped':grouped,'static_vs_default_pct':differences,'F_phases':phases,'F_adaptive_caps':caps,'T3_counts_only':t3,'D3_recovery':recovery,'input_sha256':manifest,'T3_exclusions':'No pooled first-to-last callback goodput or Jain ranking; all 108 pair clocks unqualified. Counts include drain.','statistics':'median of three run summaries; p99 is median of run p99s, not pooled p99; no significance test'}
    (evidence/'analysis.json').write_text(json.dumps(analysis,indent=2,ensure_ascii=False),encoding='utf-8')
    c=[]
    c.append('<header><div class="eyebrow">ROSPacer · W2 · 3회 반복 배치</div><h1>W2 실험 최종 결과 보고서</h1><p class="subtitle">실험 종료 '+ended.strftime('%Y-%m-%d %H:%M:%S KST')+' · 보고서 작성 '+now.strftime('%Y-%m-%d %H:%M KST')+'</p><div class="cards">'+''.join('<div class="card"><strong>'+str(value)+'</strong><span>'+label+'</span></div>' for value,label in [(207,'전체 계획 항목'),(198,'정상 측정 기록'),(6,'범위 보류'),(3,'오류 후 건너뛰기')])+'</div></header>')
    c.append('<nav aria-label="보고서 목차">'+''.join('<a href="#'+i+'">'+label+'</a>' for i,label in [('overview','결론'),('design','조건·정의'),('completion','완료 현황'),('e','T1 E'),('f','T1 F'),('t3','T3 E'),('p0','P0'),('d3','단절·복구'),('ablation','버퍼 제거'),('restore','종료·복원'),('raw','전체 기록')])+'</nav>')
    c.append('<div class="actions"><button id="expand">상세 설명 모두 펼치기</button><button id="collapse">상세 설명 모두 접기</button><span>표의 범위는 최소–최대, 중앙값은 run 3개의 중앙값입니다.</span></div>')
    c.append(section('overview','1. 결과와 판단',
        '<div class="callout"><b>배치는 종료됐습니다.</b> 정상 측정 198건, 입력 검증 범위 보류 6건, XML 기동 오류로 건너뛴 3건으로 전체 207개 항목의 처리를 마쳤습니다. 네 노트북의 복원 기록은 모두 성공입니다. 모든 연구 검증이나 논문 성능 우위가 완료됐다는 뜻은 아닙니다.</div>'+
        '<ol><li><b>Static의 효과가 여러 조건에서 관측됐습니다.</b> Cyclone T1 E의 Default 대비 처리량 +41.82%, p99 지연 −15.21%, 지터 p99 −28.91%. T1 F에서도 Static 처리량은 Fast 188.95 Mb/s, Cyclone 225.44 Mb/s로 해당 Default보다 높았습니다.</li><li><b>현재 Fixed·Adaptive는 Static보다 우수하지 않았습니다.</b> T1 E와 F에서 처리량이 낮았으며 Adaptive의 종합 지연·지터 우위도 확인되지 않았습니다. Adaptive의 상한 갱신 동작은 확인됐지만 성능 개선과는 구분해야 합니다.</li><li><b>단절 후 빠른 지연 회복은 전달 완료를 보장하지 않았습니다.</b> Cyclone D3는 일부 발행 메시지가 관측 종료까지 미수신이었습니다. Fast Static/Adaptive는 실제 발행한 메시지를 모두 수신했지만 지연 회복 기준을 3회 모두 충족하지 못했습니다.</li><li><b>남은 한계를 드러낸 결과입니다.</b> T3의 종단 지연·기존 처리량/공정성 집계는 비교에서 제외하며, Cyclone 소켓 버퍼 제거 3건은 XML 오류로 결과가 없습니다. 현재 장비·1 MiB·3회 반복의 탐색적 결과이며 5회 반복이나 통계적 유의성 검정은 수행하지 않았습니다.</li></ol>'))
    common=table(['항목','실제 조건'],[['OS·ROS','Ubuntu 22.04 · ROS 2 Humble'],['DDS','동결 Fast DDS 2.6.11 / CycloneDDS 0.10.5 런타임, run별 실제 로드 라이브러리 확인'],['데이터','std_msgs/msg/UInt8MultiArray, 1 MiB 무작위 바이트. 16바이트 순번·발행 시각 헤더 포함'],['QoS','RELIABLE · KEEP_ALL · VOLATILE'],['시간','워밍업 10초, 본 측정 60초(F는 80초), 발행자 잔여 전송 대기 30초. 수신자는 추가 여유 시간 포함'],['반복','각 DDS·조건·모드 3회, 고정 난수 시드로 모드 순서 혼합. 4·5회 추가 반복 미실행'],['무선','AX와 SR2 모두 iptimeAX1500SR, 5 GHz 채널149·80 MHz. 주 데이터는 AX'],['유선','4·5번 연결은 관리·시계용. DDS 데이터는 지정 Wi-Fi 인터페이스·주소 사용'],['교정','T1 C₀=368.7497 Mb/s, RTT=19.538 ms. 재개 전 독립 C₀=359.0907 Mb/s; 동결 모델 오차10.44%, 48/48 계산 가능. 결과에 맞춘 재학습 없음']])
    modes=table(['이름','뜻·실제 적용'],[['Default','DDS 기본 동작 중심. 공통 QoS·Wi-Fi 인터페이스·발견·메모리 할당 정책을 적용한 시험 기준군'],['Vendor','Fast: TCP와 큰 버퍼. Cyclone: 큰 소켓 버퍼·권장 커널 조각화 설정'],['Vendor-FC','Fast 전용. TCP 비교군에 비동기 발행과 고정 FlowController 예산 적용'],['Static','메시지 크기·발행률·수신자 수·C₀·RTT로 계산한 정적 DDS XML. 외부 HTB 없음'],['Fixed','같은 Static + HTB 상한·잎 fq. 고정 송신 상한을 사용'],['Adaptive','같은 Static + 최소 PHY 교정 운용 모델. 약200 ms마다 송신 관측으로 HTB 상한 갱신'],['Static−F4','Static에서 소켓 버퍼 설정 일부를 제거한 ablation. F4는 동적 경쟁 시나리오 F와 다른 이름']])
    definitions='<dl><dt>C₀와 ρ</dt><dd>C₀는 교정한 UDP 응용 데이터 처리량이며 PHY 속도 자체가 아닙니다. ρ는 교정 용량 대비 요청 응용 부하의 비율입니다. T1 요청 발행률은 <i>r = ρC₀ / (8 × 1 MiB)</i>. T3는 두 수신 복사와 송신자별 교정을 반영합니다.</dd><dt>측정창 처리량</dt><dd>T1은 실제 측정 시작부터 정해진60/80초 동안 도착한 고유 메시지 수 × 1 MiB ×8 ÷ 측정시간입니다. warmup·drain 도착을 이 분자에 넣지 않습니다. 전체 수신 수는 drain을 포함합니다.</dd><dt>발행 대비 / 요청 대비 수신율</dt><dd>발행 대비는 고유 수신/성공한 publish() 수, 요청 대비는 고유 수신/원래 목표 생성 수입니다. 역압으로 발행량이 감소하면 전자는100%여도 후자는 낮을 수 있습니다. T3는 목표 복사 수를 두 배로 둡니다.</dd><dt>종단 지연과 지터</dt><dd>지연은 publish() 직전 시각부터 수신 콜백까지이며 직렬화·큐 대기를 포함합니다. 시계 오차 상한1 ms 이하만 계산합니다. 지터는 |연속 고유 도착 간격−요청 발행 주기|의 p99로 생성 지연·역압·미수신 영향도 포함합니다. 무선만의 지터나 지연의 표준편차가 아닙니다.</dd><dt>p99의 집계</dt><dd>run별 p99를 계산하고 그 세 값의 중앙값을 표시합니다. 세 run 전체 표본의 통합 p99가 아닙니다. 표 범위는 세 run의 최소–최대입니다.</dd><dt>미회복과 미수신</dt><dd>관측창에서 회복 임계값을 달성하지 못한 것은 관측 종료까지 미회복(중도절단)입니다. 0초로 채우거나 회복한 run만으로 전체 평균을 내지 않습니다. 관측 종료까지 미수신을 곧바로 영구 패킷 손실로 단정하지 않습니다.</dd></dl>'
    c.append(section('design','2. 실험 조건과 용어',common+detail('Default·Vendor·Static·Fixed·Adaptive는 무엇인가?',modes+p('Static은 설정 생성기의 수식 기반 출력이며 sweep에서 최고 성능 행을 그대로 고른 값이 아닙니다. 본 배치 Adaptive는 ACKNACK 후보가 아니라 W1 최소 PHY 교정 모델입니다. 최초 수신 PHY 교정은 포함하되 실행 중 수신 통계 피드백·수신 SSH를 사용하지 않습니다. 초기 교정까지 포함하는 엄밀한 순수 Sender-only나 보편 물리 airtime 모델로 해석하지 않습니다.'))+detail('처리량·전달률·p99·지터·회복의 정의',definitions)+detail('정적 설정·큐·배출 대기의 해석',p('T1 설계 fq flow_limit=1490, 전체 limit=5960은 ROS 메시지 개수나 바이트가 아니라 패킷 개수입니다. flow_limit는 fq 흐름 하나의 대기 한도입니다. T1 Fixed의 실제 패킷 기준 상한은 약341.781 Mb/s이며 응용 goodput와 단위 범위가 다릅니다. 본 실험에서30초 drain은 writer를 유지하며 잔여 ACK/전송을 기다리는 절차입니다. 제안서의 전체 Drain Control을 구현·입증했다는 뜻이 아닙니다.'))))
    status_rows=[]
    for stage in STAGES:
        a=[r for r in rows if r['row']['stage']==stage];co=collections.Counter(r['status'] for r in a)
        status_rows.append([LABELS[stage],len(a),co['measured'],co['blocked_scope'],co['skipped_failed']])
    c.append(section('completion','3. 전체 완료 현황',table(['단계','계획','정상 측정','범위 보류','오류 후 건너뛰기'],status_rows)+p('정상 198건 중 T1 E 33건은 오전 배치 원자료를 그대로 사용했고, 165건은 보수 후 새로 측정했습니다. 옛 F·T3 결과는 섞지 않았습니다. 예정 항목207개를 모두 처리한 상태이며 실제 수행 가능한201개 중 XML 오류3개는 성능 결과가 없습니다.')+detail('오전 중단 배치와 재개 배치의 관계',p('오전 배치는10/15 00:30~05:51에 실행됐고 P0 토픽명의 점(.)으로 발행 전3항목 연속 실패해 중단됐습니다. 토픽 생성기를 보수하고 F는 독립 포트·절대 시작 일정, T3는 두 워밍업 종료 뒤 공통 시작 신호를 적용했습니다. AP 전환은 실제 신원·SSID 확인으로 보강했습니다. 세 번 실패하면 무조건 멈추던 정책을 제거하고, 최대2회 시도 후 환경 정상 시 건너뛰도록 했습니다. 원본과 모든 실패 시도는 보존합니다.'))))
    c.append(section('e','4. T1 E — 경쟁 없는 1:1 과부하',p('4→5, 별도 경쟁 UDP 없음. <i>ρ=1.5</i>, 요청 약553.125 Mb/s·65.9376 Hz, 60초 목표3,957개. Fast6모드·Cyclone5모드 ×3회 =33건입니다.')+metric_table(grouped['T1_E'])+p('<b>Static:</b> Cyclone은 Default 대비 처리량+41.82%, 지연−15.21%, 지터−28.91%; Fast는 처리량−0.42%로 거의 같고 지연−14.29%, 지터−22.60%였습니다. Fixed·Adaptive는 Static보다 처리량이 약13~15% 낮았으며 종합 지연·지터 우위도 없었습니다.')+p('<b>비동기 큐의 비용:</b> Fast Vendor-FC는 3회 모두3,957개 발행 성공, 관측 종료 수신은3,150/3,124/3,199개였습니다. p99는41.25~42.35초입니다. 비동기 큐 수용과 제때 전달은 다릅니다. Fast Vendor의 처리량293.88/276.54/43.76 Mb/s 중 낮은 run도 제외하지 않았습니다. 원인 확정은 보류합니다.')+detail('이 시험이 가정한 것과 해석 범위',p('C₀보다 큰 요청 부하로 DDS·소켓·큐의 과부하 동작과 역압 비용을 확인합니다. 기본 기동 실패를 재현하는 시험이 아닙니다. publish()가 기다려 실제 생성률이 줄어드는 경우를 전달 완료와 분리해 봅니다. 모든 모드의 XML·버퍼·전송 방식이 같지는 않으므로 Static 내부의 어느 설정 하나가 개선을 만들었는지는 이 비교만으로 분리할 수 없습니다.'))))
    phase_gp=table(['DDS','모드','0–20초 경쟁0','20–40초 경쟁0.5C₀','40–60초 경쟁0.9C₀','60–80초 경쟁0'],[[x['rmw'],x['mode'],*[num(z['median']) for z in x['goodput']]] for x in phases])
    phase_lat=table(['DDS','모드','0–20초','20–40초','40–60초','60–80초'],[[x['rmw'],x['mode'],*[num(z['median']) for z in x['p99']]] for x in phases])
    cap_table=table(['DDS Adaptive','경쟁 전','0.5C₀ 경쟁','0.9C₀ 경쟁','경쟁 종료 후'],[[x['rmw'],*[num(v) for v in x['phase_cap_Mbps']]] for x in caps])
    c.append(section('f','5. T1 F — 동적 경쟁과 실제 상한 추종',p('주 DDS4→5, 경쟁 UDP12→10 모두 같은 AX. 요청 <i>ρ=0.7</i>, 약258.125 Mb/s·30.7709 Hz, 80초 목표2,462개. 경쟁은20초씩0 →0.5C₀ →0.9C₀ →0이며 양의 부하 두 단계는 각각 UDP 성립을 확인했습니다. 33건 모두 정상 기록, 발행 성공 메시지는 모두 수신했습니다.')+metric_table(grouped['T1_F'])+p('<b>실제 성능:</b> Static의 전체 측정창 goodput는 Fast188.95, Cyclone225.44 Mb/s입니다. Adaptive는 각각150.78,180.98 Mb/s로 Static보다 낮았습니다. Cyclone Adaptive의 p99는400.56 ms로 Static138.16 ms보다 컸습니다. Fixed도 전체 성능에서 Static을 앞서지 못했습니다.')+ '<h3>경쟁 단계별 수신 처리량 — Mb/s, 각 단계3회 중앙값</h3>'+phase_gp+
        '<h3>Adaptive가 실제로 바꾼 HTB 상한 — 패킷 기준 Mb/s</h3>'+cap_table+p('상한은 경쟁 때 낮아지고 경쟁 종료 뒤 회복했습니다. 단계별 run 중앙값을 다시3회 중앙값으로 집계한 값입니다. 상한 추종은 동작했지만 처리량·지연의 종합 우위로 이어지지 않았습니다. T1 E/F Adaptive12건 모두 측정 구간 계산 가능 비율100%, fq drop 최대0이었습니다.')+
        detail('단계별 p99 지연과 비교 시 주의',phase_lat+p('지연은 해당 단계에서 발행한 메시지를 묶어 이후 도착까지 포함합니다. 처리량은 해당 단계에 도착한 메시지를 묶습니다. 따라서 경쟁 종료 구간에 backlog를 배출하면 처리량이 요청률보다 높아질 수 있습니다. Cyclone Static의 마지막 구간 약307.02 Mb/s는 이런 배출이 포함된 관측이며 지속 가용 용량으로 해석하지 않습니다. 20초 단위 상태 차이를 확인했지만 밀리초 단위 정착시간·오버슈트 기준의 추종 성능을 별도로 검정한 것은 아닙니다.'))+
        detail('이 시험은 무엇을 가정했나?',p('경쟁 데이터도 같은 AP를 거치므로 주 데이터와 무선 자원을 나눠 쓴다고 가정합니다. 0.5/0.9C₀는 경쟁 UDP의 요청 부하이며 실제 달성률과 같다고 가정하지 않습니다. 각 단계별 데이터·종료·시점 증거를 확인합니다. Adaptive는 최초 PHY 교정값과 송신 통계를 사용하며 실행 중 수신 피드백은 없습니다.'))))
    c.append(section('t3','6. T3 E — 두 송신자와 두 수신자',p('송신4·5가 각각 수신12·10 두 곳에 같은 메시지를 복사합니다. 각 송신자의 두 수신자 교정 C₀를 기준으로 <i>ρ=1.5</i>. 워밍업을 모두 마친 뒤 공통 시작 신호를 사용했습니다. 정상27건의 최대 시작 편차는 '+num(max(x['max_start_offset_ms'] for x in t3),3)+' ms였습니다. 이는 각 장비 시계에서 예정 시각 대비 편차이며 장비 간 시계 정확도를 입증하는 값은 아닙니다. Adaptive6건은 독립 입력 검증 미충족으로 시작하지 않았습니다.')+
        table(['DDS','설정','n','발행 합계 중앙값','수신 복사 합계 중앙값','발행 복사 대비 수신율 % 중앙값 [범위]','목표 복사 대비 수신율 % 중앙값'],[[x['rmw'],x['mode'],x['n'],num(x['published']['median'],0),num(x['received']['median'],0),span(x['delivery_pct']['values']),num(x['requested_copy_delivery_pct']['median'])] for x in t3])+
        '<div class="warning"><b>T3의 처리량·종단 지연 순위는 제시하지 않습니다.</b> 네 송수신 쌍×27건의 시계 검증108개가 모두1 ms 기준 미충족입니다. 기존 goodput_Mbps는 스트림별 첫·마지막 수신 콜백 구간율을 합산한 값이라 지속 링크 처리량이 아닙니다. 재측정에서도 최대'+num(max(r['goodput_Mbps'] for r in rows if r['row']['stage']=='T3_E' and r['status']=='measured'))+' Mb/s가 표기됐습니다. 이 값과 그로 계산한 Jain 공정성은 성능 비교에서 제외합니다. 이 보고서는 발행·복사 수신 수와 완료 비율을 중심으로 해석합니다.</div>'+
        p('Cyclone Static의 발행 수 중앙값830개·복사 수신1,660개는 Default705개·1,410개보다 많았습니다. 반면 Fast에서는 Vendor가 Static보다 실제 발행·수신 수가 많았고, Default와 Vendor-FC 일부 run에서 복사 수신 미완료도 관측됐습니다. 따라서 Static이 모든 토폴로지·DDS에서 항상 우수하다는 결론을 내릴 수 없습니다.')+
        detail('두 배 수신과 제외 지표의 의미',p('예를 들어 송신자 합계100개를 두 수신자 모두 받으면 수신 합계는200개입니다. 표의 발행 복사 대비 수신율 분모는 발행 수×2입니다. 수신 수는 drain까지 포함하고 발행 수 중앙값과 수신 수 중앙값은 각각 계산합니다. 수신 콜백이 몰리는 짧은 구간을 분모로 삼으면 링크가 실제 지속 전송한 속도를 과대 표시할 수 있습니다. 공통 고정 측정창 기준의 후속 재집계와 적절한 시계 불확실성 처리가 필요합니다.'))))
    p0body=p('P0는 우선순위 실험 묶음입니다. 낮은 부하와 용량 근처, 손상 없음, 같은 AP 경쟁과 다른 AP 간섭을 확인합니다. 각 표는 DDS·모드별3회이며 Fixed·Adaptive가 모든 P0 조건에 들어간 설계는 아닙니다.')
    for stage,description in [('P0_low_0.6','4→5, ρ=0.6, 경쟁 없음. Default/Static'),('P0_low_1.0','4→5, ρ=1.0, 경쟁 없음. Default/Static'),('P0_Clean','4→5, ρ=0.5, 경쟁·단절 없음'),('P0_C2','4→5와 경쟁12→10이 같은 AX. 주 부하ρ=0.5, 경쟁 UDP 요청0.9C₀ 지속'),('P0_B2','주4→5는AX, 경쟁12→10은다른SR2. 두AP 채널149·80 MHz 중첩. 주ρ=0.5, 다른AP UDP 포화2초/정지2초')]:
        p0body+='<h3>'+LABELS[stage]+'</h3>'+p(description)+metric_table(grouped[stage])
    p0body+=p('C2에서 Static은 Default 대비 처리량이 Fast '+num(differences['P0_C2']['fastdds']['normal_period_goodput_Mbps'])+'%, Cyclone '+num(differences['P0_C2']['cyclonedds']['normal_period_goodput_Mbps'])+'% 높았습니다. B2에서는 Fast 처리량이 거의 요청 상한에 도달해 차이가 작고, Cyclone은 Static이 더 높았습니다. Clean의 처리량은 요청한0.5C₀ 부하에 제한되므로 같은 처리량을 모델 최대용량이 같다는 의미로 읽지 않습니다. C2·B2·Clean의 실제 발행 메시지는 전부 수신했습니다.')
    p0body+=detail('Clean·C2·B2와 경쟁 포화의 의미',p('Clean은 시험에서 추가 경쟁 UDP나 단절을 주지 않은 조건이며 외부 전파가 완전히 없다고 보장하는 이름은 아닙니다. C2는 주 전송과 경쟁 전송이 같은 AP를 사용합니다. B2는 같은 채널의 별도 AP에서 경쟁 전송을 생성합니다. B2의 포화 요청은 달성할 수 있는 만큼 보내도록 한 부하이며 실제 PHY 점유율100%라는 뜻은 아닙니다. 모든 양의 부하 단계의 UDP 데이터 성립 증거는 원자료에 있습니다. C2/B2 이 표는 DDS 성능 비교이지 모델 용량 예측 오차 검증 표가 아닙니다.'))
    c.append(section('p0','7. P0 — 부하·혼잡·간섭',p0body))
    d3table=table(['DDS','설정','첫 재수신 s 중앙값 [범위]','지연 회복 달성','회복 s: 반복1 / 2 / 3','발행 대비 수신율 % 중앙값 [범위]','수신분 p99 ms 중앙값'],[[x['rmw'],x['mode'],span(x['first_arrival']['values']),str(x['recovered'])+'/'+str(x['n']),' / '.join(num(v,3) if v is not None else '미회복' for v in x['recovery_values']),span(x['delivery_pct']['values']),num(x['p99']['median'])] for x in recovery])
    c.append(section('d3','8. D3 — 단절과 복구',p('4→5, ρ=0.5. 본 측정15초 뒤 수신5의 Wi-Fi를 끄고 약5초 후 켜도록 요청했습니다. 끄기~켜기 절차 마커 간 시간은 약5.08초이며, 실제 재연결·DDS 재발견에 드는 시간은 추가될 수 있습니다. 아래 시간은 <b>복구 절차 마커 이후</b> 기준입니다.')+d3table+
        '<div class="warning"><b>지연 회복과 전달 완료를 함께 봐야 합니다.</b> Cyclone은 빠른 지연 회복을 보인 run에서도 발행한 데이터 중 일부가 관측 종료까지 미수신이었습니다. Static 수신율은77.71~78.77%, Adaptive는75.97~76.50%였습니다. 낮은 지연의 수신분만 보고 완전 전달이라고 판단할 수 없습니다. Fast Static/Adaptive는 실제 발행분100% 수신했지만 원래 목표 생성률이 낮아졌고, 지연 회복 기준을3회 모두 달성하지 못했습니다.</div>'+
        detail('복구 실험의 가정·단어·미회복 표기의 의미',p('수신 측 연결이 일시적으로 사라졌다가 돌아온다는 가정입니다. 첫 재수신은 복구 절차 이후 첫 메시지가 들어온 시각입니다. 지연 회복은 복구 후 최소3표본을 갖는 최근1초 수신창의 p95가 단절 전 p95의2배 이하가 되는 첫 시각입니다. 원자료 구현이 도착 시각마다 평가한 값을 그대로 집계했습니다. 관측 종료까지 임계값에 도달하지 못한 run은 미회복으로 두고0이나 무한대로 채우지 않습니다. 회복한 run만의 평균으로 전체 모드 순위를 매기지 않습니다. VOLATILE·재발견·보관함 처리와 미수신 원인의 세부 분리는 후속 로그 분석이 필요합니다.'))+
        detail('D3 Adaptive의 결측·보류 동작',p('단절 중 관측 입력이 부족하면 정상 계산으로 꾸미지 않고 기존 상한을 보류하는 기록이 남습니다. 정상 발행 구간의 updated 비율은 Fast 48.36%/93.33%/94.00%, Cyclone94.00%/95.00%/96.67%였습니다. E/F에서 계산 가능100%였던 사실을 단절 조건까지 그대로 확대할 수 없습니다. 실시간 보류가 동작했다는 것과 단절 복구 성능이 우수하다는 것은 별개의 판단입니다.'))))
    fast_ablate=grouped['P0_C2_F4'][0];fast_static=next(x for x in grouped['P0_C2'] if x['rmw']=='fastdds' and x['mode']=='static')
    c.append(section('ablation','9. 소켓 버퍼 설정 제거 비교와 미수행 항목',table(['DDS','조건','정상 n','처리량 Mb/s 중앙값','p99 지연 ms 중앙값','지터 p99 ms 중앙값'],[['Fast','Static',3,num(fast_static['normal_period_goodput_Mbps']['median']),num(fast_static['p99_ms']['median']),num(fast_static['jitter_p99_ms']['median'])],['Fast','Static−F4',3,num(fast_ablate['normal_period_goodput_Mbps']['median']),num(fast_ablate['p99_ms']['median']),num(fast_ablate['jitter_p99_ms']['median'])],['Cyclone','Static−F4',0,'결과 없음','XML 기동 오류','3건 건너뛰기']])+p('Fast의 버퍼 설정 제거 조건은 Static보다 처리량이 낮고 지연·지터가 컸습니다. 버퍼 설정의 기여를 시사하지만 별도 시간대의3회 비교이며 환경 변동을 포함할 수 있습니다. Cyclone은 XML 재저장 시 ns0 접두사가 붙은 루트 요소를 런타임이 unknown element로 거부해 발행 전 실패했습니다. 0처리량 성능 결과로 집계하지 않습니다. 각2회 시도 후 네 장비 환경 정상 확인을 거쳐 다음 B2로 진행했습니다.')+detail('범위 보류 6건과 오류 후 건너뛰기 3건',table(['항목','개수','원인','처리'],[['T3 Adaptive',6,'두 수신자 입력 모델의 독립 예측 오차20% 게이트 미충족','기존 검증 기준 유지, 성능 측정 없음'],['Cyclone Static−F4',3,'ns0:CycloneDDS unknown element XML 오류','시도·로그 보존, 재시도 후 건너뜀. 실험 종료 후 임의 재측정하지 않음']])+p('따라서 모든207건이 성공했다는 보고가 아닙니다. 다음 조치 후보는 Cyclone ablation XML 직렬화 보수·실제 런타임 검증 뒤3회 재측정, T3 지표/시계 보완, 정적 설정의 유망 조건 추가2회, Adaptive 성능 원인 분석입니다. 이 보고서 작성 중 추가 장비 실험이나 모델 재교정은 하지 않았습니다.'))))
    restored_rows=[]
    for h in ['4','5','12','10']:
        x=restoration[h];qs=json.loads(x['qdisc']);restored_rows.append([h,'성공' if x['restored'] else '실패',', '.join(q['kind'] for q in qs),'없음' if not x['errors'] else str(x['errors']),datetime.datetime.fromtimestamp(x['wall']).astimezone().strftime('%m/%d %H:%M:%S')])
    c.append(section('restore','10. 종료·복원·재현성',table(['노트북','감시 프로세스 복원 기록','최종 qdisc 기록','오류','복원 기록 시각 KST'],restored_rows)+p('실행기 PID41728은 종료됐고 마지막 상태는 finished_with_skipped_cases, pending=0입니다. 실행기 stderr는 비어 있습니다. 각 장비의 유한 감시 프로세스가 저장한 원래 연결·절전·CPU·커널 설정·임시 관리/시계 설정의 복원 절차를 오류 없이 마쳤다고 보고했으며, 수집된 네 장비 qdisc는 모두 noqueue입니다. 최종 행별 환경 점검과 복원 JSON을 근거로 합니다. 보고서 작성 시 장비에 새로 접속해 모든 값을 독립 재측정한 것은 아닙니다.')+p('원자료는 수정하지 않고 분석 집계와 보고서를 별도 저장했습니다. 측정 소스 스냅샷·해시, 실제 DDS 런타임 해시, XML·설정, 타이밍·수신 순번·제어 trace, 시도 이력과 case_isolation.json을 보존했습니다. 분석 입력 SHA-256은 '+link(evidence/'analysis.json','분석 근거 JSON')+'에 기록했습니다.')+detail('폴더에 있는 다른 HTML은 무엇인가?',table(['파일','작성 방식·목적'],[['W2 실험 진행 및 결과_261014.html','제가 만든 자동 실행기가 진행 중 갱신한 대시보드. 현재 종료 상태도 반영'],['W2 실행기 보수 및 재개_261015.html','제가 작성한 중단 원인·보수·재개·실패 정책 기록'],['W2 중단 배치 결과 및 재개 비교_261015.html','제가 작성한05:51 중단 배치와 재개 비교·중간 분석'],[OUT.name,'이번 요청에 따라 새로 작성한 종료 배치 전체 결과 보고서']]))))
    raw_rows=[]
    for r in rows:
        status=r['status'];raw_source=Path(r.get('source_artifacts_root',BASE/'trials'/r['id']))/'summary.json'
        if not raw_source.exists():raw_source=BASE/'trials'/r['id']/'summary.json'
        gp=r.get('normal_period_goodput_Mbps') if r['row']['topology']=='T1' else None
        rate=(r['received']/(r['published']*(2 if r['row']['topology']=='T3' else 1))*100) if r.get('published') else None
        note='T3: 지연·도착구간 처리량 제외' if r['row']['topology']=='T3' and status=='measured' else r.get('reason','')
        if status=='skipped_failed':note='XML ns0:CycloneDDS unknown element; 발행 전 실패'
        cols=[r['id'],status,r.get('published','—'),r.get('received','—'),num(rate),num(gp),num(r.get('p99_ms')) if r['row']['topology']=='T1' else '제외',num(r.get('jitter_p99_ms')) if r['row']['topology']=='T1' else '별도',note]
        raw_rows.append('<tr data-stage="'+esc(r['row']['stage'])+'" data-status="'+esc(status)+'">'+''.join('<td>'+esc(x)+'</td>' for x in cols)+'<td>'+link(raw_source,'원자료')+' · '+link(BASE/'trials'/r['id']/'summary.json','최종 판정')+'</td></tr>')
    raw='<label for="filter">조건·DDS·설정·상태 검색 </label><input id="filter" type="search" placeholder="예: cyclonedds adaptive 또는 skipped_failed"><span id="filtered-count">207개 항목</span><div class="scroll"><table id="raw-table"><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in ['ID','상태','발행','수신/복사','발행 대비 %','창 Mb/s','p99 ms','지터 p99 ms','주석','근거'])+'</tr></thead><tbody>'+''.join(raw_rows)+'</tbody></table></div>'
    c.append(section('raw','11. 전체207개 항목과 원자료',p('아래 수신 수는 drain을 포함합니다. T3는 복사 수신 합계입니다. 원자료 링크와 최종 판정 링크는 기존 파일을 가리키며 이전 배치에서 재사용한 T1 E도 실제 원본 경로에 연결합니다. 실패 시도 전체는 해당 케이스 폴더의 attempts.json에 남아 있습니다.')+detail('전체 결과 표와 검색',raw)))
    c.append('<footer>작성 근거: '+link(BASE/'results.json','results.json')+' · '+link(BASE/'progress.json','최종 진행 상태')+' · '+link(BASE/'restoration.json','최종 복원')+' · '+link(evidence/'analysis.json','집계·입력 해시')+'<br>범위: Fast DDS/CycloneDDS · 현재 장비 · 1 MiB · 조건별3회. Zenoh·전체 Drain Control·보편 물리 airtime 모델 승인·5회 반복은 포함하지 않습니다.</footer>')
    style='''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f3f5f8;color:#25354a;font:15px/1.85 "Malgun Gothic","Noto Sans KR",sans-serif}main{max-width:1320px;margin:28px auto;background:#fff;padding:40px 46px;box-shadow:0 4px 24px #24374c0a}h1{font-size:31px;letter-spacing:-.8px;margin:8px 0}h2{font-size:23px;border-bottom:2px solid #dce4ef;padding-bottom:10px;margin:42px 0 18px}h3{font-size:18px;margin-top:27px}.eyebrow{font-size:13px;letter-spacing:1px;color:#5a6d87}.subtitle{color:#617187}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:25px 0}.card{background:#f0f4fa;border:1px solid #dbe4f1;padding:18px 22px}.card strong{display:block;font-size:30px;line-height:1.3}.card span{font-size:13px;color:#60708a}nav{display:flex;flex-wrap:wrap;gap:8px 17px;border-block:1px solid #dce3ed;padding:13px 0;margin:24px 0}a{color:#315e95;text-decoration:none}a:hover{text-decoration:underline}.actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap;font-size:12px;color:#627189}button{font:inherit;cursor:pointer;background:#f6f8fb;border:1px solid #cbd5e2;border-radius:5px;padding:7px 11px;color:#354d6d}p{margin:14px 0}li{margin:10px 0}.callout,.warning{padding:18px 22px;border-left:4px solid #6688b4;background:#edf3fb;margin:20px 0}.warning{background:#fff5e8;border-color:#b6803e}.scroll{overflow:auto;max-width:100%}table{width:100%;border-collapse:collapse;font-size:12.5px;margin:17px 0}td,th{border:1px solid #dbe3ed;padding:10px 11px;text-align:left;vertical-align:top}th{background:#edf2f8;font-weight:600}td{font-variant-numeric:tabular-nums}details{padding:12px 16px;border:1px solid #dce3ed;border-radius:6px;margin:18px 0}summary{font-weight:600;cursor:pointer;color:#34577f}details[open] summary{margin-bottom:16px}dl{margin:16px 0}dt{font-weight:600;margin-top:16px}dd{margin:4px 0 12px 14px}i,.math{font-family:Georgia,"Times New Roman",serif;font-style:italic}footer{font-size:12px;color:#67778d;border-top:1px solid #dce3ed;margin-top:35px;padding-top:20px}input[type=search]{width:min(560px,100%);padding:9px 12px;font:inherit;border:1px solid #c4d0df;border-radius:4px;margin:10px 8px}#raw-table{font-size:11px}#raw-table td:first-child{overflow-wrap:anywhere;min-width:240px}#raw-table td:nth-child(9){max-width:300px}#raw-table td:last-child{min-width:90px}section{scroll-margin-top:18px}@media(max-width:760px){main{padding:22px 17px;margin:0}h1{font-size:25px}.cards{grid-template-columns:repeat(2,1fr);gap:8px}.card{padding:13px}td,th{padding:8px;font-size:12px}nav{font-size:13px}}@media print{body{background:#fff;font-size:11px}main{margin:0;padding:0;max-width:none;box-shadow:none}.actions,nav,input{display:none}.scroll{overflow:visible}h2{break-after:avoid}tr{break-inside:avoid}a{color:inherit}.cards{gap:8px}}'''
    script='''document.getElementById('expand').onclick=()=>document.querySelectorAll('details').forEach(d=>d.open=true);document.getElementById('collapse').onclick=()=>document.querySelectorAll('details').forEach(d=>d.open=false);document.getElementById('filter').oninput=e=>{const words=e.target.value.toLowerCase().trim().split(/\\s+/).filter(Boolean);let n=0;document.querySelectorAll('#raw-table tbody tr').forEach(r=>{const show=words.every(w=>r.textContent.toLowerCase().includes(w));r.hidden=!show;if(show)n++;});document.getElementById('filtered-count').textContent=n+' / 207개 항목';};'''
    body='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>W2 실험 최종 결과 보고서 — 261015</title><style>'+style+'</style></head><body><main>'+''.join(c)+'</main><script>'+script+'</script></body></html>'
    DEST.mkdir(parents=True,exist_ok=True);OUT.write_text(body,encoding='utf-8')
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in manifest.items()),'Input files changed during reporting'
    print(json.dumps({'report':str(OUT),'ended_at':ended.isoformat(),'counts':dict(counts),'bytes':OUT.stat().st_size,'evidence':str(evidence/'analysis.json')},ensure_ascii=True))

if __name__=='__main__':main()
