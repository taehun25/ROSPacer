"""Report measured failures separately from calibration and connectivity recovery."""
import html,json,statistics
from pathlib import Path
from deploy import ROOT
BASE=ROOT/'runs/w1_20261014_sender_multiphy'
NAME='W1 Sender-only PHY·접속·C2 재검증_261014.html'
OUT=ROOT.parent/'html 파일 모음/결과/W1 실험결과'/NAME
def load(name):return json.loads((BASE/name).read_text())
def n(x,scale=1):return '—' if x is None else f'{x*scale:.3f}'
def table(head,rows):return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def note(title,body):return '<details><summary>'+html.escape(title)+'</summary><div>'+body+'</div></details>'
def main():
    p=load('frozen_profile.json');d=load('frozen_direct.json');q=load('validation_results.json');rs=q['results'];protocol=load('protocol.json');cleanup=load('final_restoration.json');receipt=load('preservation.json')
    s='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>W1 Sender-only PHY·접속·C2 재검증</title><style>body{margin:0;background:#f3f6fa;color:#25364b;font:16px/1.8 system-ui,sans-serif}main{max-width:1180px;margin:24px auto;background:white;padding:30px}h1{font-size:28px}h2{margin-top:36px;border-bottom:1px solid #d4dfeb;padding-bottom:8px}.status{background:#fff4df;border-left:4px solid #a97617;padding:18px}table{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}th,td{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #d4dfeb}th{background:#edf2f8}.scroll{overflow:auto}details{border:1px solid #d4dfeb;margin:16px 0}summary{padding:12px;cursor:pointer;font-weight:650;background:#f7f9fc}details>div{padding:16px}.math{font:italic 18px/1.9 Cambria,"Times New Roman",serif;background:#f1f5fa;padding:16px;overflow-wrap:anywhere}i{font-family:Cambria,"Times New Roman",serif;font-style:italic}code{overflow-wrap:anywhere}a{color:#175e99}@media(max-width:650px){main{margin:0;padding:16px}h1{font-size:24px}}</style></head><body><main><h1>W1 Sender-only PHY·접속·C2 재검증</h1><p>2026-10-14 실제 장비 측정 · 10/12·10/13 기록과 별도의 교정·독립 검증</p><div class="status"><b>요청한 교정·독립 검증은 수행했다. Sender-only 자동 제어는 미승인이다.</b><p>두 위치의 교정 자료로 계수와 PHY 적용 범위를 고정한 뒤, 자기 부하·B2·C2·두 DDS를 새로 측정했다. 모든 독립 조건에서 계산 가능 창의 비율이95% 기준에 미달했다. 수신 보조 모델은 유지하며, 이번에는 실제 HTB 송신율을 바꾸지 않는 shadow 관측만 수행했다.</p></div><p><a href="W1 보고서.html">기존 W1 보고서</a> · <a href="W1 Sender-only 입력 충분성·안정성 검증_261013.html">10/13 Sender-only 검증</a> · <a href="#evidence">원자료·재현 정보</a></p>
