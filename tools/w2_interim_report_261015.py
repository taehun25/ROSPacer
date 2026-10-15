"""Local-only analysis of the stopped batch; never contacts laboratory hosts."""
import collections,datetime,hashlib,html,json,statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'runs/w2_20261014_3rep'
CURRENT=ROOT/'runs/w2_20261015_resume1'
OUT=ROOT.parent/'html 파일 모음/결과/W2 실험결과/W2 중단 배치 결과 및 재개 비교_261015.html'

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def esc(v):return html.escape(str(v))
def num(v,d=2):return '—' if v is None else f'{v:,.{d}f}'
def table(head,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def link(path,label):return '<a href="'+esc(path.resolve().as_uri())+'">'+esc(label)+'</a>'
def group(rows,stage):
    output=[]
    for rmw in ['fastdds','cyclonedds']:
        for mode in ['default','vendor','vendor_fc','static','fixed','adaptive']:
            a=[r for r in rows if r['row']['stage']==stage and r['row']['rmw']==rmw and r['row']['mode']==mode and r['status']=='measured']
            if not a:continue
            item={'rmw':rmw,'mode':mode,'n':len(a),'ids':[r['id'] for r in a]}
            for key in ['normal_period_goodput_Mbps','p99_ms','jitter_p99_ms','published','received']:
                values=[r[key] for r in a if isinstance(r.get(key),(int,float))]
                item[key]={'median':statistics.median(values),'min':min(values),'max':max(values)} if values else None
            item['delivery_successful_publish_pct']=[100*r['metrics']['delivery_successful_publish'] for r in a]
            item['delivery_requested_pct']=[100*r['metrics']['delivery_requested'] for r in a]
            output.append(item)
    return output

def main():
    rows=read(OLD/'results.json');progress=read(CURRENT/'progress.json');matrix=read(CURRENT/'matrix.json')
    now=datetime.datetime.now().astimezone();e=group(rows,'T1_E');f=group(rows,'T1_F')
    ea=[r for r in rows if r['row']['stage']=='T1_E']
    stats={stage:dict(collections.Counter(r['status'] for r in rows if r['row']['stage']==stage)) for stage in sorted({r['row']['stage'] for r in rows})}
    old_hashes={k.replace('\\','/'):v for k,v in read(OLD/'source_sha256.json').items()}
    current_hashes={k.replace('\\','/'):v for k,v in read(CURRENT/'source_sha256.json').items()}
    source_comparison={key:key in old_hashes and key in current_hashes and old_hashes[key]==current_hashes[key] for key in ['rospacer/model.py','rospacer/profiles.py','rospacer/sender_minphy.py','tools/w2_analysis.py']}
    assert all(source_comparison.values()),'Frozen model/profile/controller hashes changed; comparison text must be reviewed'
    med=lambda rmw,mode,key:next(x for x in e if x['rmw']==rmw and x['mode']==mode)[key]['median']
    differences={}
    for rmw in ['fastdds','cyclonedds']:
        differences[rmw]={}
        for mode,reference in [('static','default'),('fixed','static'),('adaptive','static')]:
            differences[rmw][mode+'_vs_'+reference]={k:(med(rmw,mode,k)/med(rmw,reference,k)-1)*100 for k in ['normal_period_goodput_Mbps','p99_ms','jitter_p99_ms']}
    meta={'generated_at':now.isoformat(),'scope':'stopped batch only; active campaign observed from local files only',
          'old_base':str(OLD),'current_progress_snapshot':progress,'old_status_counts':stats,
          'T1_E_groups':e,'T1_F_preliminary_groups':f,'T1_E_relative_changes_pct':differences,
          'unchanged_source_hashes':source_comparison,
          'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [OLD/'results.json',OLD/'progress.json',OLD/'source_sha256.json',CURRENT/'source_sha256.json',CURRENT/'capacity_continuity.json']}}
    content=[]
    content.append('<h1>W2 중단 배치 결과 및 재개 비교</h1><p class="sub">'+esc(now.strftime('%Y-%m-%d %H:%M:%S %Z'))+' 작성 · 제어 PC의 저장 파일만 분석 · 장비 명령·AP 전환·송신 없음</p>')
    content.append('<div class="callout"><b>핵심 판단:</b> 05:51 중단은 P0의 잘못된 ROS 토픽명에 따른 운영 실패였습니다. T1 E 33건은 유지합니다. 이 자료에서 CycloneDDS Static은 Default 대비 처리량 약 41.8% 증가, p99 지연 약 15.2% 감소, 지터 p99 약 28.9% 감소를 보였습니다. Fixed·Adaptive의 Static 대비 우위는 확인되지 않았습니다. F·T3는 절차 보수 뒤 재측정 중입니다.</div>')
    content.append('<h2>1. 05:51 중단 배치와 현재 배치의 차이</h2><p>중단 배치는 실제 한국시간 <b>10/15 00:30:03부터 05:51:25까지</b> 실행됐습니다. 폴더의 20261014는 준비일 기준 이름입니다. 현재 배치는 10/15 재개 구간이며, 실패 처리 정책까지 반영한 실행기는 <b>12:29</b>부터 동작합니다.</p>')
    content.append(table(['항목','중단 배치','현재 배치'],[
        ['연구 비교 대상','W1 구현을 이용한 W2 성능 비교','동일. 성능이 좋아 보이도록 모델·DDS 설정을 다시 맞춘 배치가 아님'],
        ['계산 모델·DDS 프로파일·제어기','당시 동결 코드','model.py, profiles.py, sender_minphy.py(교정·제어 구현), w2_analysis.py 해시 일치'],
        ['교정 기준 C₀','368.7497 Mb/s','동일 기준 유지. 새 독립 측정 359.0907 Mb/s, 기존 대비 −2.62%. 예측 오차 10.44%, 48/48 계산 가능'],
        ['T1 E','33건 measured','33건 그대로 재사용. 원자료 수정 없음'],
        ['F 경쟁 부하','동일 서버 포트 재사용, 앞 클라이언트 종료 뒤 다음 실행. 일부 실패·시점 지연','양의 부하 단계마다 독립 서버·포트, 각 단계를 예정 시각에 독립 실행, 단계별 UDP 데이터·종료·시각 확인. 33건 모두 재측정'],
        ['T3 측정 시작','각 발행자가 워밍업 직후 시작. 블로킹 때문에 시작 시각이 달라질 수 있음','두 발행자의 워밍업 종료를 모두 기다린 뒤 5초 여유를 둔 공통 시작 신호. 실행 대상 27건 재측정'],
        ['P0 발행 전 오류','0.6이 포함된 케이스 ID가 ROS 토픽명에 그대로 들어가 InvalidTopicNameException','허용 문자로 변환하고 충돌 방지 해시 추가. 실제 Humble 토픽 검증과 시운전 통과'],
        ['T3 Adaptive','입력 예측 오차 게이트 미충족 6건이 failed로 표시됨','같은 게이트 유지. blocked_scope로 올바르게 구분하며 자동 실행하지 않음'],
        ['AP 전환','고정 대기와 저장된 상태에 의존','실제 장비 MAC·SSID 확인, 양방향 전환 시험, 부분 전환 후 재탐색, 절전 해제 확인'],
        ['실패 시 처리','운영 실패 3회 연속이면 전체 중단','최대 2회 시도 후 공통 환경 복구 확인 시 skipped_failed로 기록하고 다음 케이스. 두 차례 정리·확인 후 환경 미복구 시 중단'],
        ['원자료','w2_20261014_3rep','원본 불변. 새 시도는 w2_20261015_resume1에 분리; 각 시도·실패·환경 점검 기록 유지']]))
    content.append('<p>현재 실행기에는 명시적 SSH 입력 종료 처리와 원자적 제어 파일 쓰기도 적용돼 있습니다. 위 수정은 기동·부하 성립·동시 시작·안전한 진행을 보수한 것이며, Adaptive에 유리한 성능 기준을 도입한 것이 아닙니다.</p>')
    content.append('<h2>2. 현재 실제로 수행하는 실험</h2>')
    content.append('<p>저장 상태 확인 시각 <b>'+esc(progress['updated_UTC'])+' (UTC; 한국시간 +9시간)</b>: <b>'+esc(progress.get('active'))+'</b>, 상태 '+esc(progress['state'])+'. 정상 measured '+str(progress['valid_measured'])+'건, 범위 보류 '+str(progress['blocked_scope'])+'건, 실패 후 건너뛰기 '+str(progress.get('skipped_failed',0))+'건, 남은 항목 '+str(progress['pending'])+'건입니다. 이 수치는 작성 시점의 스냅샷입니다.</p>')
    content.append('<h3>T1 F: 1:1 전송 중 같은 AP의 경쟁 부하가 바뀌는 시험</h3><p><b>주 데이터:</b> 4번 → AX 공유기 → 5번. <b>경쟁 데이터:</b> 12번 → 같은 AX 공유기 → 10번. 네 장비는 AX에 연결하고, 다른 SR2 AP에서 포화시키는 B2와 구분합니다. 4·5번의 랜 케이블은 관리·시계 동기화용입니다. DDS 사용자 데이터는 XML과 Wi-Fi 주소로 무선 경로에 묶습니다.</p>')
    content.append(table(['측정 시작 후','경쟁 UDP 요청 부하','확인 목적'],[['0–20초','없음','경쟁 전 기준 상태'],['20–40초','0.5 C₀ ≈ 184.375 Mb/s','중간 경쟁 부하에 대한 반응'],['40–60초','0.9 C₀ ≈ 331.875 Mb/s','강한 경쟁 부하에 대한 반응'],['60–80초','없음','경쟁 종료 후 회복']]))
    content.append('<p>주 발행 요청은 <i>ρ = 0.7</i>, 즉 응용 데이터 기준 약 <b>258.125 Mb/s ≈ 30.7709 Hz</b>입니다. 80초 동안 목표 2,462개를 요청합니다. 실제 발행 수는 publish() 대기 등으로 줄 수 있으므로 목표량·실제 발행량·수신량을 함께 봅니다. 경쟁 부하의 숫자는 요청 전송률이며 실제 달성률은 각 단계의 iperf 원자료로 확인합니다.</p>')
    content.append('<details><summary>공통 조건·비교군·측정 지표의 자세한 의미</summary><p>Ubuntu 22.04, ROS 2 Humble, Fast DDS 2.6.11 및 CycloneDDS 0.10.5의 동결 런타임. 1 MiB std_msgs/msg/UInt8MultiArray 무작위 데이터에 16바이트 순번·발행 시각을 포함합니다. QoS는 RELIABLE·KEEP_ALL·VOLATILE. 워밍업 10초 → F 측정 80초(다른 조건은 60초) → 종료 전 drain 30초. 기동·발견·수집·정리 시간은 별도입니다. drain은 잔여 데이터 전송을 기다리는 시간이며 제안서 전체 Drain Control 구현을 뜻하지 않습니다.</p>'+table(['비교군','실제 구성'],[
        ['Default','기본 DDS 동작 중심. 공통 QoS, Wi-Fi 인터페이스·발견 설정, 시험용 메모리 할당 정책은 적용'],
        ['Vendor','Fast: TCP 전송과 큰 버퍼. Cyclone: 큰 소켓 버퍼와 권장 커널 조각화 설정'],
        ['Vendor-FC','Fast만 추가. TCP 기반 비교군에 비동기 발행과 고정 FlowController 예산 적용'],
        ['Static','메시지 크기·발행률·수신자 수·C₀·RTT로 계산한 DDS 정적 XML. HTB 없음'],
        ['Fixed','같은 Static XML + HTB/fq 고정 상한. T1에서 패킷 기준 상한 약 341.781 Mb/s'],
        ['Adaptive','같은 Static XML + W1 최소 PHY 교정 모델로 약 200 ms마다 HTB 상한 갱신. 실행 중에는 송신 측 관측만 사용; 최초 수신 PHY 교정은 포함']])+ '<p>각 DDS·비교군은 3회 반복합니다. F의 경우 Fast 6개 모드 × 3회 + Cyclone 5개 모드 × 3회 = 33건입니다. 발행 호출 시간, 순번 기반 전달률, 실제 발행률, 측정창 처리량, 지연 p50·p95·p99, 도착 간격 지터, 제어기 입력·상한, HTB/fq·소켓·커널 통계와 실제 로드 라이브러리 해시를 기록합니다. 시계 오차 상한 1 ms 초과 구간의 종단 지연은 제외합니다.</p></details>')
    content.append('<h3>전체 순서와 남은 매트릭스</h3>')
    descriptions={'T1_E':('4→5, 1:1','과부하 ρ=1.5, 경쟁 UDP 없음','33건 유지'), 'T1_F':('4→5, 경쟁12→10','ρ=0.7, 경쟁0/0.5/0.9/0 단계','33건 재측정 중'), 'T3_E':('송신4·5 → 각각 수신12·10','각 발행자는 두 수신자에 같은 데이터를 복사, 각 교정 C₀ 기준 ρ=1.5','27건 재측정 예정, Adaptive 6건 보류'), 'P0_low_0.6':('4→5','ρ=0.6, Default/Static','대기'), 'P0_low_1.0':('4→5','ρ=1.0, Default/Static','대기'), 'P0_Clean':('4→5','ρ=0.5, 별도 경쟁·단절 없음','대기'), 'P0_C2':('4→5, 경쟁12→10 같은 AP','ρ=0.5, 같은 AP 경쟁 UDP 0.9 C₀ 지속','대기'), 'P0_D3':('4→5','ρ=0.5, 측정 15초 뒤 수신5 Wi-Fi 5초 단절·재연결','대기'), 'P0_D3_adaptive':('4→5','같은 D3, Adaptive 추가','대기'), 'P0_C2_F4':('4→5, 같은 AP 경쟁','같은 C2, Static에서 소켓 버퍼 설정 일부 제거하는 ablation','대기'), 'P0_B2':('4→5는 AX, 경쟁12→10은 SR2','ρ=0.5, 다른 AP에서 같은 채널 149/80 MHz를 2초 포화·2초 정지','마지막 대기')}
    counts=collections.Counter(r['stage'] for r in matrix)
    content.append(table(['단계','계획 건수','장비 역할','실험 조건','작성 시점 상태'],[[stage,counts[stage],*descriptions[stage]] for stage in counts]))
    content.append('<p>207개 계획 항목 중 실행 가능한 대상은 201개이며 T3 Adaptive 6개는 범위 보류입니다. 33건 재사용 뒤 이번 재개 구간의 신규 대상은 168건입니다. P0는 우선 수행하는 실험 묶음이며, F4는 여기서 소켓 버퍼 설정 제거 조건을 가리킵니다. 동적 경쟁 시나리오 F와 다릅니다.</p>')
    content.append('<h2>3. 05:51 중단 배치의 결과</h2>')
    content.append(table(['단계','기록','당시 상태','이번 보고서의 사용 범위'],[['T1 E',33,'measured 33','주요 성능 비교에 사용; 현재 배치에서도 유지'],['T1 F',33,'measured 27 / 경쟁 부하 미성립 6','절차가 다른 예비 자료. 전체 재측정으로 교체'],['T3 E',33,'measured 26 / 시작 시각 미충족 1 / 범위 보류 6(당시 failed)','예비 자료. 성능 비교용 27건 재측정, Adaptive 6건 보류'],['P0 ρ=0.6 처음 3건',3,'모두 발행 전 운영 실패','성능 결과 없음'],['나머지 계획',105,'실행 전 중단','결과 없음']]))
    content.append('<p>총 102개 항목에 기록이 있고, 당시 <code>measured</code> 표시는 86건입니다. 이 86건 전체를 같은 신뢰도의 정식 결과로 취급하지 않습니다. 6개 T3 Adaptive는 성능이 나빠서 탈락한 것이 아니라, 입력 예측 오차가 20% 기준을 넘어서 시작을 허용하지 않은 항목입니다.</p>')
    content.append('<h3>T1 E: 과부하에서 얻은 주요 성능 결과</h3><p>4→5, 경쟁 트래픽 없음, <i>C₀ = 368.7497 Mb/s</i>, <i>ρ = 1.5</i>. 요청 발행 부하는 약 553.125 Mb/s, 65.9376 Hz이며 60초 목표 수는 3,957개입니다. 아래는 각 모드 <b>3회 run 통계의 중앙값</b>입니다. p99 열도 run별 p99의 중앙값이며, 세 run의 모든 표본을 합친 p99가 아닙니다.</p>')
    content.append(table(['DDS','모드','측정창 처리량 Mb/s','p99 지연 ms','도착 간격 지터 p99 ms','실제 발행/수신 중앙값','실제 발행 대비 수신율'],[[x['rmw'],x['mode'],num(x['normal_period_goodput_Mbps']['median']),num(x['p99_ms']['median']),num(x['jitter_p99_ms']['median']),num(x['published']['median'],0)+' / '+num(x['received']['median'],0),('100%' if min(x['delivery_successful_publish_pct'])==100 else num(min(x['delivery_successful_publish_pct']))+'–'+num(max(x['delivery_successful_publish_pct']))+'%')] for x in e]))
    content.append('<p><b>해석 1 — Static의 효과:</b> Cyclone Static은 Default 대비 처리량 +41.82%, p99 지연 −15.21%, 지터 p99 −28.91%였습니다. 세 반복 모두 처리량은 268.71–270.81 Mb/s로 Default 187.49–192.24 Mb/s보다 높았습니다. Fast Static은 처리량 −0.42%로 거의 비슷하면서 p99 지연 −14.29%, 지터 p99 −22.60%를 보였습니다. 정적 설정을 평가할 유용한 결과입니다.</p>')
    content.append('<p><b>해석 2 — 페이싱 추가의 비용:</b> Fixed/Adaptive는 Static보다 처리량이 Fast에서 각각 12.82%/13.73%, Cyclone에서 14.07%/15.11% 낮았습니다. 이 조건에서는 Static 대비 지연·지터도 개선되지 않았습니다. Adaptive가 Fixed보다 낫다는 근거도 없습니다. 경쟁 없는 지속 과부하에서 현재 페이싱 구성의 비용이 관측됐으며, 원인을 HTB 하나로 단정할 수는 없습니다.</p>')
    content.append('<p><b>해석 3 — 발행 성공과 전달 완료의 차이:</b> Fast Vendor-FC는 세 번 모두 목표 3,957개의 publish() 호출을 성공시켰지만 관측 종료까지 3,150/3,124/3,199개만 수신했습니다. 수신율은 실제 발행 대비 78.95–80.84%, p99 지연은 41.25–42.35초였습니다. 비동기 큐가 발행 부하를 받아들인 것과 제때 전달한 것은 다릅니다. 미수신분을 영구 패킷 손실로 단정하지 않으며 30초 drain을 포함한 관측 한계 안의 미완료로 기록합니다. 다른 모드의 100% 수신도 요청한 3,957개를 모두 생성했다는 뜻이 아닙니다.</p>')
    content.append('<p><b>해석 4 — 변동과 제어 동작:</b> Fast Vendor의 3회 처리량은 293.88 / 276.54 / 43.76 Mb/s였고 마지막 run의 p99는 652.50 ms였습니다. 시계·시작·복원 게이트를 통과한 실제 저성능 결과라 제외하지 않습니다. 원인은 이 자료만으로 확정하지 않습니다. Adaptive 6건은 측정 발행 구간 계산 가능 비율 100%, 전체 실행 로그 HTB 변경 644–715회, Fixed/Adaptive 12건 모두 fq drop 최대값 0이었습니다. 동작 성공과 성능 우위는 별개입니다.</p>')
    content.append('<details><summary>지표 정의와 유효성 근거</summary><p><b>측정창 처리량:</b> 발행자의 실제 측정 시작부터 60초 동안 도착한 고유 메시지 수 × 1 MiB × 8 ÷ 60초. warmup·drain을 처리량 분모에 섞지 않습니다. <b>종단 지연:</b> 메시지에 넣은 publish() 직전 시각부터 수신 콜백까지이므로 직렬화·DDS 대기·전송·콜백 대기를 포함합니다. <b>도착 간격 지터:</b> 연속 고유 메시지 도착 간격과 요청 주기(약 15.17 ms)의 차이 절댓값이며 역압·생성 지연도 포함합니다. 무선 경로만의 지터가 아닙니다. <b>발행 대비 수신율:</b> 고유 수신 수/성공한 publish() 수. 별도로 요청 대비 수신율을 보존합니다.</p><p>T1 E 33건 모두 실제 라이브러리 해시·시계·시작·qdisc 복원 확인을 통과했습니다. 시계 상대 오차 상한은 0.0555–0.1412 ms, 측정 시작 편차 최대 0.0964초였습니다. 3회 반복의 일관된 관측 차이를 보고하는 것이며 통계적 유의성 검정이나 제안서의 5회 반복 완료를 뜻하지 않습니다. 메시지 크기 1 MiB·현재 NIC/AP·현재 고정 프로파일에 한정합니다. Static 내부 개별 설정의 기여는 ablation 전에는 분리하지 않습니다.</p></details>')
    content.append('<details><summary>T1 E 33개 run 개별 결과 — 이상값 포함</summary>'+table(['ID','발행','수신','요청 대비 수신 %','측정창 Mb/s','p99 ms','지터 p99 ms','publish() p99 ms'],[[r['id'],r['published'],r['received'],num(100*r['metrics']['delivery_requested']),num(r['normal_period_goodput_Mbps']),num(r['p99_ms']),num(r['jitter_p99_ms']),num(r['metrics']['publish_duration_ms']['p99'])] for r in ea])+'</details>')
    content.append('<h3>T1 F: 예비 경향과 재측정 사유</h3><p>33건 중 6건은 경쟁 클라이언트 실패로 조건이 성립하지 않았습니다. 성공 표시 27건도 강한 경쟁·종료 단계가 계획보다 약 0.38–2.24초 밀렸고, 옛 게이트는 모든 양의 부하 단계의 성립을 각각 입증하지 않았습니다. 따라서 아래 값은 보수 전 자료의 기술 통계이며 현재 재측정과 합쳐 우위를 주장하지 않습니다. n은 실패를 제외하고 남은 예비 run 수여서 균등하지 않습니다.</p>')
    content.append(table(['DDS','모드','예비 n','측정창 Mb/s 중앙값','p99 ms 중앙값','지터 p99 ms 중앙값'],[[x['rmw'],x['mode'],x['n'],num(x['normal_period_goodput_Mbps']['median']),num(x['p99_ms']['median']),num(x['jitter_p99_ms']['median'])] for x in f]))
    content.append('<p>예를 들어 Fast Adaptive는 남은 두 run에서 82.68 Mb/s·p99 4,045 ms로 Static의 183.29 Mb/s·201 ms보다 좋지 않았습니다. 이는 검증할 진단 신호이며, 불균등 반복·경쟁 부하 절차 문제 때문에 확정 성능 결론으로 사용하지 않습니다. 낮은 성능 run을 골라 버리지 않고 원본을 모두 보존합니다.</p>')
    content.append('<h3>T3 E: 보류·시간 동기화·집계 한계</h3><p>두 발행자가 각각 두 수신자에게 복사하므로 수신 수 최대값은 발행 수의 두 배입니다. Adaptive 6건은 독립 입력 오차 게이트 미충족으로 실행 보류입니다. 그 밖의 27건 중 1건은 시작 오차가 1초를 넘었으며, 기록된 27건 모두 네 송수신 쌍에서 종단 지연 시계 기준을 충족하지 못했습니다. 종단 지연 비교를 할 수 없습니다.</p>')
    content.append('<div class="warn"><b>처리량 표기 주의:</b> T3 Fast Default r1의 기존 goodput_Mbps는 17,477.35입니다. 수신12의 두 스트림 콜백이 각각 약 51.43 ms/30.42 ms 안에 37/43개 몰린 탓에, 각 스트림의 첫·마지막 콜백 간격으로 계산한 수치를 합산하면서 발생했습니다. 지속 링크 처리량이 아닙니다. 원본 값은 유지하지만 처리량·공정성 우위 근거로 사용하지 않습니다. 현재 실행기에도 이 도착 구간 합산 정의가 남아 있으므로, 새 T3 자료도 공통 고정 측정창 기준의 사후 집계가 필요합니다. 이 분석 중 실행 중인 코드는 수정하지 않았습니다.</div>')
    t3=[r for r in rows if r['row']['stage']=='T3_E' and 'pairs' in r]
    content.append('<details><summary>T3 개별 발행·수신 수 — 성능 우위 판정에서 분리</summary>'+table(['ID','당시 상태','발행 합계','수신 복사 수 합계','지연 기준 통과 쌍 / 4'],[[r['id'],r['status'],r['published'],r['received'],str(sum(p['clock']['validated'] for p in r['pairs']))+' / 4'] for r in t3])+'</details>')
    content.append('<h3>P0: 발행 전 중단 원인</h3><p>처음 3건 모두 토픽명 <code>/w2_P0_low_0.6_…</code>의 점(.) 때문에 발행자를 만들지 못했습니다. DDS의 전송 성능 실패가 아닙니다. 각 케이스마다 여러 번 실패한 것이 아니라, 서로 다른 세 계획 항목이 연속 실패해 옛 보호 조건이 작동했습니다. 네 장비 복원은 모두 성공했습니다. P0 성능 결과는 아직 없으며, 현재 토픽 생성기를 보수한 뒤 순서대로 실행할 예정입니다.</p>')
    content.append('<h2>4. 지금 보고할 수 있는 결론</h2><p><b>유의미한 관측은 있습니다.</b> 정적 설정은 Cyclone의 과부하 성능을 일관되게 개선했고, Fast에서는 처리량을 유지하며 지연·지터를 줄였습니다. 반면 현재 Fixed·Adaptive는 이 조건에서 Static보다 좋지 않았고, 비동기 발행의 높은 발행 성공률은 큐 지연과 미완료를 감출 수 있었습니다. 논문 기여의 후보와 개선할 지점을 모두 확인한 단계입니다.</p><p>Adaptive의 경쟁 변화 추종 우위, T3 다중 송수신 성능, P0 일반화, 전체 Drain Control 완료는 아직 결론낼 수 없습니다. 현재 F 재측정 → T3 공통 시작 재측정 → P0 순서를 유지하며, 보수 전 F·T3를 좋은 결과만 선별해 새 결과와 합치지 않습니다.</p>')
    content.append('<details><summary>중단 배치 전체 102개 기록과 원자료 링크</summary><ul>'+''.join('<li>'+link(OLD/'trials'/r['id']/'summary.json',r['id'])+' — '+esc(r['status'])+' '+esc(r.get('reason',''))+'</li>' for r in rows)+'</ul></details>')
    content.append('<p>입력 원자료: '+link(OLD/'results.json','중단 배치 결과 JSON')+' · '+link(OLD/'progress.json','05:51 종료·복원 기록')+' · '+link(CURRENT/'progress.json','현재 진행 상태')+' · '+link(CURRENT/'failure_policy.json','새 실패 처리 정책')+'</p>')
    body='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>W2 중단 배치 결과 및 재개 비교 — 261015</title><style>body{font:15px/1.85 "Malgun Gothic",sans-serif;color:#25364b;background:#f5f7fb;margin:0}main{max-width:1200px;margin:28px auto;background:white;padding:36px 44px}h1{font-size:28px}h2{margin-top:38px;border-bottom:2px solid #dce4ef;padding-bottom:9px}h3{margin-top:28px}p{margin:13px 0}.sub{color:#607187;font-size:13px}.callout,.warn{padding:18px 22px;background:#edf3fb;border-left:4px solid #597dac}.warn{background:#fff4e4;border-color:#b67b2e}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;margin:18px 0}td,th{border:1px solid #dce3ed;padding:10px;text-align:left;vertical-align:top}th{background:#eef2f7}details{border:1px solid #dce3ed;border-radius:5px;padding:12px 16px;margin:18px 0}summary{cursor:pointer;font-weight:600}code{background:#f0f3f7;padding:2px 4px;overflow-wrap:anywhere}a{color:#315c94}li{overflow-wrap:anywhere}i{font-family:Georgia,"Times New Roman",serif}@media(max-width:700px){main{padding:20px;margin:0}td,th{padding:7px}}@media print{body{background:white}main{padding:0;margin:0;max-width:none}.scroll{overflow:visible}details{break-inside:avoid}}</style></head><body><main>'+''.join(content)+'</main></body></html>'
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(body,encoding='utf-8')
    evidence=CURRENT/'interim_analysis_261015';evidence.mkdir(exist_ok=True)
    (evidence/'analysis.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(OUT),'generated_at':now.isoformat(),'current':{k:progress.get(k) for k in ['active','valid_measured','pending','updated_UTC']},'old_counts':stats},ensure_ascii=True))

if __name__=='__main__':main()
