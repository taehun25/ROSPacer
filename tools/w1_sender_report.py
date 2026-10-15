"""Render sender-only prototype evidence without changing W1 approval."""
from collections import Counter
import csv
import hashlib
import html
import json
from pathlib import Path
from deploy import ROOT


BASE=ROOT/'runs/w1_20261013_sender_only'
NAME='W1 송신 측 수동 관측 프로토타입_261013.html'


def load(path):return json.loads((BASE/path).read_text())
def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def note(title,body):return '<details><summary>'+title+'</summary><div>'+body+'</div></details>'
def link(path,label):return '<a href="../../../ROSPacer/runs/w1_20261013_sender_only/'+path+'">'+label+'</a>'


def main():
    fast=BASE/'dds_v4_fastdds';rows=list(csv.DictReader((fast/'4/sender.csv').open()))
    valid=[r for r in rows if r['status']=='estimated']
    fast_summary={'rmw':'fastdds','planned':120,'published':load('dds_v4_fastdds/4/pub.json')['succeeded'],'received':load('dds_v4_fastdds/5/sub.json')['unique_received'],
                  'sender_estimates':len(valid),'beta_raw_range':[min(float(r['beta']) for r in valid),max(float(r['beta']) for r in valid)],'holds':dict(Counter(r['error'] for r in rows if r['status']=='hold')),
                  'receiver_feedback_used':False,'HTB_applied':False,'note':'wireless collection failed after run; evidence subsequently recovered over direct Ethernet'}
    (fast/'summary.json').write_text(json.dumps(fast_summary,indent=2),encoding='utf8')
    cyclone=load('dds_v5_cyclonedds/summary.json');b2=load('validationB2_100/validation.json');p=load('frozen_sender_profile_v2.json')
    s='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>W1 송신 측 수동 관측 프로토타입 · 2026-10-13</title><style>