<h2>1. 장비·전송·측정 조건</h2><p>주 데이터는 <b>4번 → AX 공유기 → 5번</b>의 Wi-Fi 전송이다. 두 노트북 MT7921, Ubuntu22.04·ROS2 Humble, 설치 커널6.8.0-138과 기존 서명 survey 수정 모듈을 사용했다. AX와 SR2는 iptimeAX1500SR 두 대이며, 둘 다149번·80MHz다. 4·5의 랜 케이블은 임시192.168.50.2/1 관리 경로이며 데이터 목적지는192.168.0.5로 고정했다.</p><p>측정 중 Wi-Fi 절전off, CPU performance, 커널 rmem_max/wmem_max 각각4MiB를 적용했다. UDP 교정·검증은 payload1400B, 요청 소켓1MiB, 본 전송24초다. DDS는 수정 없는 고정 런타임 Fast DDS2.6.11/CycloneDDS0.10.5, Static XML, UInt8MultiArray·1MiB·무작위 바이트·순번/발행 시각, RELIABLE·KEEP_ALL·VOLATILE, 요청 발행15초다. 실제 로드 라이브러리 경로·해시를 양쪽에서 확인했다.</p><p>따라서 모든 DDS 설정이 기본값인 시험은 아니다. Static은 모델 생성기의 메시지 크기·발행률·교정 처리량·RTT 입력으로 단편·소켓 버퍼·보관함 등을 계산한 XML이다. sweep 최적값을 그대로 가져온 조건도 아니다. 외부 HTB/fq는 적용하지 않았다.</p>'''
    s+=note('관측·단어·시계 조건', '''<p><b>Sender-only</b>: 온라인 추정에는 4번의 survey/native/station 계수와 같은 무선 라디오의 임시rpmon 프레임만 사용한다. 5번 수신 통계는 교정 및 사후 대조용이고 온라인 제어 입력으로 전송하지 않았다. 유선 관리 자체가 수신 보조 추정이라는 뜻은 아니다.</p><p><b>shadow</b>: 약200ms마다 입력을 읽고 약3초 창으로 추정치를 CSV에 기록하지만 qdisc를 설치하거나 갱신하지 않는다. <b>estimated</b>는 해당 창의 입력 게이트를 통과한 계산, <b>hold</b>는 계산 보류다. 보류를 수신 손실로 해석하지 않는다. <b>closure</b>는 실제 로드된 DDS·RMW 공유 라이브러리 경로와 해시 묶음이다.</p><p><b>PHY</b>는 무선 변조 전송률, <b>goodput</b>은 실제 전달된 응용 payload 처리량이다. 서로 같지 않다. 수신 reference는200ms 계수이고 송수신 wall 시각에 가장 가까운 표본끼리 맞췄다. 최대 대응 시각 차이는 별도 원자료에 남겼으며, 정밀 시계 자격 검사를 새로 수행하지 않았다. 이 보고서로 종단 지연·지터·복구시간 우위를 주장하지 않는다.</p>''')
    s+='<h2>2. 교정 자료와 확보한 PHY 범위</h2><p>처음 위치와 이동한 두 번째 위치에서 UDP50/150Mb/s 및 포화 전송을 각각 측정했고, 두 번째 위치에서 DDS 두 종류를 교정 자료에 추가했다. 추가 이동은 공간·케이블 제약으로 수행하지 않았다. 설치 드라이버의 bitrate mask 명령은−95(EOPNOTSUPP)로 거절돼 강제 전송률을 적용하지 못했다. TX power는 변경하지 않았다.</p>'
    train=[]
    for tag in protocol['training']:
        f=load(tag+'/features.json');ws=f['windows'];up=[w['up_Bps']*8/1e6 for w in ws];down=[w['down_Bps']*8/1e6 for w in ws if w['down_Bps']];cov=[w['body_coverage'] for w in ws]
        train.append([tag,n(f['receiver_payload_Bps'],8/1e6),f'{min(up):.1f}~{max(up):.1f}',f'{min(down):.1f}~{max(down):.1f}' if down else '결측',f'{min(cov):.3f}~{max(cov):.3f}',sum(w['down_Bps'] is None for w in ws)])
    s+=table(['교정 run','UDP 수신Mb/s','상향 harmonic Mb/s','하향 harmonic Mb/s','정상CRC body coverage','하향PHY 결측 창'],train)
    s+=f'<p>새 <i>C₀</i>는 두 포화 UDP 수신값의 중앙값 <b>{n(p["capacity_reference"]["C0_Bps"],8/1e6)}Mb/s</b>다. 교정 후 고정한 적용 범위는 상향 <b>{p["uplink_Mbps_range"][0]:.1f}~{p["uplink_Mbps_range"][1]:.1f}</b>, 하향 <b>{p["downlink_Mbps_range"][0]:.1f}~{p["downlink_Mbps_range"][1]:.1f}Mb/s</b>다. 범위는 샘플 가시성 조건을 통과한 교정 창에 숫자 여유1Mb/s를 더한 것이며, 전체PHY나 낮은PHY 일반화를 뜻하지 않는다.</p>'
    s+=note('harmonic·aggregation·가시성이 무엇인가', '''<p><b>harmonic PHY</b>는 같은 창에서 전송 바이트·재시도를 가중치로 사용한 조화 평균이다. 마지막 iw 전송률 한 개로 전체 구간을 대표하지 않도록 변경했다. <b>aggregation</b>은 여러 데이터 단위를 무선 전송 묶음으로 모으는 기능이다. MSDU는 MAC에 제공되는 데이터, MPDU는 MAC 프레임, A-MSDU/A-MPDU는 각각 해당 단위의 집합이다. PPDU는 프리앰블 등을 포함한 물리 전송 단위다. 암호화된 A-MSDU 내부 발신자는 현재 캡처 경로로 분리하지 못한다.</p><p><b>body coverage</b>는 CRC가 정상인 AP→5 중계 body 바이트 / 4번 station TX 바이트의 운용 가시성 지표다. 정확한 PPDU 포착률이나 수신 전달률은 아니다. 실제 정상 전달 중에도 송신 위치의 monitor가 하향 프레임을 적게 볼 수 있다. Cyclone 교정에서는3개 창 중2개에서 하향PHY가 전혀 관측되지 않았다. 호스트 capture drop=0이어도 공중의 모든 프레임을 관측했다는 뜻은 아니다.</p>''')
    s+='<h2>3. 고정한 두 후보와 검증 전제</h2><p>기존 직접 관측 모델은 정상CRC 중계 body를 충분히 포착해야 하므로 포화·DDS 교정에서 실패했다. 이를 유지한 채, 송신 station 바이트 보존을 이용하는 별도 후보를 교정했다. 새 후보는 누락된 프레임을 정상으로 승격하지 않고, 중계 데이터 직렬화 항에 송신 바이트를 대리 입력으로 사용한다.</p>'
    s+=table(['항목','직접 관측 후보','송신 바이트 보존 후보'],[['파일','frozen_direct.json','frozen_profile.json'],['교정 창',d['fit_window_count'],p['fit_window_count']],['BlockAck 유효 비용µs',n(d['BA_busy_s'],1e6),n(p['BA_busy_s'],1e6)],['하향 교환 유효 비용µs',n(d['relay_exchange_busy_s'],1e6),n(p['relay_exchange_busy_s'],1e6)],['직렬화 입력','관측한 CRC 정상 중계 바이트/하향PHY','송신 station TX 바이트/관측 하향PHY'],['가시성 계약','body coverage0.8~1.1','PHY 샘플 body coverage0.25~1.1, 정상MPDU≥128, peerBA≥32'],['온라인 수신 피드백','없음','없음'],['자동제어 승인','false','false']])
    s+=f'<p>두 후보의 대칭 조건부 <i>O<sub>up</sub>=O<sub>down</sub>={n(p["O_up_s"],1e6)}µs</i>는 포화 교정에 맞춘 운용 계수다. 상하향 비용을 독립 식별한 물리적 고정 비용이 아니다. 검증 전에 파일 해시를 고정했으며, 검증 자료로 계수나 적용 범위를 바꾸지 않았다.</p>'
    s+='''<div class="math">Δ = 송신 active 증분<br>T̂relay = c<sub>BA</sub>N<sub>ownBA</sub> + B<sub>station,TX</sub>/R<sub>down</sub> + c<sub>DL</sub>N<sub>peerBA</sub><br>β̂oth = (Δbusy − b<sub>idle</sub>Δ − T̂relay)/Δ<br>θ = [(1+ν)(O<sub>up</sub>+L<sub>IP</sub>/R<sub>up</sub>) + O<sub>down</sub>+L<sub>IP</sub>/R<sub>down</sub>]/L<sub>station</sub><br>q̂ = min(0.9C₀, 0.9(1−β̂oth)/θ)</div>'''
    s+=note('새 후보의 가정·busy/TX·각 수식의 뜻', '''<p><i>Δbusy</i>는 해당 장비에서 관측하는 수신 CCA busy 시간 증분이다. 기존 관측에 따라 자기 TX를 포함하는 전제는 사용하지 않으며 TX를 다시 빼지 않는다. <i>Δtx</i>는 송신 시간 카운터 증분이다. 수신CCA와TX가 같은 포함 관계라는 보편 전제가 없으므로 TX≤busy를 강제하지 않는다.</p><p><i>Bstation,TX</i>는 송신 station의 바이트 증가량, <i>Rup/Rdown</i>은 byte/s 단위 PHY 조화 평균이다. <i>NownBA</i>는 AP가 송신 단말의 상향에 응답한 BlockAck 개수, <i>NpeerBA</i>는5번이 AP 하향에 응답한 BlockAck 개수다. 계수는 그 교환의 유효busy 비용으로, 실제PPDU 개수나 물리 BA 길이가 아니다. <i>ν</i>는 송신 retry/packet 비율이다. IPv4/UDP1400B 교정에서 station1462B, IP1428B, 운용 station 추가분34B를 사용했다.</p><p>수신MAC에 대용량 송신자가 하나이며, AP가 해당 송신 바이트를 같은 시간창에 전달하고, 관측한 하향PHY 샘플이 나머지 전송률을 대표한다는 가정이 필요하다. 사후 바이트 보존 검사는 AP 큐·손실 문제를 대조하지만 온라인으로 가정을 보장하지는 않는다. 암호화·바이트 보존 대리 입력으로 모든 자기 중계와 경쟁 트래픽을 완전히 분리한 결과가 아니다.</p><p>직접 관측의0.8 기준을0.25로 단순 완화해서 통과시킨 것은 아니다. 중계 바이트 항을 교체한 별도 가정·후보이며 독립 검증도 실패했다. CRC 오류·알 수 없는 HE PHY·capture drop·계수 초기화는 계속 보류한다. 실제HTB가 있었다면 EMA0.7/0.3으로 상한을 갱신하는 코드지만 이번 시험에서는 CSV만 기록했다.</p>''')
    s+=table(['미리 고정한 판정','기준'],[['계산 가용성','정상 구간 estimated 비율≥95%'],['자기 부하 잔차','경쟁 부하 없는 조건 |β̂oth| p95≤0.05'],['포화 용량 오차','안전 계수·상한·EMA 이전 payload 예측과 실측의 상대오차≤20%'],['사후 바이트 보존','보정된 송수신 byte 비율의 |ratio−1|≤10%'],['포착/PHY','capture drop0, unknown PHY0, 최소 정상 샘플 수, 고정한 PHY 범위'],['접속 안정성','monitor 제거·noqueue 유지·전송 후 일반Wi-Fi ping/SSH; 종료 후 재연결로 복구한 run을 통과로 세지 않음']])
    s+='<h2>4. 교정에 사용하지 않은 자기 부하·B2·C2</h2><p>자기 부하0.2/0.5/0.8은 송신 요청량을 새 <i>C₀</i>의 비율로 설정한 조건이다. 물리 링크 속도를 줄인 조건이 아니다. 정상 구간은 전송 시작+4초부터 종료−2초까지다.</p>'
    rows=[]
    for r in rs:
        if r['tag'].startswith('dds_'):continue
        rows.append([r['tag'],n(r['received_payload_Mbps']),f'{r["estimated_windows"]}/{r["steady_windows"]} ({r["estimated_fraction"]*100:.1f}%)',n(r['accepted_beta_abs_p95']),n(r.get('conditional_capacity_relative_error'),100),r['exit_lifecycle']['healthy_without_reconnect'],'미통과'])
    s+=table(['독립 run','수신payload Mb/s','계산 가능 창','계산된 창 |β|p95','조건부 용량오차%','재연결 없는 종료','입력95% 판정'],rows)
    s+='<p><b>B2·C2 포화에서는 계산 가능 창이0개라 유효한 용량 예측 오차를 보고할 수 없다.</b> 무경쟁 포화의19.009%도 단1개 창에서 계산한 조건부 값이며, 전체run이95% 가용성에 실패해 정식 용량 검증 통과로 인정하지 않는다. 계산 가능한 자기 부하 창의 잔차가 작다는 사실만으로 보류된 나머지 창을 통과시킬 수 없다.</p>'
    s+=note('B2·C2·경쟁 부하·실제 수신량 설명', '''<p><b>B2</b>: 주 전송4→AX→5, 경쟁12→SR2→10. 공유기는 다르고149번·80MHz 무선 채널은 겹친다. <b>C2</b>: 주 전송4→AX→5, 경쟁12→같은AX→10. 실제SSID/BSSID/MAC/IP를 확인해 같은 AP 조건을 보장했다. AX 전환 시12는192.168.0.12,10은192.168.0.10으로 식별했다.</p><p>경쟁 UDP는요청300Mb/s·1400B·70초이며 주24초 시험을 덮도록 실행했다. 요청률을 채널100% 점유로 해석하지 않는다. 실제 경쟁 수신량은 아래 표처럼 별도 대조했다. 이번 B2는 지속 경쟁 입력 시험이다. 제안서의2초ON/2초OFF나 동적추종F 정식성능 시험을 완료한 것으로 세지 않는다. quiet는 의도적인 경쟁UDP를 켜지 않은 주 링크 시험이며 주변AP 전원을 모두 끈 조건은 아니다.</p>''')
    bg=[]
    for r in rs:
        if 'background' not in r:continue
        raw=load(r['tag']+'_background/10_server.json');streams=[x for interval in raw['intervals'] for x in interval['streams']];good=sum(x['bytes'] for x in streams)/sum(x['seconds'] for x in streams)*8/1e6
        bg.append([r['tag'],r['background']['kind'],'300',n(good),'70초 전체 평균; 주24초와 동일 창 아님'])
    s+=table(['경쟁 run','AP 배치','요청Mb/s','실제 경쟁 수신Mb/s','시간 창'],bg)
    holds=[]
    for r in rs:holds.append([r['tag'],'; '.join(f'{k}: {v}' for k,v in r['hold_reasons'].items())])
    conservation_rows=[[r['tag'], '~'.join(n(x) for x in r['offline_conservation_ratio_range']), n(r['offline_conservation_error_max'],100), n(r['offline_pair_window_skew_s_max'],1000)] for r in rs if 'offline_conservation_ratio_range' in r]
    s+=note('사후 송수신 바이트 보존 대조', table(['run','RX/(TX−20×packet) 범위','최대 비율 오차%','최대 대응 시각 차이ms'],conservation_rows)+'<p>송신iw station TX바이트에서패킷당20B 운용계층보정을뺀값과수신iw station RX바이트를비교했다. 20B는이번교정의계층차이이며보편MAC헤더가아니다. 모든UDP 조건의비율오차는10%이내이고수신UDP RcvbufErrors/SndbufErrors/InErrors증가도0이었다. 데이터가실제도달해도송신monitor가하향을못볼수있다는근거다. 이사후측정은온라인수신피드백으로사용하지않았다.</p>')
    s+=note('모든 정상 구간 보류 사유',table(['run','보류 횟수'],holds)+'<p>게이트는 순서대로 확인한다. 첫 실패 사유 하나만 기록하므로 상향 범위 이탈로 보류된 창에 하향 관측 문제도 동시에 있을 수 있다. 보류 횟수는 원인의 유일성을 증명하지 않는다. 독립 전송에서는 상향PHY가 교정의 하한보다 낮아지는 경우가 많았고 하향도987Mb/s 등으로 내려갔다. 교정 범위에 억지로 넣거나 결측을 이전값·0으로 대체하지 않았다.</p>')
    s+='<h2>5. DDS 독립 자기 부하 확인</h2>'
    ddsrows=[]
    for r in rs:
        if 'DDS' not in r:continue
        a=r['DDS'];pub=load(r['tag']+'/4/pub.json');ds=[x['publish_duration_ms'] for x in pub['records']]
        ddsrows.append([a['rmw'],a['planned'],a['published'],a['received'],n(statistics.median(ds)),n(max(ds)),f'{r["estimated_windows"]}/{r["steady_windows"]} ({r["estimated_fraction"]*100:.1f}%)',all(a['runtime_valid'].values())])
    s+=table(['DDS','계획 발행','실제 발행','고유 수신','publish 중앙ms','publish 최대ms','추정 가용성','고정 라이브러리 확인'],ddsrows)
    s+=f'<p>공통 요청 발행률은 <i>r=0.2C₀/1MiB={0.2*p["capacity_reference"]["C0_Bps"]/1048576:.6f}Hz</i>로, 계획122개다. Fast는122/122개, Cyclone은실제83/83개 수신했다. Cyclone은deadline에 도달해39개를 시도하지 못했고 publish 최대5,457.435ms를 기록했다. 오류39개나 수신 손실39개가 아니다. 보관함/전송 대기에 의한 발행 속도 저하와 맞는 관측이지만, 소켓·WHC 동시 상세 계측 없이 유일한 원인을 확정하지 않는다.</p>'
    s+=note('이 DDS 시험이 증명하는 범위', '<p>Static XML을 적용한 실제DDS 트래픽에서도 Sender-only 입력을 충분히 확보하는지 확인했다. 고정 런타임의 수정 없음은 라이브러리 소스가 수정 없다는 뜻이고, XML·커널 준비까지 모두 기본값이라는 뜻은 아니다. 두DDS모두입력95%기준실패다. Fast/Cyclone 성능 순위를 확정한 반복 비교나 Adaptive 대 Static/Fixed 성능 비교가 아니다. 수신 보조 제어기나 sweep 설정의 우열도 이 표로 비교하지 않는다.</p>')
    s+='<h2>6. 접속 안정성: 상태 승계와 새 연결을 구분</h2><p>앞선 상태를 승계한 무부하 진단에서는 절전on 후SSH 실패를 재현했다. 절전off만으로 재연결 없이 돌아온 경우가 있었다. 같은 시험에서IPQoS=none만 추가한SSH는 실패를 해결하지 못했다. 이때의 상태에는 앞선 monitor 동작·이동 영향이 섞여 있으므로 절전 하나를 유일한 원인으로 확정하지 않았다.</p>'
    lifecycle=[]
    for prefix in ['stability','fresh_stability']:
        for mode in ['power_only','monitor_off','monitor_restore_on']:
            rows=[load(f'{prefix}_{mode}_{k}.json') for k in [1,2]]
            lifecycle.append(['상태 승계' if prefix=='stability' else '각 시험 전 새 AX 연결',mode,f'{sum(r["after_default"]["rc"]==0 for r in rows)}/2',f'{sum(r["after_qos_none"]["rc"]==0 for r in rows)}/2',f'{sum(r["after_power_off_no_reassociate"]["rc"]==0 for r in rows)}/2'])
    s+=table(['준비 상태','무부하 조건','종료SSH 성공','IPQoS none 성공','절전off 후SSH 성공'],lifecycle)
    loaded=load('loaded_stability.json')
    s+=table(['새 연결 후 UDP100Mb/s·10초','실제 종료 절전 상태','종료SSH','절전off 후SSH'],[[r['mode'],r['client']['power_after'].strip(),r['ordinary_wifi_ssh_after']['rc']==0,r['recovered_by_power_off']['rc']==0] for r in loaded])
    s+=note('접속 시험의 뜻·가정·해결 판정', '''<p><b>power_only</b>는monitor 없이절전on 전환, <b>monitor_off</b>는절전off 상태에서monitor 생성·삭제, <b>monitor_restore_on</b>은원래절전on을저장한뒤monitor 중off·종료후on 복원이다. 무부하monitor 유지3초와 UDP100Mb/s·10초 부하시험을 분리했다. 종료SSH는5번에서4번Wi-Fi 주소로 일반SSH hostname을실행한 결과다.</p><p>각시험전새연결은 시작상태를재설정한 시험 조건이다. 시험 종료 실패를 재연결로 감춘 것과 구분한다. 이 준비 조건의무부하6회와부하3회는모두통과했고, 독립UDP7개도종료ping/SSH가성공했다. 장시간·모든상태에서의영구해결이나kernel원인수정으로해석하지않는다. 드라이버를추가수정하거나재설치하지않았다. 기존sshd IPQoS설정은유지했다.</p>''')
    s+=note('최종 복원 과정의 추가 접속 실패', '<p>모든 전송이 끝난 뒤 원래 절전on으로 복원했을 때 4번의IPv4/IPv6 SSH timeout이 다시 재현됐다. 유선 관리로 절전off만 적용하자 재연결 없이IPv4 SSH가 돌아왔다. 이후 원래AX 프로파일을 새로 연결하고 절전on으로 복원했으며 IPv4/IPv6 SSH가 모두 성공했다. cleanup_connection_recovery.json에 원격명령·결과를 보존했다. 따라서 단기새연결시험의성공을절전전환문제의영구해결로해석할수없다. 마지막복구재연결은안정성통과횟수에추가하지않는다.</p>')
    s+='<h2>7. 복원·최종 판정·남은 조건</h2>'
    s+=table(['장비','복원 검사'],[[h,'; '.join(k+': '+('확인' if v else '실패') for k,v in row.items())] for h,row in cleanup['checks'].items()])
    s+=f'<p>최종 복원 전체 판정: <b>{"완료" if cleanup["complete"] else "미완료"}</b>. 12·10은원래SR2로복귀하고임시AX프로파일과도우미를종료했다. 4·5는기존절전on·CPUpowersave·커널버퍼212992·noqueue로복귀했고임시관리IP·monitor·전송프로세스·실험절전억제기를제거했다. 기록된기존연구DDS 라이브러리와모듈해시는유지됐다. 최종원격조회는기존Wi-Fi IPv6 link-local 경로로수행했으며최종IPv4의전조건장기안정을새로보장하지않는다.</p>'
    s+=table(['요청 항목','이번 결론'],[['여러PHY교정','두 위치의 실제변화로교정. 낮은하향PHY까지포괄하지못함'],['교정과독립검증분리','완료.8개교정run과9개후속검증run분리,고정해시유지'],['Sender-only입력충분성','미통과.독립9조건모두95%미달'],['B2·C2','실제배치/경쟁전송/원자료확보.포화추정0창으로모델오차확정불가'],['접속안정성','새연결준비의단기시험통과.승계상태실패및영구원인미확정'],['Sender-onlyHTB자동제어','validated=false 유지. 실제송신율갱신미실행'],['정확한물리airtime/보편O','미확정.이번유효운용계수로대체해성공처리하지않음']])
    s+='<p>다음 변경은 <b>낮아진상·하향PHY에서도교정가능하고, 자기송신중하향PHY·aggregation관측이끊기지않는입력경로</b>를확보하는것이다. 범위만넓히는것으로샘플0창을해결할수없다. 새입력경로나명시적모델가정을정하면새교정자료로고정한뒤이번자료와분리한새자기부하/B2/C2/DDS를다시검증해야한다. 현재하드웨어관측으로어떤범위도Sender-only가불가능하다는결론은아니지만, 지금후보를정식자동제어에사용할근거도부족하다.</p><p>Receiver-assisted는이와별도로남겨뒀다. W1전체를새로완료라고표시하지않으며, Sender-only입력승인·일반화·정식성능비교를이번단기시운전으로완료처리하지않는다.</p>'
    s+='<h2 id="evidence">8. 원자료·수식·재현 정보</h2><p>원자료는 <code>ROSPacer/runs/w1_20261014_sender_multiphy</code>에 보존했다. 실행별pcap·CSV·nativeJSONL·receiverJSON·XML·실제로딩해시·계수freeze·복원감시baseline/receipt를함께보존했다. 원자료의실제타임스탬프를유지했으며10/12·10/13표의수치를덮어쓰지않았다.</p>'
    import os
    evidence=[]
    for name,label in [('protocol.json','검증전절차와판정기준'),('freeze_receipt.json','계수파일고정해시'),('validation_results.json','독립검증정량판정'),('frozen_profile.json','송신바이트보존후보'),('frozen_direct.json','직접관측후보'),('loaded_stability.json','부하시접속시험'),('cleanup_connection_recovery.json','최종복원접속실패·복구'),('final_restoration.json','최종복원검사'),('evidence_sha256.json','원자료SHA256목록'),('source_snapshot.tar.gz','현소스스냅샷'),('preservation.json','보존영수증')]:
        href=Path(os.path.relpath(BASE/name,OUT.parent)).as_posix();evidence.append('<li><a href="'+html.escape(href,quote=True)+'">'+label+'</a></li>')
    s+='<ul>'+''.join(evidence)+'</ul>'
    s+=f'<p>보존파일 {receipt["files"]}개 · 기준git commit <code>{receipt["git_commit"]}</code> · dirty source 스냅샷을별도보존(미커밋변경을한커밋으로오인하지않음). 새코드의카운터초기화/PHY범위/CRC·결측보류/무승인HTB차단등60개unittest통과. pytest는로컬미설치여서프로젝트의unittest discovery로검증했다.</p><p>고정후보SHA256: <code>{q["frozen_sha256"]["frozen_profile.json"]}</code></p><p>현재모듈의정확한HE duration/LTF·완전한PPDU관측이부족하므로 이수식을단일물리적고정비용의검증으로인용하지않는다. 모든수식·기호는이탤릭체로표시했고,외부수식렌더러 없이HTML 자체로읽을수있게작성했다.</p></main></body></html>'
    for before,after in [('두위치교정','두 위치 교정'),('독립검증수행','독립 검증 수행'),('입력95%미통과','입력 95% 기준 미통과'),('자동제어보류','자동 제어 보류'),('새연결준비접속시험통과','새 연결 준비 접속 시험 통과'),('최종복원확인','최종 복원 확인'),('정식성능 시험','정식 성능 시험'),('물리독립 식별','물리 독립 식별')]:s=s.replace(before,after)
    OUT.write_text(s,encoding='utf8')
    for target in [ROOT.parent/'html 파일 모음/W1 보고서.html',OUT.parent/'W1 보고서.html']:
        text=target.read_text(encoding='utf8');uid='sender-multiphy-20261014'
        href=('결과/W1 실험결과/' if target.parent.name=='html 파일 모음' else '')+NAME
        add='<p id="'+uid+'"><a href="'+html.escape(href,quote=True)+'">10/14 Sender-only PHY·접속·C2 재검증</a> — 두위치교정과독립검증수행. 입력95%미통과로자동제어보류; 새연결준비접속시험통과, 최종복원확인.</p>'
        if uid not in text:target.write_text(text.replace('</main>',add+'</main>',1),encoding='utf8')
    print(OUT,flush=True)
if __name__=='__main__':main()
