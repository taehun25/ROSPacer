"""Publish bounded sender capture diagnosis, including failed trials."""
import csv
import hashlib
import html
import json
from pathlib import Path
import subprocess
from deploy import ROOT

BASE=ROOT/'runs/w1_20261013_sender_gap'
NAME='W1 송신 관측 누락 진단_261013.html'
DEST=ROOT.parent/'html 파일 모음/결과/W1 실험결과'/NAME

def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def detail(title,body):return '<details><summary>'+title+'</summary><div>'+body+'</div></details>'
def link(path,title):return '<a href="../../../ROSPacer/runs/'+path+'">'+title+'</a>'

def main():
    labels=['clean_fcs_retry','b2_fcs_1','observer_clean','observer_b2','control_clean','control_b2']
    results={n:json.loads((BASE/n/'gap_analysis.json').read_text()) for n in labels}
    s='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>W1 송신 관측 누락 진단 · 2026-10-13</title><style>
body{font:16px/1.75 system-ui,sans-serif;color:#24364d;background:#f3f6fa;margin:0}main{max-width:1180px;margin:24px auto;background:white;padding:32px;border-radius:10px}h1{font-size:28px}h2{margin-top:34px;border-bottom:1px solid #d4dfeb;padding-bottom:8px}table{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}th,td{padding:11px;border-bottom:1px solid #d7e1eb;text-align:left;vertical-align:top}th{background:#edf2f8}.scroll{overflow:auto}.status{background:#fff3d7;border-left:4px solid #ae7a20;padding:18px}details{border:1px solid #d3dfeb;border-radius:6px;margin:15px 0}summary{padding:12px;cursor:pointer;font-weight:650;background:#f5f8fc}details>div{padding:15px}code{overflow-wrap:anywhere}a{color:#175d99}.muted{font-size:14px;color:#566b81}i,.eq{font-family:Cambria,serif;font-style:italic}@media(max-width:650px){main{margin:0;padding:18px}h1{font-size:24px}}
</style></head><body><main><h1>W1 송신 측 관측 누락 진단과 경로 보강</h1><p class="muted">2026-10-13 · 4번의 송신 측 입력만 사용하는 경로 · 수신측 캡처는 오프라인 검사 참조</p>
<div class="status"><b>CRC 오류로 인한 정상 프레임 관측 부족과 CTS 주소 필터 누락을 확인하고 수집 코드를 보강했다.</b><p>전체 공중 프레임 누락의 단일 원인까지 확정하지 않았다. CRC 오류 프레임을 정상 데이터에 합치지 않았으며, RTS 예약 시간으로 airtime을 대체하지 않았다. 기존 sender profile은 validated=false를 유지한다. Sender-only 적응형 제어의 B2/C2 승인과 자동 HTB 갱신은 미완료다.</p></div>
<h2>1. 이번 시험의 조건</h2>'''
    s+=table(['항목','조건'],[['주 송수신','4번(csilab, 192.168.0.4) → AX1500 → 5번(csi, 192.168.0.5)'],['무선','두 iptimeAX1500SR AP의 채널149·80MHz. 주 AP는 iptime5GAX1500, 경쟁 AP는 iptime5GAX1500SR2'],['B2 경쟁','12번 → SR2 → 10번, UDP300Mb/s 요청48초. 주 UDP100Mb/s 요청8초'],['비교 창','주 발행 시작 후1.5초~종료 전1.5초 안의 source counter 샘플 사이 약5초'],['관측','같은 MT7921 라디오의 임시 monitor, radiotap MAC 헤더 캡처160B, survey/station/하드웨어 오류 계수200ms'],['관리','4·5번 직접 유선50.2/50.1. 송신 절전off·CPU performance 임시 적용, 종료 후 원복'],['변경 범위','새 드라이버 설치 없음. UDP 진단에서는 DDS XML과 maxMessageSize를 사용하지 않음. HTB 미적용']])
    s+=detail('B2·clean·observer 조건과 비교의 한계','<p><b>B2</b>는 다른 AP의 같은 채널에서 경쟁 UDP를 켠다. <b>clean</b>은 그 경쟁 UDP를 끈 조건이며, 외부의 모든 RF 신호가 없다는 뜻은 아니다. 이번 B2는 연속 경쟁 진단이고 proposal의2초 ON/2초 OFF 정식 시험과 구분한다.</p><p><b>observer</b>는 4번이 사용자 데이터를 송신하지 않고 현재 PC(192.168.0.11)가 AP를 통해5번으로 보내는 조건이다. 4번의 관측 창에서 TX 증가0을 확인했다. PC의 VHT 상향과4번의 HE 상향은 같지 않고 시험도 순차 실행이므로, 차이를 송신 blind 구간의 정확한 기여율로 환산하지 않는다.</p><p>5번은 일반 수신기와 검사 후 캡처 참조다. 온라인 제어기로 수신 통계를 전달하지 않는다. 수신 캡처 시계의 약9ms 차이는 MAC 헤더·길이·시각 후보 매칭으로 추정했으며 정밀 종단 지연이나 물리 프레임 손실률에 사용하지 않는다.</p>')
    s+='<h2>2. 데이터 관측률과 CRC 오류</h2>'
    rows=[]
    for n,r in results.items():
        rows.append([n,f"{r['source_tx_fraction']*100:.2f}%",f"{r['busy_fraction']*100:.2f}%",f"{r['good_body_coverage']*100:.2f}%",f"{r['all_candidate_body_coverage']*100:.2f}%",r['low_level_delta']['dot11FCSErrorCount'],r['source']['signal_dbm_median']])
    s+=table(['run','4번 TX/active','4번 busy/active','정상 CRC body 관측','오류 CRC 포함 후보','HW FCS 오류 증가','data RSSI 중앙값(dBm)'],rows)
    s+=detail('각 수치의 의미와 잘못 해석하기 쉬운 부분','<p><b>정상 CRC body 관측</b>은4번에서 정상 CRC로 보인 AP→5번 MAC body byte를4번 송신 station byte로 나눈 대리값이다. observer에서는 PC가 보낸 UDP payload byte가 분모다. 두 분모 정의를 구분해야 한다. header·aggregation·재전송·관측 창 경계 때문에 이 수치가 정확한 전달률은 아니다.</p><p><b>오류 CRC 포함 후보</b>는 CRC 오류로 표시된 프레임의 주소·길이를 잠정적으로 사용한 진단량이다. 주소 헤더도 손상됐을 수 있다. 수신 성공 byte, 정상 PHY 입력 또는 제어기 coverage로 사용하지 않는다. observer clean에서100%를 조금 넘은 것도 이 대리량의 한계이며 전달률100% 초과라는 뜻이 아니다.</p><p><b>HW FCS 오류</b>는 debugfs의 dot11FCSErrorCount 증가이며 이 라디오 전체의 캐시된 카운터다. 우리 AP/5번의 오류만 세는 값이 아니고 프레임별 bad-FCS 개수와 같지도 않다. 접근 불가 시 None으로 기록하고0으로 대체하지 않는다. <b>RSSI</b>는 이미 관측된 프레임의 신호 세기이며 포착하지 못한 프레임의 상태를 알려주지는 않는다.</p>')
    s+='<h2>3. 확인한 원인과 남은 구분</h2>'
    s+=table(['항목','증거','판정'],[['CRC 오류 프레임 제외','b2_fcs_1 정상32.13% → CRC 오류 후보 포함72.74%; source HW FCS 오류3765 증가','정상 CRC 관측 부족의 상당 부분을 설명하는 경로 확인'],['호스트 캡처 큐 드롭','유효6개 run의 source tcpdump kernel drop0, MAC 파싱 오류0','이번 누락을 호스트 큐 드롭으로 설명하는 증거 없음; 공중 누락0의 증명 아님'],['CTS 필터 누락','CTS는 TA가 없고 RA만 AP. 기존4·5 MAC 주소 필터에 해당하지 않음','소프트웨어 필터 누락 확인·수정'],['자기 송신만의 영향','observer_b2에서 source TX0인데 정상68.73%, CRC 후보 포함84.73%','송신 중 blind 구간만으로 전체 누락 설명 불가'],['beamforming/PHY','포착된 데이터는 HE SU, radiotap TXBF 표시false; RSSI 약−46~−49dBm','포착되지 않은 프레임과 실제 RF 송신 정책까지 단정할 수 없음'],['남은 공중/RX 누락','CRC 후보 포함도 B2에서 약73~85%; 순차 run 간 변동 존재','간섭·수신 불가 구간·HW/firmware 전달·타이밍의 기여를 완전히 분리하지 못함']])
    s+='<p>설치된 Ubuntu6.8.0-138용 mt7921 코드는 FIF_FCSFAIL을 지원하고 FCS_ERR 수신 상태를 RX_FLAG_FAILED_FCS_CRC로 전달한다. 이전 monitor 요청은 control·otherbss만 사용했다. 현재는 fcsfail을 추가해 오류 경로를 볼 수 있게 했다. 드라이버 원문과 소스 버전을 보존했다.</p>'
    s+='<h2>4. 보강한 RTS·CTS·Block ACK 경로</h2>'
    rows=[]
    for n in ['control_clean','control_b2']:
        r=results[n];a=r['control_diagnostic']['4'];ref=r['control_diagnostic']['5'];ca=a['counts'];cr=ref['counts']
        ratio=ca['peer_rts_good']/cr['peer_rts_good']
        rows.append([n,ca['peer_rts_good'],cr['peer_rts_good'],f'{ratio*100:.2f}%',ca.get('peer_rts_cts_candidates',0),ca.get('peer_rts_cts_ba_candidates',0),a['rts_nav_us_median'],a['rts_to_ba_minus_nav_us_median']])
    s+=table(['조건','4번 AP→5 RTS','5번 참조 RTS','RTS 개수 비율','RTS-CTS 후보','RTS-CTS-BA 후보','NAV 중앙값(µs)','BA timestamp−NAV 차이 중앙값(µs)'],rows)
    s+=detail('RTS·CTS·BA·NAV·TSFT와 수식 적용 보류','<p><b>RTS</b>(Request To Send)는AP가5번에 보내는 전송 예약 요청, <b>CTS</b>(Clear To Send)는그에 대한 응답이다. CTS는 송신자 TA가 없으므로 AP로 향하는 모든 CTS를5번 것이라고 간주하지 않는다. 직전 AP→5 RTS와 동일 로컬 타임스탬프의20~200µs 차이, NAV 감소량과 그 차이의 일치(±4µs)를 함께 만족해야 후보로 묶는다.</p><p><b>Block ACK/BA</b>는5번이AP에 보내는 묶음 수신 확인이다. 그 후보 응답을 기록하되 실제 PPDU 수와 같다고 가정하지 않는다. 다른 RTS가 등장하면 미완결 후보로 분리한다. CTS를 놓치거나 BA를 놓친 것도 완결 교환으로 만들지 않는다.</p><p><b>NAV</b>(Network Allocation Vector)는 MAC Duration/ID의 예약 구간 정보다. 예약돼도 실제 사용되지 않을 수 있고 충돌·재시도·TXOP와 다르다. <b>TSFT</b>는 radiotap 타이머이며 표준 설명은 첫 MPDU bit의 MAC 도착 시각이다. 현재 driver의32bit 수신 타이머는 래핑을 처리하지만 실제 시간 의미가 충분히 교정됐다는 뜻은 아니다.</p><p>이번 RTS→BA 타임스탬프와 NAV는 중앙값 기준91/99µs 차이가 있었다. 원인을 HE/BA duration이나 타이머 위치로 하나로 확정하지 않았다. <b>NAV 합계를 busy에서 빼거나 이를 전체 airtime으로 쓰지 않는다.</b> RTS 개수 비율은 오프라인 시각 정렬 후의 개수 비교이지, 개별 프레임이97%/90% 정확히 포착됐다는 물리 검증은 아니다. 암호화 A-MSDU 내부의 원송신자도 여전히 구분되지 않아 receiver exclusivity 가정이 남는다.</p>')
    s+='<h2>5. 실제 코드에 반영한 항목</h2>'
    s+=table(['코드/기능','반영'],[['sender monitor','control·otherbss·fcsfail. AP 주소를 가진 제어 프레임을 BPF에 추가. 원래 frame 길이는 보존하고 헤더만 복사'],['decode','Duration/ID, TSFT, legacy PHY rate, bad FCS 표시. CTS/ACK 뒤의 FCS/padding을 TA로 잘못 읽지 않음'],['sender CSV','control_diagnostic·crc_diagnostic·source_fcs_error_delta·counter availability를 유효/hold 창 모두 기록'],['추정 게이트','CRC 오류 byte는 coverage/serialization에 포함하지 않음. 부족한 body/PHY/캡처 drop이면 hold 유지'],['측정 실패','연결2초 timeout·전체 유한 실행·실패 캡처 회수·실패 run 분석 제외'],['자동 검사','52개 통과; CRC 데이터 승격 방지·CTS TA·제어 교환 매칭·타이머 래핑·결측 계수 처리 확인']])
    s+='<h2>6. 두 DDS에서 강화한 live 관측 로그 확인</h2>'
    live=[]
    for rmw in ['fastdds','cyclonedds']:
        folder=ROOT/'runs/w1_20261013_sender_only'/('dds_gap_v6_'+rmw)
        r=json.loads((folder/'summary.json').read_text());trace=list(csv.DictReader((folder/'4/sender.csv').open()))
        diagnostics=[row for row in trace if row['control_diagnostic']]
        fcs=[int(row['source_fcs_error_delta']) for row in trace if row['source_fcs_error_delta']]
        live.append([rmw,f"{r['planned']}/{r['published']}/{r['received']}",r['sender_estimates'],len(diagnostics),max(fcs) if fcs else '결측',r['monitor_removed'],r['qdisc_unchanged']])
    s+=table(['DDS','예정/발행/수신','유효 추정 횟수','제어/CRC 진단 로그 창 수','창 내 FCS 증가 최댓값','monitor 삭제','qdisc 불변'],live)
    s+=detail('DDS 시운전의 설정·해석','<p>4→5, UInt8MultiArray1MiB, RELIABLE·KEEP_ALL·VOLATILE, 약0.2C₀·15초 발행, Static XML, 고정 Fast2.6.11/Cyclone0.10.5 runtime이다. 송신 측 shadow38초이며 약200ms마다 약3초 창을 본다. 유효 추정 횟수는 메시지 수나 HTB 갱신 횟수가 아니다.</p><p>기존 frozen sender profile을 재맞추지 않았다. 수신 피드백 없이 진단·추정/보류가 함께 기록되는지 확인한 무경쟁 기능 시험이다. B2의 모델 예측 오차나 adaptive 성능 우위를 통과한 시험이 아니다. counter가 radio 전체의 캐시값이므로 겹치는 창의 delta를 모두 더해 누적 오류 수로 쓰지 않는다. 시계 미승인으로 새 종단 지연은 분석하지 않는다.</p>')
    s+='<h2>7. 실패 반복과 무선 접속 문제</h2><p><code>control_b2_repeat</code>는 main iperf 제어 연결14초 timeout으로 종료됐다. 유효 전달 부하가 없으므로 위 표와 모델 검증에서 제외했다. monitor와 counter는 유한 시간 후 종료됐고 양쪽 캡처·오류 기록을 유선으로 회수했다. 종료 후4→5 ARP 실패가 확인됐으며 같은 AX1500 프로파일 재연결 뒤 ping이 복구됐다. 30분 커널 로그에는 관련 메시지가 없었다. monitor가 유일한 원인인지, 기존 무선 접속 문제와 같은 원인인지는 확정하지 않았다.</p>'
    s+='<h2>8. 복원·판정·다음 구현</h2>'
    restoration=BASE/'final_restoration.json'
    s+=('<p>'+link(BASE.name+'/final_restoration.json','최종 복원·4대 장비 점검')+'</p>') if restoration.exists() else '<p>최종 복원 점검 대기.</p>'
    if restoration.exists():
        r=json.loads(restoration.read_text())
        s+='<p><b>설정 복원 확인:</b> 임시 monitor·실험 트래픽 종료, noqueue·rmem/wmem212992·절전on·4번 CPU powersave, 임시 유선50.2/50.1 제거를 확인했다. 4번은 주소 제거 후 Wi-Fi UDP로 서명된 최종 영수증을 보내 실제 제거 상태를 확인했다.</p>'
        if not r.get('source_wifi_ssh_qualified',False):s+='<p><b>별도 접속 문제:</b> 4번 Wi-Fi SSH의 정상 명령 실행은 확인되지 않았다. ping·SSH 인증은 성공했지만 양방향 TCP 재전송이 누적됐고 절전off에서도 이번 점검은 해결되지 않았다. 실험 준비 전에도 Wi-Fi 접속 문제가 있었다. 원인이나 원상태 대비 영향은 확정하지 않았으며, Wi-Fi 관리 접속이 정상이라고 표시하지 않는다.</p>'
    s+='<p>정상 CRC 데이터에만 의존하던 경로에 오류 계수와 제어 교환을 추가했고 B2에서 확인했다. 남은 방향은 <b>제어 교환의 시간 의미를 독립 교정하거나, 같은 송신 호스트의 별도 수신 라디오로 공중 관측을 강화하는 것</b>이다. 별도 라디오도 receiver telemetry 없이 sender-local 입력으로 유지할 수 있다. 어떤 경로든 프로파일을 새로 동결하고 자기 부하·B2·C2를 새 자료로 검증한 뒤에만 자동 제어를 승인한다. Receiver-assisted 구현은 보존한다.</p>'
    s+='<h2>9. 원자료와 참고</h2><p>'+' · '.join(link(BASE.name+'/'+n+'/gap_analysis.json',n) for n in labels)+'</p><p>'+link(BASE.name+'/control_b2_repeat/failure.json','실패 반복 기록')+' · '+link(BASE.name+'/manifest.json','코드 SHA/버전·범위')+'</p>'
    s+='<p><a href="https://radiotap.org/fields/TSFT.html">radiotap TSFT 정의</a> · <a href="https://android.googlesource.com/kernel/common/+/e095493091e850d5292ad01d8fbf5cde1d89ac53/drivers/net/wireless/mediatek/mt76/mt7921/main.c">mt7921 RX filter 참조</a>. 설치 커널의 정확한 원문: <code>ROSPacer/runs/w1_completion_readiness/survey_driver_fix/source/ubuntu_138/mt76/</code>. 실험 증거와 시간 의미를 구분한다.</p></main></body></html>'
    fix=ROOT/'runs/w1_20261013_ssh_repair/verification.json'
    if fix.exists():
        v=json.loads(fix.read_text())
        s=s.replace('<b>별도 접속 문제:</b>','<b>이 복원 검사 당시의 접속 문제:</b>',1)
        follow='<h2 id="ssh-repair">10. 후속: 4번 Wi-Fi SSH 수정과 재검증</h2><p><b>해결 확인:</b> 위 복원 검사 당시의 SSH 미해결 상태는 후속 검사에서 해결했다. 4번 SSH 서버에 IPQoS0x00(cs0/cs0)을 적용했다. 기존 유효 설정은 lowdelay/throughput이었다. 캡처에서 TOS0x10→0x08 전환 직후4→5 응답이5번 수신 캡처에 나타나지 않았고 양방향 TCP 재전송이 누적됐다. 작은 MSS와 절전off만으로는 해결되지 않았다.</p>'
        follow+=table(['검증','결과'],[['임시 SSH 포트에서 IPQoS0','명령 즉시 성공'],['22번 포트에 새 설정 적용','직접 Wi-Fi SSH 성공'],['기존 설정으로 잠시 복귀',f"rc={v['old_qos_restored_test']['rc']}, 8초 timeout 재현"],['IPQoS0 재적용',f"{v['new_qos_repeated_successes']}회 연속 명령 성공"],['양방향 전송',f"각 {v['two_way_bytes_each']:,}B, SHA-256 일치"],['임시 진단 종료','PC tunnel·임시 sshd·tcpdump 종료 후 직접 SSH 재확인']])
        follow+=detail('IPQoS·변경 파일·해결 범위','<p><b>IPQoS</b>는SSH의 IP 패킷에 붙이는 우선순위/TOS 표시이며 DDS의 RELIABLE·KEEP_ALL QoS와는 별개다. 4번의 <code>/etc/ssh/sshd_config.d/00-rospacer-wifi-ipqos.conf</code> 한 개에 <code>IPQoS 0x00</code>을 넣었다. 기존 SSH 설정·인증키·권한·암호화는 유지하고 sshd 설정 검사 후 reload했다. 재부팅 후에도 적용된다. 원복은 이 작업에서 만든 파일만 제거하고 ssh 서비스 reload하는 방식이다.</p><p>반복과 전송 검증은 임시PC 터널 없이 기존5→AP→4 Wi-Fi의22번 포트에서 했다. 우선순위 설정과 증상의 관계는 재현·해소·원복·재해소로 확인했다. AP 내부 WMM 처리와 칩셋/driver 중 정확한 손실 위치까지 확정하지 않았다. <b>B2의 수동 monitor 관측 부족이 해결됐다는 뜻은 아니다.</b> 두 문제의 동일 원인도 확인되지 않았다.</p><p><a href="https://man.openbsd.org/OpenBSD-7.1/sshd_config.5#IPQoS">OpenSSH IPQoS 옵션 정의</a>. 장비의 실제 기본값은 웹 문서에서 추정하지 않고 설치 sshd -T 출력과 캡처로 확인했다.</p>')
        follow+='<p>'+link('w1_20261013_ssh_repair/applied_ipqos.json','적용 설정·검사')+' · '+link('w1_20261013_ssh_repair/verification.json','재현·반복·전송 검증')+' · '+link('w1_20261013_ssh_repair/final_audit.json','임시 진단 종료')+'</p>'
        s=s.replace('</main>',follow+'</main>',1)
    DEST.write_text(s,encoding='utf8')
    manifest={'date':'2026-10-13','scope':'sender-local CRC/control diagnostics; continuous B2 topology; not adaptive approval','commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'dirty_source':True,'files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['rospacer/sender_radio.py','tools/w1_gap_analyze.py','tools/w1_monitor_guard.py','tools/w1_counter_worker.py','tools/w1_sender_probe.py','tools/w1_sender_b2.py','tests/test_sender_radio.py']},'receiver_feedback':False,'HTB':False,'profile_validated':False,'tests_passed':52}
    (BASE/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    # Add evidence links without replacing the older experiment's results.
    for path in [ROOT.parent/'html 파일 모음/W1 보고서.html',DEST.parent/'W1 보고서.html',DEST.parent/'W1 무선 입력 추가 검증_261013.html',DEST.parent/'W1 송신 측 수동 관측 프로토타입_261013.html']:
        if not path.exists():continue
        original=path.read_text(encoding='utf8')
        if 'id="sender-gap-reference"' in original:continue
        href=('결과/W1 실험결과/' if path.parent==ROOT.parent/'html 파일 모음' else '')+NAME
        note='<p id="sender-gap-reference"><a href="'+href+'">10월13일 추가: Sender B2 관측 누락 진단과 경로 보강</a> — CRC 오류·CTS 필터 누락 확인, 제어 프레임 관측 보강. Sender-only adaptive 승인은 보류.</p>'
        marker='</main>' if '</main>' in original else '</body>'
        path.write_text(original.replace(marker,note+marker,1),encoding='utf8')
    print(DEST)

if __name__=='__main__':main()