body{font:16px/1.7 system-ui,sans-serif;color:#20334d;background:#f3f6fa;margin:0}main{max-width:1120px;margin:24px auto;padding:30px;background:white;border-radius:10px}h1{font-size:27px}h2{margin-top:36px;border-bottom:1px solid #ccd6e3;padding-bottom:6px}.status{background:#fff3d4;border-left:4px solid #b48014;padding:16px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;margin:18px 0;font-size:14px}th,td{padding:12px;border-bottom:1px solid #d9e1eb;text-align:left;vertical-align:top}th{background:#edf2f9}details{margin:16px 0;border:1px solid #d4deeb;border-radius:6px}summary{cursor:pointer;font-weight:650;padding:12px;background:#f5f8fc}details>div{padding:16px}code{overflow-wrap:anywhere}a{color:#1c6396}i{font-family:Cambria,serif;font-style:italic}.eq{overflow-wrap:anywhere;font-family:Cambria,serif;font-style:italic}.muted{color:#536479;font-size:14px}@media(max-width:600px){main{margin:0;padding:18px}h1{font-size:23px}}
</style><main><h1>W1 송신 측 수동 관측 프로토타입</h1><p class="muted">측정·구현: 2026-10-13 · Receiver-assisted와 별도 경로 · 기존 W1 판정 유지</p>
<div class="status"><b>판정: 송신 측 추정 경로 구현 · 무경쟁 DDS 기능 확인 · B2 경쟁 조건은 보류</b><p>수신측 별도 통계를 받지 않고 송신 노트북에서 AP→수신 단말의 데이터 PHY와 aggregation 대리값을 관측했다. 하지만 B2에서 중계 가시성이 약19%로 감소해 추정을 거부했다. 송신 측만으로 경쟁까지 충분히 분리하는 정식 adaptive를 완성했다고 판정하지 않는다. 현재 프로파일은 validated=false이며 HTB 자동 갱신을 활성화하지 않았다.</p></div>
<h2>1. 유지한 경로와 새 경로</h2>'''
    s+=table(['경로','입력','이번 상태'],[['adaptive (Receiver-assisted)','송신 통계 + 수신 단말이 유선으로 전달한 native RX/PHY 통계','기존 코드·교정·자료 유지'],['sender-observe','송신 노트북의 survey/station + 같은 장비의 임시 monitor MAC/radiotap','새 shadow 구현; HTB 변경 없이 검사'],['adaptive-sender','동일 송신 측 추정값으로 기존 HTB/fq 갱신','구현했지만 별도 검증된 sender profile이 없으면 설치 전 거부']])
    s+=note('Sender-only의 정확한 의미와 현재 가정','<p>실행 중 입력은 4번 한 대에서 얻는다. 5번이 보내는 별도 무선 통계/PHY 피드백은 없다. 일반 DDS 데이터·ACKNACK과 802.11 ACK/BlockAck는 원래 전송에 필요한 프로토콜 동작이며 수신측 측정 에이전트의 피드백과 다르다. 수신 결과와 5번 캡처는 검사 후 참조로만 회수했다.</p><p>기존 UDP 교정 처리량 C₀를 사전 입력으로 재사용했다. 즉, 온라인 Receiver-assisted는 아니지만 C₀까지 새 monitor 조건에서 독립 재교정한 시험도 아니다. 현재는 수신 MAC으로 보내는 대용량 트래픽이 4번에서만 온다는 운영 가정을 둔다.</p>')
    s+='<h2>2. 송신 측에서 관측한 정보</h2>'
    s+=table(['정보','관측 방법','해석 한계'],[['하향 PHY','AP→5번 데이터의 HE MCS·NSS·BW·GI known 비트','AP→4번 제어 프레임 속도로 대체하지 않음; 현재 약1201Mb/s 범위만 교정'],['aggregation','A-MSDU 표시·MAC 길이·중복 시퀀스·재전송·AMPDU reference','독립 PPDU 전체 길이와 airtime 확정 아님'],['자기 상향 교환','AP→4번 BlockAck 계수','교정된 운영 비용 대리값; 물리 BA duration과 다름'],['자기 하향 교환','5번→AP BlockAck 계수','실제 PPDU 수와 같다고 가정하지 않음'],['다른 트래픽 잔차','raw busy − quiet baseline − 자기 교환 추정','자기 중계가 충분히 보이지 않으면 구분 보류']])
    s+=note('암호화된 A-MSDU에서는 왜 원송신자 구분이 제한되는가','<p>일반 From-DS 프레임의 Addr3 원송신자는 바깥 헤더에서 볼 수 있다. 하지만 이번 AP의 A-MSDU는 바깥 Addr3가 AP/BSSID였고, 각 하위 데이터의 원송신자는 암호화된 내부 헤더에 있다. 따라서 AP→5번 전체를 자기 중계로 취급하려면 5번의 대용량 사용자 트래픽이 4번에서만 온다는 가정이 필요하다. 여러 송신자가 같은 5번으로 보내는 경우를 해결한 것으로 주장하지 않는다.</p>')
    s+='<h2>3. 교정식과 단위</h2><p class="eq">T̂relay = kUpBA × N(AP→4 BA) + Σ(MAC bytes / Rdown) + kDownExchange × N(5→AP BA)<br>β̂raw = (busy − idle_fraction × Δ − T̂relay) / Δ<br>θ̂ = ((1+retry)(Oup + IP_bytes/Rup) + Odown + IP_bytes/Rdown) / mean_station_bytes<br>cap = min(0.9C₀, 0.9(1−β̂raw)/θ̂)</p>'
    s+=table(['항목','값','의미'],[['kUpBA',f"{p['BA_busy_s']*1e6:.3f} µs/관측 교환",'source-local 회귀값; 물리 BA32µs와 구분'],['kDownExchange',f"{p['relay_exchange_busy_s']*1e6:.3f} µs/관측 교환",'하향 전송 교환의 운영 비용'],['quiet baseline',f"{p['idle_busy_fraction']*100:.3f}%",'교정 30·100·200Mb/s 시험의 발행 전 source busy'],['Oup·Odown',f"각 {p['O_up_s']*1e6:.3f} µs",'기존 C₀와 송신 측에서 관측한 PHY로 맞춘 대칭 조건부 비용; intrinsic O 아님'],['송신 byte 계수 비용','34 B/패킷','UDP1400에서 iw bytes/packets=1462, IP=1428. Ethernet14로 간주한 v1을 수정'],['중계 body 관측 비율','0.80~1.10','source TX byte 대비 수동 관측 body의 공학적 게이트; 정확한 수신률 아님']])
    s+=note('계수 고정·교정과 검증 분리','<p>30·100·200Mb/s source 관측으로 운영 계수를 고정했다. 교정 오차는 약−0.960%, +1.847%, −0.890%였다. 그다음 70·140Mb/s 자료를 평가했다. v1→v2 변경은 회귀값 재맞춤이 아니라 송신 MAC byte 계수의 헤더 비용 수정이다. 원래 profile과 실패 run을 보존했다. 현재 계수는 PHY 약1201Mb/s·149/80MHz·MT7921·AX1500·단일 주 송신자 범위의 임시 프로파일이다.</p><p>자기 TX가 raw busy에 완전히 포함되지 않는 기존 관측 계약을 사용하므로 TX를 다시 빼지 않는다. 음수 β를 0으로 치환하지 않는다. 캡처 drop, 부족한 중계 가시성, unknown PHY, 범위 밖 입력은 hold다.</p>')
    s+='<h2>4. 교정에 사용하지 않은 자기 부하</h2>'
    checks=[]
    for n in ['validation70','validation140']:
        r=load(n+'/validation.json');e=r['sender_estimate'];checks.append([n,f"{r['receiver_bps']/1e6:.3f} Mb/s",f"{e['beta']*100:.3f}%",f"{e['body_coverage']*100:.2f}%",'|β|≤5% 범위'])
    s+=table(['조건','수신 처리량 참조','<i>β̂</i> raw','송신 대비 body 관측','판정'],checks)
    s+='<h2>5. 두 DDS의 실시간 송신 측 shadow</h2>'
    s+=table(['DDS','예정/발행/수신','유효 추정 횟수','<i>β̂</i> raw 범위','별도 수신 피드백','HTB 변경'],[[r['rmw'],f"{r['planned']}/{r['published']}/{r['received']}",r['sender_estimates'],f"{r['beta_raw_range'][0]*100:.3f}% ~ {r['beta_raw_range'][1]*100:.3f}%",'없음','없음'] for r in [fast_summary,cyclone]])
    s+=note('이 DDS 시험의 조건과 hold 해석','<p>4→AX1500→5, UInt8MultiArray 1MiB 무작위 바이트, 순번·발행 시각, RELIABLE·KEEP_ALL·VOLATILE, Static XML, 발행15초, 약0.2C₀ 부하다. Fast2.6.11·Cyclone0.10.5의 별도 고정 runtime을 사용했다. 추정기는38초 동안 약200ms마다 읽고 약3초 관측 창을 사용했다. 유효 창만 추정하며, 초기 warm-up·발행 종료 후 no own packets·부족한 가시성·unknown PHY 등은 보류했다.</p><p>76/44는 메시지 수가 아니라 유효한 추정 계산 횟수다. HTB 갱신 횟수가 아니다. 두 DDS의 성능 우위나 적응형 제어 완료를 주장할 수 없다. Wi-Fi 절전은 관측 중 껐고 종료 후 on으로 복원했다. 무선 SSH가 끊긴 Fast 결과는 유선으로 회수했으며 정상 수신과 추정 로그를 보존했다. 절전을 끈 조건과 켠 조건의 결과를 섞지 않는다.</p>')
    s+='<h2>6. B2 경쟁 진단에서 확인한 실패 조건</h2>'
    s+=table(['조건','source busy/active','송신 대비 body 관측','수신 처리량 참조','추정 결과'],[['주 4→5 AX1500; 경쟁12→10 SR2; 두 AP149/80MHz',f"{b2['source_delta']['busy_s']/b2['source_delta']['active_s']*100:.2f}%",f"{b2['source_visible']['body_coverage']*100:.2f}%",f"{b2['receiver_bps']/1e6:.3f} Mb/s",b2['sender_estimate_error']]])
    s+=note('B2 결과가 말하는 것과 아직 말할 수 없는 것','<p>경쟁 쌍은 별도 AP에서300Mb/s를48초 요청했고, 주 쌍은100Mb/s를8초 요청했다. 이번은 원 proposal의2초ON/2초OFF B2와 다른 연속 경쟁 진단이다. 경쟁 실행과 같은149/80MHz 조건을 확인했다. source raw busy는 증가했으나 자기 중계가 약19%만 보였다. 교정 범위 아래라 경쟁 β의 점 추정과 상한 계산을 거부했다.</p><p>kernel capture drop0이어도 공중 프레임이 모두 포착됐다는 뜻은 아니다. 원인을 송신 중 blind 구간·간섭·beamforming·driver RX 경로 중 하나로 확정하지 않았다. 5번 캡처는 오프라인 참조이며 clock이 정밀 동기화되지 않아 두 캡처 비율을 정확한 물리 프레임 손실률로 쓰지 않는다.</p><p>주 부하가 포화 용량 측정이 아니므로66.824Mb/s를 링크 최대 용량으로 쓰거나 모델 오차20% 검증을 한 것으로 해석하지 않는다. Sender-only B2·C2 공식 예측 오차, 동적 경쟁 추종 및 HTB 자동 제어는 미완료다.</p>')
    s+='<h2>7. 수정 기록·복원·다음 작업</h2>'
    s+=note('수집 코드 오류와 실제 관측 한계를 구분','<p>초기 live 수집에서 짧은 BPF snaplen을 사용해 원래 프레임 길이가 잘렸던 코드 오류를 발견했다. BPF는 원래 길이를 보존하고 recvmsg는 헤더만 복사하도록 수정했다. 반복 파싱을 줄이고 주소 필터를 커널에 적용했으며 캡처 drop이 있었던 창을 거부하도록 했다. 이 초기 실패를 실제 PHY 관측 한계와 혼동하지 않는다. 수정 후 무경쟁 DDS 추정은 나왔지만 B2 가시성 부족은 남았다.</p>')
    s+='<p>다음 검증의 우선순위는 <b>B2에서 source-local 수동 프레임 가시성을 확보하는 것</b>이다. 후보는 같은 송신 호스트의 별도 수신 인터페이스 또는 현재 driver/firmware에서 누락 구간을 확인·보정할 수 있는 추가 관측이다. 독립 PPDU 전체가 식별됐다고 가정하지 않는다. 관측 경로가 개선되면 계수를 다시 교정해 동결하고, 새 자기 부하·B2·C2·PHY 변화에서 검증한 뒤에만 adaptive-sender의 HTB 갱신을 승인한다.</p>'
    restoration=BASE/'final_restoration.json'
    s+='<p>'+('최종 복원 자료: '+link('final_restoration.json','final_restoration.json') if restoration.exists() else '최종 복원은 실행 중이다. 완료 후 영수증을 추가한다.')+'</p>'
    s+='<p>원자료: <code>ROSPacer/runs/w1_20261013_sender_only/</code>. 코드·시험 조건: <a href="../../../ROSPacer/docs/sender-only-prototype.md">sender-only-prototype.md</a>.</p>'
    s+='<p>'+link('frozen_sender_profile_v2.json','고정 sender profile')+' · '+link('dds_v4_fastdds/4/sender.csv','Fast source CSV')+' · '+link('dds_v5_cyclonedds/4/sender.csv','Cyclone source CSV')+' · '+link('validationB2_100/validation.json','B2 보류 근거')+'</p>'
    gap='W1 송신 관측 누락 진단_261013.html'
    if (ROOT.parent/'html 파일 모음/결과/W1 실험결과'/gap).exists():
        s+='<p id="sender-gap-reference"><a href="'+gap+'">10월13일 추가: Sender B2 관측 누락 진단과 경로 보강</a> — CRC 오류·CTS 필터 누락 확인, 제어 프레임 관측 보강. Sender-only adaptive 승인은 보류.</p>'
    s+='</main></html>'
    dest=ROOT.parent/'html 파일 모음/결과/W1 실험결과'/NAME;dest.write_text(s,encoding='utf8');print(dest)


if __name__=='__main__':main()
