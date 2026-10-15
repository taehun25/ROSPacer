"""Report verified sender-local W1 evidence; never upgrades failed gates."""
import hashlib
import html
import json
from pathlib import Path
import statistics
import subprocess
import tarfile
from deploy import ROOT
from w1_sender_integrated import BASE

REPORT = ROOT.parent/'html 파일 모음/결과/W1 실험결과/W1 송신 측 단독 교정·제어 통합 검증_261014.html'


def read(p):
    return json.loads(p.read_text())


def table(headers, rows):
    def cell(v): return '<td>'+html.escape(str(v))+'</td>'
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(cell(x) for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def main():
    sender=BASE/'sender4'; validation=[]; errors=[]
    for p in sorted(sender.glob('validation*/validation.json')):
        r=read(p);c=r['receiver_phy_calibrated'];s=r['downlink_equals_uplink']
        validation.append([p.parent.name,r['condition'],f"{c['predicted_Mbps']:.3f}" if c['predicted_Mbps'] is not None else '계산 불가',
                           f"{c['measured_Mbps']:.3f}",f"{c['relative_error']*100:.2f}%" if c['relative_error'] is not None else '미정',
                           f"{c['usable_fraction']*100:.1f}%",'통과' if c['passed'] else '실패',
                           f"{s['relative_error']*100:.2f}% / {s['usable_fraction']*100:.1f}%" if s['relative_error'] is not None else '계산 불가'])
    for p in sorted(sender.glob('validation*.log')):
        if not (sender/p.stem/'validation.json').exists():errors.append([p.stem,p.read_text()[-600:]])
    trials=[];groups={}
    for p in sorted(sender.glob('smoke*/**/results.json')):
        for r in read(p):
            m=r['metrics'];g=r.get('govern',{});caps=r.get('cap_Mbps_range',[])
            trials.append([r['condition'],r['rmw'],r['mode'],r['rep'],f"{r['planned']} / {r['published']} / {r['received']}",
                           f"{m['actual_publish_hz']:.3f}",f"{m['arrival_interval_goodput_Bps']*8/1e6:.3f}",
                           f"{m['arrival_jitter_ms']['p95']:.3f}",g.get('HTB_changes','해당 없음 — HTB 미적용'),
                           f"{min(caps):.2f}~{max(caps):.2f}" if caps else '해당 없음 — HTB 미적용',r.get('fq_drops','해당 없음'),r['qdisc_restored']])
            groups.setdefault((r['condition'],r['rmw'],r['mode']),[]).append(m['arrival_interval_goodput_Bps']*8/1e6)
    medians=[[condition,rmw,mode,len(v),f'{statistics.median(v):.3f}'] for (condition,rmw,mode),v in sorted(groups.items())]
    restore=read(BASE/'final_restoration.json') if (BASE/'final_restoration.json').exists() else {'complete':False,'checks':{}}
    links=[('송신 측 교정·제어 코드',ROOT/'rospacer/sender_minphy.py'),('사용 방법과 범위',ROOT/'docs/sender-local-minphy.md'),
           ('실험 조건 사전 기록',BASE/'controlled_protocol.json'),('송신 전용 배치 기록',BASE/'deployment.json'),
           ('종료 복원',BASE/'final_restoration.json'),('코드 검사',BASE/'unit_tests.txt'),('원자료 해시',BASE/'evidence_sha256.json')]
    import os
    linkhtml='<ul>'+''.join('<li><a href="'+html.escape(os.path.relpath(p,REPORT.parent).replace('\\','/'))+'">'+name+'</a></li>' for name,p in links if p.exists())+'</ul>'
    text='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>W1 송신 측 단독 교정·제어 통합 검증</title><style>body{background:#f3f6fa;color:#25364b;font:16px/1.8 system-ui,sans-serif;margin:0}main{max-width:1200px;margin:24px auto;background:white;padding:30px}h1{font-size:28px}h2{margin-top:32px;border-bottom:1px solid #d4dfeb}.note{background:#fff4df;padding:18px;border-left:4px solid #a97617}table{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}td,th{padding:10px;border-bottom:1px solid #d4dfeb;text-align:left;vertical-align:top}th{background:#edf2f8}.scroll{overflow:auto}details{border:1px solid #d4dfeb;margin:16px 0}summary{padding:12px;cursor:pointer;font-weight:650}details>div{padding:16px}.math,i{font-family:Cambria,"Times New Roman",serif;font-style:italic}a{color:#175e99}code{overflow-wrap:anywhere}</style></head><body><main><h1>W1 송신 측 단독 교정·제어 통합 검증</h1><p>2026-10-14 · ROSPacer 새 코드 배치는 송신4번만 · 초기 수신 PHY 교정 · 실행 중 송신 관측만</p>'''
    text+=f'<div class="note"><b>종료·복원 완료: {restore["complete"]}</b><p>송신 측 단독 배치, 모델의 용량 예측, 실제 제어 성능을 별도로 판정한다. 초기 수신 PHY 교정은 필요하다. 원래 물리 airtime·경쟁 점유율의 완전한 분해나 W2의 정식 성능 우위를 완료했다고 주장하지 않는다.</p></div>'
    text+='''<h2>1. 송신 측 통합</h2><p><code>sender-calibrate</code>가 송신4번에서 초기 표준 도구 시험을 실행하고 PHY·RTT·처리량을 읽어 계수·교정 파일·Static XML을 만든다. 수신5번에서는 기존 SSH·iw·iperf3만 사용한다. <code>sender-validate</code>는 고정한 계수를 새 시험에서 평가한다. <code>sender-govern</code>은 송신4번의 로컬 무선 통계로 HTB를 갱신하며 수신 SSH 계정·키·피드백을 입력받지 않는다. 이전 ACK/Receiver-assisted 코드는 보존했다.</p><p>제어 PC는 이 검증에서 코드 배포·유한 작업 시작·원자료 회수와 경쟁12/10 준비에 사용했다. 초기 교정·계수 계산·XML 생성·실시간 제어의 실행 위치는 송신4번이다. 교정 중 제어 PC가 다른 AP에 있어도 송신 작업은 계속됐다. 4/5에 유선 관리 IP를 추가하지 않았다. 교정용 SSH 키는 iw와 제한 시간/포트 iperf3 및 교정 검증용 UDP 계수기 읽기로 제한한다. 성능 측정용 SSH 키는 실험 종료 때 제거한다.</p>
<details><summary>설치와 관측의 의미·수신 측 의존성</summary><div><p>송신 측에만 ROSPacer를 설치한다는 것은 교정·계수 계산·제어 프로그램을 송신 측에서 실행한다는 의미다. 초기 교정에는 수신 측 정보와 기존 표준 도구/SSH 권한이 필요하다. 따라서 초기 교정까지 정보 출처가 송신 측뿐이라는 주장은 하지 않는다. 실행 중에는 수신 측 통계 에이전트·유선 피드백·상시 PHY 피드백이 없다. 측정용 기존 ROS subscriber와 종료 후 결과 회수는 제어 입력이 아니다.</p><p>현재 CLI는 MT7921·149번/80MHz·수신자1개·1MiB DDS 시험 범위의 W1 프로토타입이다. 수신 이동으로 하향 PHY가 달라지는 것은 송신 측만으로 확실히 감지하지 못하며 재교정이 필요하다.</p></div></details>
<h2>2. 교정 근거와 조건</h2><p>최초 기본 버퍼/수신 절전 조건의 교정242.509Mb/s는 Clean을 통과했지만 B2 오차37.30%로 실패했다. 그 자료를 보존하고 자동 제어를 승인하지 않았다. 이후 양쪽 절전 off·CPU performance·커널 rmem/wmem_max4MiB·명시적 UDP 소켓1MiB로 조건을 통일했다. 동일한 계수 계산식으로 새 idle/50/150/포화 교정 자료만 사용해 고정했다. 새 UDP 교정348.909Mb/s, 송신 측 ping 평균19.580ms, 수신 PHY1200.9Mb/s다. 수정 모델에 맞춘 계수이며 물리 고정 비용 O가 아니다.</p><p>제안서의 하향=상향 가정과 수신 PHY 사용을 같은 수정 모델에서 비교했다. 제안서 원식은 TX≤busy가 성립하지 않아 그대로 검증했다고 할 수 없다. 계산 불가는 오차20% 초과로 바꾸지 않는다. 같은 수정 모델의 PHY 입력 비교는 원식 전체의 도입 조건을 소급 입증하지 않는다.</p>
<details><summary>유효 비용·교정과 검증의 분리</summary><div><p>idle은 경쟁 UDP와 ROS 발행을 켜지 않은 기준이다. load50/150은 교정 UDP 요청50/150Mb/s, capacity는600Mb/s 요청 포화다. 처리량은 수신 iperf의 interval바이트/시간으로 계산하며 server end bytes0은 사용하지 않는다. 계수는 이 교정 자료로만 계산한다. Clean/B2/C2 검증은 새15초 시험이며 검증 뒤 계수를 바꾸지 않는다. PHY는 데이터 처리량이 아니라 AP→수신 단말의 마지막 보고 물리 전송률이다.</p><p>B2는 같은 채널의 다른 AP(SR2)에12/10을 붙여 경쟁 UDP를 만드는 조건, C2는 측정 AP(AX)에12/10을 붙이는 조건이다. 여기서는 연속 경쟁300Mb/s 요청을 사용하는 W1 교정 시운전이다. 제안서 본 평가 B2의2초 on/off와 C2의0.9C0 및 W2 F 동적 단계 시험을 완료한 것은 아니다.</p></div></details>'''
    text+='<h2>3. 독립 용량 검증과 PHY 입력 비교</h2>'+table(['실행','조건','교정 PHY 예측 Mb/s','실측 Mb/s','오차','계산 가능','판정','하향=상향 오차 / 계산 가능'],validation)
    if errors:text+='<details><summary>측정을 완료하지 못한 실행·사유</summary><div>'+table(['실행','보존한 로그'],errors)+'</div></details>'
    text+='''<p>통과 기준은 용량 오차≤20%와 평가 대상 구간 계산 가능≥95%다. 계산 가능100%는 전체 시간·모든 환경의 보장값이 아니다. 점유율 잔차 z는 물리적 경쟁 점유율로 확정하지 않는다. 검증 실패 파일을 제어 명령에 전달하면 시작을 거부한다.</p><h2>4. 실제 DDS 비교 시운전</h2><p>송신4→수신5, 기존 수정 없는 고정 Fast DDS2.6.11/CycloneDDS0.10.5 closure, UInt8MultiArray1MiB·random+순번/시각, RELIABLE KEEP_ALL VOLATILE. 요청30Hz·15초·450개다. 동일한 송신 측 계산 Static XML을 사용하고 Static은HTB 없음, Fixed는동일HTB 상한 고정, Adaptive는최소PHY 운용 모델로 갱신한다. 두 반복의 비교 순서는 Static/Adaptive/Fixed와 Fixed/Adaptive/Static이다. 데이터는 Wi-Fi, 종단 시계가 새로 검증되지 않아 E2E 지연은 계산하지 않는다. p95 지터는 도착 간격과33.333ms의 절대차이며 발행 역압 영향도 포함한다.</p>'''
    text+=table(['조건','DDS','방식','반복','계획 / 발행 / 수신','발행 Hz','유효처리량 Mb/s','도착 간격 지터 p95 ms','HTB 변경','상한 Mb/s','fq drop','복원'],trials)
    text+=table(['조건','DDS','방식','반복 수','유효처리량 중앙값 Mb/s'],medians)
    text+='<div class="note"><b>성능 판정: Adaptive 우위 미확인.</b><p>CycloneDDS는 Adaptive133/139개, Fixed213/204개, Static219/209개를 발행·수신했다. Adaptive의 유효처리량 중앙값 약76.19Mb/s는 Fixed 약116.51Mb/s보다 낮았고 지터도 더 컸다. Fast DDS는 반복 간 변동이 커 우위를 판정하지 않는다. 용량 예측 게이트 통과를 DDS 성능 개선으로 해석하지 않는다. 현재 제어기를 기본 자동 운영 방식으로 채택할 근거는 부족하다.</p></div>'
    text+='<p>두 반복15초는 W1 작동·성능 시운전이다. 실제 경쟁률의 차이를 함께 보며 숫자 차이를 W2의 통계적 우위로 승격하지 않는다. 발행한 데이터의 수신100%만으로 요청450개를 모두 처리했다고 주장하지 않는다.</p>'
    text+='<details><summary>송신 상한과 지표를 읽는 방법·실험의 한계</summary><div><p>상한 Mb/s 범위는 준비·발행·배출을 포함한 전체 제어 로그의 값이다. 이는 실제 ROS 유효처리량이나 HTB class 전송률과 다르다. 갱신은 새 무선 통계로 계산해 tc class change를 적용하는 일이며 Fixed는0회다. 모든 Adaptive의 실제 발행 구간에서 계산 가능 비율은100%였고, 적용한HTB/fq에서는drop0이었다. 계산이 계속 된다는 사실만으로 좋은 상한을 선택했다고 볼 수 없다.</p><p>기존 수정 없는 런타임은12개 실행의 송·수신 실제 라이브러리 경로와 해시로 확인했다. ROSPacer를 수신 측에 새로 설치하지 않았지만, 비교를 위해 수신 DDS에 Static XML과 커널버퍼를 적용했다. 수신 기본 설정에서도 같은 결과가 나온다는 의미는 아니다. 전체 경쟁UDP는600초 요청300Mb/s로 켜 두었다. 같은 요청률이어도 각15초 동안 실제 경쟁률은 변하므로 두 반복의 차이는 정식 효과 크기가 아니다.</p></div></details>'
    text+='<h2>5. 결측·변경·종료 복원</h2><p>AP/채널/드라이버 변경은 시작 전에 거부한다. 실행 중 결측·초기화·관측 공백은 상한 갱신을 보류하고 계수기로0을 대입하지 않는다. 정상 종료·SIGTERM·독립 만료 감시가 자신이 만든HTB/fq만 제거한다. 기존 root qdisc는 보존한다. 임시 실험 프로세스·CPU/절전·커널버퍼와 경쟁AP 프로파일은 실험 전 상태로 복원한다.</p>'
    text+=table(['장비','복원 검사'],[[h,'; '.join(f'{k}: {v}' for k,v in r.items())] for h,r in restore.get('checks',{}).items()])
    lifecycle=sender/'lifecycle_checks/results.json'
    if lifecycle.exists():
        lc=read(lifecycle)
        text+=table(['실제 검사','결과'],[['SIGTERM 중단',lc['sigterm']['restored']],['SIGKILL 후 독립 만료 복원',lc['sigkill_expiry']['restored']],['실패 검증으로 시작 거부',lc['failed_validation_rejected']['rejected']],['거부 시 qdisc 보존',lc['failed_validation_rejected']['qdisc_unchanged']]])
    text+='<p>고정 프로파일의 실제 장비 계수는 <i>k<sub>TX</sub></i>=0.788606, 유효 서비스 비용 약5.990µs, idle busy 비율0.004269다. 설치된 송신 실행기는 유지하며 수신 측의 제한된 교정용 SSH 공개키만 남긴다. 수신 측에 추가 통계 에이전트나 신규ROSPacer 코드를 배포하지 않았다.</p>'
    text+='<details><summary>적용한 수정 운용 모델의 수식과 기호</summary><div><div class="math">T̂<sub>self</sub> = k<sub>TX</sub> ΔTX (R<sub>up,window</sub> / R<sub>dn,cal</sub>) / (1+ν)<br>z = (Δbusy − b<sub>idle</sub> Δactive − T̂<sub>self</sub>) / Δactive<br>θ<sub>effective</sub> = [(1+ν)(O<sub>effective</sub>/2 + s/R<sub>up,window</sub>) + O<sub>effective</sub>/2 + s/R<sub>dn,cal</sub>] / (s+14)<br>R<sub>budget</sub> = min(R<sub>ceiling</sub>, 0.9(1−z)/θ<sub>effective</sub>)<br>R<sub>applied,new</sub> = min(R<sub>ceiling</sub>, 0.7R<sub>applied,old</sub>+0.3R<sub>budget</sub>)</div><p><i>s</i>는 창의 평균 송신 station바이트/패킷에서Ethernet14바이트를 뺀IP크기, <i>ν</i>는재시도/패킷이다. <i>R<sub>up,window</sub></i>는같은관측창의바이트·재시도가중조화평균상향PHY, <i>R<sub>dn,cal</sub></i>은저장한수신PHY다. <i>z</i>는보정잔차이며실제다른트래픽점유율로확정하지않는다. <i>O<sub>effective</sub></i>는운용서비스비용이다. 속도는계산상B/s이며tc적용때bit/s로변환한다. 새고정상한은323.428Mb/s다.</p></div></details>'
    text+='<h2>6. W1 판정과 남은 범위</h2><p>송신 측에 교정·계수 계산·설정 생성·유한 제어 명령을 통합했고 실제 자료로 검증했다. 용량 게이트와 실제 DDS 결과는 위의 각 실행 판정을 따른다. 초기 수신 PHY를 이용하는 송신 측 운용 제어기이며, 수신 이동·다른 AP/드라이버로의 일반화, 정확한 물리적 점유율/전체HE airtime 식별은 미완료다. W2 정식 반복 성능 비교·E/F·전체Drain Control도 이 시운전과 구분한다.</p>'+linkhtml+'</main></body></html>'
    REPORT.write_text(text,encoding='utf-8');print(REPORT)
    for main_report in [ROOT.parent/'html 파일 모음/W1 보고서.html',REPORT.parent/'W1 보고서.html']:
        if not main_report.exists():continue
        contents=main_report.read_text(encoding='utf-8')
        if 'sender-local-integrated-261014' in contents:continue
        href=os.path.relpath(REPORT,main_report.parent).replace('\\','/')
        note='<section id="sender-local-integrated-261014"><h2>10/14 송신 측 단독 교정·제어 통합</h2><p><a href="'+html.escape(href)+'">새 통합 검증 보고서</a> — 교정·계수 계산·제어를 송신 측 명령으로 통합한 W1 검증. 실패 자료와 새 독립 검증·성능 시운전을 분리해 기록했다.</p></section>'
        contents=contents.replace('</body>',note+'</body>');main_report.write_text(contents,encoding='utf-8')


if __name__=='__main__':main()
