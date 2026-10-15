"""Add reader-facing conditions and explanations to the saved W1 report.

Rebuilds from the preserved pre-edit HTML; does not rewrite measurement logs.
"""
import html
import json
from pathlib import Path
import re
from deploy import ROOT

BASE=ROOT/'runs/w1_20261012_radio45'
REPORT=ROOT.parent/'html 파일 모음/W1 보고서.html'
NOTES=BASE/'report_revision_20261013'


def table(head, rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def toggle(name, body):
    return '<details class="reader-note"><summary>'+name+'</summary><div class="note-body">'+body+'</div></details>'


def load(path):return json.loads(path.read_text(encoding='utf-8'))


CONDITIONS='''<p><b>송신 4번 → 수신 5번</b>, Wi-Fi 1:1, 주 AP는 AX1500이다. 유선은 시계·SSH 관리용이며 DDS 전송은 실험용 규칙으로 차단했다. 의도적인 경쟁 트래픽은 넣지 않았다.</p>
<ul><li>메시지: <code>std_msgs/msg/UInt8MultiArray</code>, 메시지당 <b>1 MiB = 1,048,576 B</b>의 배열. 이미지·영상의 압축 성능을 시험한 것이 아니다.</li><li>내용: 고정 난수 시드로 만든 무작위 바이트. 처음 16 B에 순번과 발행 직전 시각을 기록해 수신 중복·전달·지연을 계산한다. ROS 직렬화 및 전송 헤더는 1 MiB 배열 외에 추가될 수 있다.</li><li>QoS: <b>RELIABLE·KEEP_ALL·VOLATILE</b>. RELIABLE은 신뢰성 복구를 요청하며 무조건적인 전달 보장은 아니다. KEEP_ALL은 자원 한도 안에서 이력을 유지하며 무한 메모리를 뜻하지 않는다. VOLATILE은 늦게 참가한 구독자에게 과거 샘플의 내구성 보관을 요구하지 않는다.</li><li>정상 시운전: <b>15초, 예정 117개</b>. 구독자의 관측 시간과 발견·잔여 전송을 기다리는 시간은 별도로 둔다.</li><li>발행률: 모든 DDS와 비교군에 기본 UDP 교정 처리량의 <b>20%</b>를 동일하게 요청한다. 7.794 Hz는 각 DDS의 최대 발행 성능을 찾아낸 값이 아니다.</li></ul>
<div class="formula">r = 0.2C<sub>0</sub> / (1 MiB)<br>= [0.2 × (326.893 × 10<sup>6</sup> bit/s ÷ 8)] / 1,048,576 B<br>≈ <b>7.7937 Hz</b>　(요청 주기 약 128.31 ms)</div>
<p>C<sub>0</sub>는 이 기본 교정의 UDP 수신 처리량이다. MiB는 2<sup>20</sup> B, Mb/s는 10<sup>6</sup> bit/s이다. 발행률 공식에 넣기 전에 bit/s를 B/s로 변환했다.</p>'''

DEFINITIONS=table(['조건','실제 의미','ROSPacer 개발에서의 위치'],[
 ('default','DDS 기본 동작 중심. 공통 QoS·Wi-Fi 시험 환경은 적용한다. 후속 Cyclone Default에는 wlp2s0 인터페이스 지정만 추가한다.','기본 동작 비교군. 모든 OS 설정을 공장 기본값으로 되돌린 조건은 아니다.'),
 ('vendor','벤더 권장 기능을 참고한 구성. Fast는 LARGE_DATA의 TCP 데이터 전송과 큰 버퍼, Cyclone은 큰 버퍼와 설치 버전의 기본 단편·WHC 동작을 사용한다.','벤더 기능 비교군. Cyclone은 원문 권장 설정의 일부만 적용한 시운전이다.'),
 ('static','메시지 크기·발행률·C₀·RTT 등을 설정 생성기에 넣어 계산한 DDS/XML·버퍼·보관함 설정. 외부 HTB 제한은 없다.','정적 최적화 부분의 초기 구현. F1~F4 sweep 최적값 파일을 읽어 적용한 것은 아니다.'),
 ('fixed','Static 설정 + HTB·fq의 고정 송신 상한. 정상 시운전은 packet 상한 0.9C₀ ≈294.204 Mb/s로 유지한다.','페이싱 제어기 장치의 고정 상한 동작을 분리해 확인하는 조건. 적응형 추정·갱신은 하지 않는다.'),
 ('adaptive_diagnostic','Static 기반 설정 + 임시 계수 해석으로 HTB 상한을 약200 ms마다 바꾸는 제한된 진단.','적응형 갱신 경로의 동작 확인. 정식 ROSPacer 성능·모델 검증 완료를 뜻하지 않는다.')])

VENDOR='''<p><b>proposal의 「실험 설계 → 비교군과 지표」를 기준으로 삼았지만, 이번 시운전은 그 전체 Vendor 구성을 그대로 적용한 것은 아니다.</b> Fast는 LARGE_DATA와 큰 소켓 버퍼를 적용했고 실제 Wi-Fi TCP 데이터 전송을 확인했다. Cyclone은 [ROS2Tuning]의 큰 수신 버퍼 방향을 참고했다.</p>
<p>이번 Cyclone Vendor의 요청값은 송신 버퍼 1 MiB, 수신 버퍼 <b>10 MiB =10,485,760 B</b>다. 원문/ROS 문서의 10 MB 예시와 단위가 정확히 같지는 않다. 생성 XML에서 단편 크기와 WHC 관련 강제값을 제거해 설치 버전의 기본 동작을 사용했고, Wi-Fi 인터페이스·발견 설정은 남겼다.</p>'''+table(['항목','proposal / ROS 튜닝 예시','이번 Cyclone Vendor의 적용 범위'],[
 ('수신 커널 상한 rmem_max','ROS Jazzy 예시는2,147,483,647 B','run 준비에서 요청 수신 버퍼를 허용할 만큼 올림. 문서의 최대값을 그대로 적용한 구성 아님'),
 ('SocketReceiveBufferSize','ROS 문서 예시 최소10 MB','최소/최대10,485,760 B(10 MiB) 요청'),
 ('ipfrag_time','3초 예시','Vendor run에서 명시적으로 주입·검증하지 않음'),
 ('ipfrag_high_thresh','134,217,728 B 예시','Vendor run에서 명시적으로 주입·검증하지 않음'),
 ('FragmentSize / WHC','이번 Vendor는 기본 동작 사용','설치 버전의 기본 단편 및 Writer History Cache(송신 이력 보관함) 동작')])+'''
<p>따라서 이 행을 <b>ROS2Tuning 전체를 적용한 최종 Vendor 성능</b>으로 인용하지 않는다. Fast의 Vendor-FC(flow controller)도 이번 네 조건 시운전에는 포함되지 않았다.</p>
<p>근거: <a href="../연구 프로포졸 자료/WirelessXML_Proposal%20(2).html">proposal HTML</a>, <a href="https://docs.ros.org/en/jazzy/How-To-Guides/DDS-tuning.html">ROS Jazzy DDS tuning</a>, <a href="https://raw.githubusercontent.com/ros2/ros2_documentation/jazzy/source/How-To-Guides/DDS-tuning.rst">같은 공식 문서의 Jazzy 소스</a>. 실제 적용 범위는 <code>tools/w1_ros45.py</code>의 profile 생성·sysctl 주입과 저장된 XML을 대조했다.</p>'''

RUNTIME='''<p><b>고정 런타임</b>은 실행할 DDS/RMW 바이너리와 관련 라이브러리의 버전·내용을 고정했다는 뜻이다. <b>fixed</b>라는 송신 상한 조건과는 다른 용어다.</p>
<p>초기 연구용 설치는 기존 ros2_ws 설치를 그대로 사용했다. 장비마다 연구 수정본·빌드가 섞여 있어 공식 기본 성능 비교의 기준으로 쓰기 어렵다. 후속 고정 런타임은 같은 DDS/RMW 라이브러리 묶음을 별도 폴더에 배치하고, 실제 프로세스에 로드된 파일의 SHA-256(내용 식별 해시)을 각 run에서 대조했다.</p>
<p><b>closure</b>는 DDS 본체뿐 아니라 RMW·직렬화 라이브러리 등 함께 필요한 관련 공유 라이브러리 묶음이다. Fast DDS 2.6.11 묶음은10번의 공식 ROS 패키지에서 가져왔고, CycloneDDS 0.10.5 묶음은4번의 수정 없는 소스 빌드에서 가져왔다. 두 묶음 모두 실제 송수신 장비인4·5번에 별도로 배치했다. 기존 연구 설치를 덮어쓰지 않았다. RMW는 ROS 2와 DDS 구현 사이의 연결 계층이다.</p>
<p>버전 혼입을 줄인 <b>고정 런타임 시운전을 기준으로 보는 것이 적절</b>하다. 다만 15초의 기능 시운전이고 반복 성능 평가가 아니므로 이 표만으로 우위를 확정하지 않는다.</p>'''

HTB='''<p><b>HTB(Hierarchical Token Bucket)</b>는 Linux 송신 대역폭 제한 장치다. <b>class</b>는 특정 패킷들을 모아 제한하는 구획이며, 이번 class에는 분류된 DDS RTPS 패킷(사용자 데이터 외 제어·재전송도 포함 가능)이 들어간다. RTPS는 DDS의 네트워크 통신 프로토콜이다.</p>
<div class="formula">HTB class Mb/s = 8 × (class 송신 바이트 증가량) / (관측 시간 × 10<sup>6</sup>)</div>
<p>표 값은 <b>실제 class 전송률</b>이며 설정 상한·Wi-Fi PHY 전송률·수신 ROS payload 처리량과 다르다. DDS 시험에서는 발행 구간의 시작3초 뒤부터 종료1초 전까지 제어기 class 계수의 차이를 사용한다. 낮은 부하에서는 실제 전송률이 설정 상한보다 작다.</p>
<p>Default·Vendor·Static은 HTB를 적용하지 않아 <b>해당 없음 — HTB 미적용</b>으로 표시한다. 실제 HTB 실행에서 유효 계수 표본이 부족한 경우만 미확정이다. 지연·지터를 만들 수 없는 발견 실패는 발행 시작 안 함으로 구분한다.</p>
<p><b>지연 p50/p95/p99</b>는 발행 직전 시각부터 수신 콜백까지의 지연 분포 백분위값이다. <b>도착 간격 지터 p99</b>는 |연속 고유 메시지의 도착 간격−요청 발행 주기|의99번째 백분위값이며, 지연의 표준편차가 아니다. 큐 대기를 추가해 지연이 늘어도 순간 몰림이 줄면 지터가 낮아질 수 있다. 이 인과는 별도 검증해야 한다.</p>'''

FQ='''<p><b>fq(Fair Queue)</b>는 흐름별 큐를 나누어 패킷을 내보내는 Linux 큐 관리 장치다. <b>flow_limit</b>은 fq가 구분한 <b>각 흐름에 대기할 수 있는 최대 패킷 수</b>이며, 바이트 수·ROS 메시지 수·Hz가 아니다. 넘는 패킷은 버려질 수 있다. 흐름이 항상 ROS 토픽이나 DDS 참가자 하나와 같은 것은 아니며 소켓/패킷 식별과 구현에 따라 나뉜다.</p>
<p>별도의 <b>limit</b>은 fq 전체의 패킷 수 한도다. 이번 역압 비교는 <b>flow_limit=100 대1,490</b>, 전체 limit는 둘 다5,960으로 동일했다. 1 MiB 메시지 하나가 약700개 이상의 UDP/RTPS 단편으로 나뉠 수 있어, 작은 흐름별 한도가 순간 패킷 묶음을 버리는 원인이 될 수 있다.</p>
<p>1,490은 현재 생성기의 메시지 묶음·여유를 반영한 설계값이다. 최적값을 sweep으로 확정한 것은 아니다. 큰 큐가 항상 좋다는 뜻도 아니며, 다른 부하에서는 대기를 늘릴 수 있다. 이번 fq는 <code>nopacing</code>으로 사용했고, 송신율 상한은 HTB가 담당했다.</p>
<p>근거: <a href="https://man7.org/linux/man-pages/man8/tc-fq.8.html">fq 공식 매뉴얼(flow_limit 기본100)</a>.</p>'''

RADIO='''<p>다음은 <a href="https://docs.kernel.org/6.8/driver-api/80211/cfg80211.html#c.survey_info">Linux 6.8 survey_info API</a>의 정의와 이번 측정 방법이다. 표에는 현재 사용 중인149번 채널의 <code>iw survey dump</code> 누적값을 구간 전후로 차감하고, ms를1,000으로 나눈 <b>초(s)</b>를 기록한다. 서로 다른 채널을 합산하지 않는다.</p>'''+table(['값','Linux API의 정의','이번 보고서에서의 해석'],[
 ('active s / time','해당 채널에서 무선 장치가 켜져 있던 시간(ms)','관측 구간의 누적값 차이. 이번 구간은 실제 관측 길이와 대체로 비슷함'),
 ('busy s / time_busy','주(primary) 채널이 바쁘다고 감지된 시간','전체80 MHz 채널의 모든 프레임 airtime 합이나 다른 트래픽만의 시간이라고 자동 해석하지 않음'),
 ('tx s / time_tx','무선 장치가 데이터를 송신한 시간','해당 송신 단말 자체의 드라이버 보고 시간. AP의 중계 송신 시간 자체는 아님'),
 ('stationTX bytes','연결된 AP에 대한 station tx bytes의 증가량','드라이버의 송신 바이트 지표. ROS 유효 payload나 독립 캡처 wire bytes와 같은 단위의 관측은 아님')])+'''
<p><b>정의와 실제 구현은 구분한다.</b> 이번 mt792x 드라이버는 busy를 <code>MT_MIB_SDR9</code>, TX를 <code>MT_MIB_SDR36</code>의 별도 하드웨어 계수에서 읽는다. 코드에서 출처는 확인했지만, 이 장비/펌웨어에서 자기TX의 포함 여부·집계 기준이 정확히 어떻게 구현됐는지는 독립 검증하지 못했다. API 이름만으로 <code>TX가 busy의 부분집합</code>이라고 추가 가정할 수 없다.</p>
<p>따라서 “정확히 주채널 감지 busy를 요청하는 API”라는 정의는 제시할 수 있지만, “이 장비의 raw busy가 모든 자기TX를 포함하는 물리적 총 busy”라는 정의를 확정해서 제시할 수는 없다. 그 미확정 사항 자체가 W1 결과다.</p>'''

REFERENCE='''<p><b>idle</b>은 노트북·AP·Wi-Fi 연결은 그대로 두고 <b>이 시험이 만드는 대용량 UDP 송신만 하지 않는 약6초 기준 구간</b>이다. AP를 끄거나 모든 전파를 없앤 상태가 아니다. 비콘·연결 유지·관리 통신과 주변 Wi-Fi는 있을 수 있으므로 계수 증분이 반드시0일 필요도 없다.</p>
<p><b>ap_only</b>는4번에서 공유기 자체의 UDP 목적지로 약100 Mb/s를8초 송신해5번으로의 데이터 중계를 제거한 참조다. 공유기가 iperf 수신 서버로 처리량을 보고한 시험은 아니다. <b>relay</b>는4번→AP→5번으로 약100 Mb/s iperf UDP를8초 전송해 AP 하향 중계가 추가되는 참조다.</p>
<p>세 구간은 자기 송신만 있을 때와 중계가 추가될 때 계수가 어떻게 달라지는지 보는 <b>정성적 분리 시험</b>이다. 관리 트래픽·재시도·PHY/묶음 전송 상태도 달라질 수 있어 busy 증가분 전부를 정확한 AP 중계 airtime으로 단정하지 않는다.</p>'''

B2='''<p><b>B2는 주 링크와 다른 AP의 동일 채널 간섭</b>이다. 주 데이터는 4번 → AX1500 → 5번, 경쟁 데이터는 12번 → SR2 → 10번이다. AX1500과 SR2는 <b>둘 다 149번·80 MHz</b>여서 같은 무선 채널을 경쟁한다. 공유기는 서로 다르다.</p>
<p>경쟁 UDP는 무제한 목표율(<code>iperf3 -b 0</code>, 실제 전송률은 장비가 허용하는 만큼)로 <b>2초 켜짐·2초 꺼짐</b>을 반복한다. “포화”는 계속 보낼 데이터가 있다는 뜻이지 전파 점유가 정확히 100%라는 뜻은 아니다.</p>
<p><b>clean_otherAP_idle</b>은 다른 AP와 장비 연결은 유지하되 <b>그 시험의 경쟁 UDP를 켜지 않은 기준 구간</b>이다. 비콘·관리·주변 통신까지 0인 전파 무음 조건은 아니다. 처리량은 같은 B2 묶음의 기준과 비교한다.</p>'''

C2='''<p><b>C2는 주 링크와 경쟁 링크가 같은 AP를 쓰는 혼잡</b>이다. 이번에는 4번 → SR2 → 5번과 12번 → SR2 → 10번이 <b>모두 SR2를 사용</b>한다. 경쟁 UDP의 목표율은 <b>SR2의 quiet 세 번 중앙값 329.696 Mb/s의 0.9배, 약296.726 Mb/s</b>였다. 이 값은 AX1500 기본 교정 326.893 Mb/s의 0.9배와 구분한다. 목표 전송률이 실제 달성 처리량이나 채널 점유율을 뜻하지는 않으며, B2처럼 무제한 목표율을 켜고 끄는 시험은 아니다.</p>
<p><b>quiet1·quiet2·quiet3</b>는 같은 배치에서 <b>경쟁 UDP를 실행하지 않은 기준 측정 세 번</b>이다. 의도적인 주 데이터 트래픽은 한 AP의 4→5 링크뿐이라는 이해는 맞다. 그러나 경쟁 노트북이 연결돼 있을 수 있고 다른 AP도 물리적으로 꺼졌다는 뜻은 아니므로, “주변에 AP가 정확히 한 대뿐”인 시험과는 다르다.</p>
<p>quiet와 C2를 비교해야 경쟁 부하의 영향을 볼 수 있다. AX1500에서 교정한 326.893 Mb/s와 SR2의 quiet값을 무조건 같은 기준으로 묶지 않는다. quiet3의 수신 버퍼 오류 59건도 보고서에 보존했다.</p>'''


def add_section_notes(source, additions):
    pattern=r'(<h[23] id="section-(\d+)"[^>]*>.*?</h[23]>)(.*?)(?=<h[23]\b|</main>)'
    def change(m):
        number=int(m[2]);return m[1]+m[3]+additions.get(number,'')
    return re.sub(pattern,change,source,flags=re.S)


def main():
    NOTES.mkdir(exist_ok=True)
    baseline=NOTES/'W1_before_reader_notes.html'
    if not baseline.exists():baseline.write_bytes(REPORT.read_bytes())
    source=baseline.read_text(encoding='utf-8');derived=load(BASE/'derived_report.json')
    # Use one coherent comparator set. Do not splice stock values into the
    # differently configured research-runtime table. Archived evidence remains.
    source=re.sub(r'<h2 id="section-7">.*?(?=<h2 id="section-8">)','',source,flags=re.S)
    source=re.sub(r'<a href="#section-7">.*?</a>','',source,flags=re.S)
    # Mark genuinely inapplicable HTB values, preserving all other measurements.
    def htb_table(m):
        block=m[0];heads=re.findall(r'<th>(.*?)</th>',block,re.S)
        if 'HTB class Mb/s' not in heads:return block
        index=heads.index('HTB class Mb/s')
        def row_change(r):
            row=r[0];cells=list(re.finditer(r'<td>(.*?)</td>',row,re.S))
            if len(cells)<=index:return row
            label=html.unescape(re.sub('<[^>]+>',' ',cells[0][1]))
            if re.search(r'_(?:default|vendor|static)(?:\s|$)',label) or label=='baseline':
                cell=cells[index];return row[:cell.start()]+'<td>해당 없음 — HTB 미적용</td>'+row[cell.end():]
            return row
        return re.sub(r'<tr[^>]*>.*?</tr>',row_change,block,flags=re.S)
    source=re.sub(r'<table>.*?</table>',htb_table,source,flags=re.S)
    source=source.replace('<h2 id="section-8">고정 DDS 런타임의 비교군 시운전</h2>','<h2 id="section-8">고정 DDS 런타임의 비교군 시운전 <span class="reference-badge">이것을 기준으로 보는 것이 적절</span></h2>')
    comparison=[]
    for vendor in ['fastdds','cyclonedds']:
        for campaign,label,duration in [('ros45_stock','fixed',15),('ros45_stock_adaptive_diagnostic','adaptive_diagnostic',20)]:
            e=derived['campaigns'][campaign][vendor+'_'+label];met=e['metrics'];comparison.append([vendor,label,duration,f"{met['unique_received']}/{met['requested']}",f"{met['end_to_end_latency_ms']['p99']:.3f}",f"{met['arrival_jitter_ms']['p99']:.3f}"])
    adaptive='''<p><b>적응형(adaptive)</b>은 실행 중 측정에 따라 상한을 바꾼다는 뜻이고, <b>diagnostic</b>은 진단 시험이라는 뜻이다. Static의 정적 설정 위에 갱신 경로를 시험했으며, 정식 운영 적응형 모드의 모델 검증 게이트는 유지했다.</p>
<ul><li>raw busy가 자기 TX를 제외한다고 임시 가정해 계산 시 TX 포함 관계를 보정했다.</li><li>수신 5번의 PHY 전송률을 실행 준비에서 읽은 snapshot(그 시점의 값)으로 사용했다. 실행 중 수신 단말의 실시간 피드백으로 갱신한 값은 아니다.</li><li>O는 UDP 교정에 맞춘 조건부 비용이며 독립 식별한 물리적 고정 비용으로 승인하지 않았다.</li><li>HTB packet 상한은 무조건 0.9C₀ ≈294.204 Mb/s 이하로 제한했다.</li><li>약 200 ms마다 추정하고, 이전 상한 70%+새 추정 30%로 완화해 적용했다.</li></ul>
<p>ROS 송신 조건은 4→5, UInt8MultiArray 1 MiB 무작위 데이터·순번/시각, RELIABLE·KEEP_ALL·VOLATILE, 요청 약 7.7937 Hz다. <b>메시지 발행 구간은 20초, 예정 156개</b>이고 제어기 전체 실행은 약 46초다. 각 230회 갱신에는 발행 전후 구간도 들어 있어 20초 동안 230회라는 뜻이 아니다. 두 DDS 모두 156/156 수신, 갱신 230회·보류 0을 기록했다.</p>
<p><b>이 결과로 “적응형이 Fixed보다 훨씬 좋다”고 결론낼 수 없다.</b> 아래는 다른 run의 수치를 나란히 놓은 참고값이다. Fast의 p99 지연은 거의 같고 Cyclone의 p99 지연·지터는 오히려 진단에서 더 높았다.</p>'''+table(['DDS','조건','발행 구간s','수신/예정','지연p99 ms','지터p99 ms'],comparison)+'''
<p>15초 Fixed와 20초 진단의 다른 run이므로 표본 수·시간·무선 상태가 같지 않다. 의도적인 링크 몫 변화도 주지 않았다. 상한 갱신 코드의 실행 가능성을 확인한 것이며, 성능 우위는 동일 조건·시간·반복 및 간섭/혼잡/몫 변화 시험으로 따로 판정해야 한다.</p>
<p class="reader-callout"><b>단절·역압 표와의 직접 비교는 특히 피해야 한다.</b> 단절 Fixed는5초 UDP 차단을 넣었지만 이 적응형 진단은차단하지 않았다. 역압 시험은발행0.8C₀·상한0.5C₀이고, 이진단은발행0.2C₀·상한최대0.9C₀다. 진단의지연이이들보다낮아도제어방식의효과와부하·손상조건의차이를분리할수없다.</p>
<p><b>PHY 전송률</b>은 무선 변조 방식으로 보고되는 링크 전송률이며 응용 수신 처리량과 다르다. <b>O</b>는 모델의 단위당 고정 비용, <b>β</b>는 다른 트래픽의 점유비 추정값이다. <b>C₀</b>는 기본 UDP 교정의 수신 처리량 326.893 Mb/s다.</p>'''+DEFINITIONS+RUNTIME+HTB
    bp='''<p><b>bp = backpressure(역압)</b>다. 발행 요청보다 송신 출구를 느리게 만들어 대기 압력이 DDS·응용까지 전달되는지 보는 시험이다. 송신 4→수신 5, UInt8MultiArray 1 MiB 무작위 바이트·순번/시각, RELIABLE·KEEP_ALL·VOLATILE, 30초다.</p>
<div class="formula">발행 요청 0.8C₀ ≈261.514 Mb/s ≈31.1749 Hz<br>HTB packet 상한 0.5C₀ ≈163.446 Mb/s<br>요청량이 상한보다 큼 → 큐·소켓·DDS 대기/오류 → 실제 발행률 감소</div>
<p>각 run 예정 936개다. <b>bp_default100은 DDS Default가 아니다.</b> 두 조건 모두 같은 Static XML·버퍼·보관함과 같은 HTB 상한을 사용하고 flow_limit만 100과 1,490으로 달리했다. <b>bp_design은 그 한도의 설계값</b>이며 모든 설정의 전역 최적값이라는 뜻은 아니다.</p>'''+FQ+'''
<p><b>관측:</b> 설계 한도에서 두 DDS의 fq drop과 UdpSndbufErrors가 0으로 줄고 지연·지터·발행률이 개선됐다. 이 조건에서는 설계 한도가 유리하다. 다만 큰 큐가 항상 좋거나 모든 오류 경로에서 무손실 대기를 보장하는 결론은 아니다.</p>
<p><b>수신/예정</b>의 예정은 요청 계획 936개다. Fast 설계 조건은 성공 발행 414개·수신 414개, Cyclone 설계 조건은 성공 발행 536개·수신 536개였다. 예정과의 차이에는 publish 대기 때문에 발행하지 못한 몫이 있다. <b>publish실패</b>는 호출 예외 수이며, 0이라고 목표 발행률을 유지했다는 뜻은 아니다.</p>
<p><b>ss</b>는 소켓 상태 조회 도구, <b>skmem</b>은 그 출력의 소켓 메모리 계수다. <b>socket t</b>는 송신 메모리 할당, <b>socket w</b>는 다른 송신 큐 메모리 항목으로서 서로 구분한다. 단순히 w=0만 보고 소켓에 압력이 없다고 판단하지 않는다. <b>UdpSndbufErrors</b>는 커널 UDP 송신 버퍼 오류 계수, <b>fq drop</b>은 fq에서 버린 패킷 계수다. 단위는 DDS 메시지 개수가 아니고, 두 계수가 같아도 그 수만큼의 ROS 메시지 유실이라는 뜻은 아니다. ss와 오류·qdisc·publish 시간을 같은 run에서 약 0.1초마다 확인했다. 여기서 C₀는 기본 교정 326.893 Mb/s다.</p>'''+DEFINITIONS+RUNTIME
    outage='''<p>이 시험은 <b>전송을 잠시 막았다가 다시 열었을 때 수신과 지연이 어떻게 회복되는지</b> 확인한다. 비교한 행은 Fast Fixed와 Cyclone Fixed이며, Default 대 Fixed나 sweep 최적 설정의 비교가 아니다.</p>
<p>송신 4→수신 5, UInt8MultiArray 1 MiB 무작위 데이터·순번/시각, RELIABLE·KEEP_ALL·VOLATILE, 요청 약 7.7937 Hz, 발행 20초·예정 156개다. <b>Fixed=Static+고정 HTB·fq</b>이고 정상 시운전과 같은 0.9C₀ packet 상한을 사용한다. 5번에서 상대 4번의 Wi-Fi UDP를 입출력 양방향 약 5초 차단한 뒤 해제했다. AP 전원이나 Wi-Fi 연결 자체를 끊은 시험은 아니다. SSH·유선 시계는 유지한다.</p>
<ul><li><b>단절 실제s:</b> 시험 규칙이 적용된 실제 차단 시간. 명령 지연으로 5초와 조금 다르다.</li><li><b>첫 도착s:</b> 차단 해제부터 첫 메시지를 받은 시간. 지연이 정상화됐다는 뜻은 아니다.</li><li><b>proposal복구s:</b> 복구 뒤 전체 1초 도착 창의 p95 지연이 단절 전 p95의 2배 이하가 되는 첫 시점. 최소 3표본을 요구한다.</li><li><b>단절전p95:</b> 이 run에서 단절 전 기준으로 계산한 지연값. p95는 95번째 백분위다.</li></ul>
<p>Cyclone의 첫 도착 0.058초와 지연 정상화 3.993초는 서로 다른 지표다. Fast의 미확정은 <b>관측 창에서 복구 기준을 충족하지 못함(관측 시간 제한)</b>을 뜻하며, 영구 복구 불가능으로 단정하지 않는다. 대기 데이터 배출과 재전송 상태를 같이 봐야 한다. 여기서 C₀는 기본 교정 326.893 Mb/s다.</p>'''+DEFINITIONS+RUNTIME+HTB
    selfload='''<p><b>자기 부하</b>는 경쟁 UDP를 추가하지 않고 4→AP→5의 우리 송신 목표만 0.2·0.4·0.6·0.8C₀로 올리는 시험이다. 여기서는 ROS가 아닌 UDP 1,400 B iperf를 각 15초 실행하고 처음/끝 여유 구간을 제외해 계수 증분을 대조했다.</p>
<p><b>β̂<sub>oth</sub></b>는 다른 트래픽의 추정 채널 점유비다. <b>T<sub>relay</sub></b>는 AP가 우리 데이터를 5번으로 중계하는 추정 시간이다. 자기 송신·자기 중계를 빼고 β̂가 0 근처에 머무는지 확인해야 우리 부하를 다른 부하로 오인하지 않는다. 주변/관리 통신은 있을 수 있으므로 엄밀한 전파 무음 시험은 아니다.</p>
<div class="formula">기존식: β̂<sub>oth</sub> = (Δbusy − Δtx − T<sub>relay</sub>) / Δactive</div>
<p><b>gate(게이트)</b>는 이 입력 전제가 승인됐는지 확인하는 시작 조건이다. 현재 일반 adaptive는 계수의 물리적 해석이 통과하지 않아 시작을 거부하고 qdisc를 변경하지 않는다. 별도 diagnostic의 성공으로 게이트를 승인하지 않는다.</p>'''+RADIO+'''
<p>이번 네 부하와 공유기 직접/중계 참조에서 <b>Δbusy&lt;Δtx</b>가 반복 관측됐다. “busy가 모든 자기 TX를 포함한 총 바쁨 시간”이라면 모순이 맞다. 관측값의 포함 관계가 그 가정을 만족하지 않아 기존 식을 그대로 쓸 수 없다는 판정이다. 모든 장비/모든 부하에서 항상 이 관계라는 일반화는 아니다.</p>
<p>자기 TX를 제외한다고 가정하면 잔차는 줄지만 자기 부하에 따라 달라진다. 음수를 0으로 잘라 정상처럼 만들지 않았고, missing/미갱신 계수를 0으로 넣지 않았다. O≈2.595µs는 UDP 포화 교정에 맞춘 조건부 비용이며, 프리앰블·ACK·aggregation을 독립 식별한 고정값이 아니다.</p>'''
    additions={
      4:toggle('링크 교정 설명 · C₀·UDP·TCP·RTT·오류의 의미','<p>4→AP→5 링크에서UDP1400 B·30초를3회, TCP30초를1회, ping200회를실행하며station/survey통계를같이수집했다. UDP수신interval의bytes/time으로처리량을계산했다. UDP는전송부하, TCP는연결·혼잡제어가있는전송, RTT는왕복응답시간이다. UDP수신중앙값이C₀이며DDS의최대goodput·무손실보장과같지않다. udp3의RcvbufErrors52건도유지했다. 위조건의C₀는시간/AP/경쟁상태가바뀌면다를수있다.</p>'+RADIO),
      5:toggle('시계·지연·지터 설명 · 비교 가능한 지표의 조건','<p>4번이유선으로5번chrony시계를참조한다. chrony는단말시계의상대차이를교정하는도구다. 5번은local기준이므로절대UTC정확도를검증한시험은아니다. run별시계기록의연속성과상대오차한계를검사하고1ms보다큰run의종단지연은배제한다. payload발행시각부터수신콜백까지의지연에는직렬화·DDS·큐대기가포함된다.</p>'+HTB),
      6:toggle('HTB 200 Mb/s 검사 설명 · baseline·burst·class·payload','<p>4→5실제Wi-Fi에서UDP시험포트55311을사용했다. baseline은HTB미적용, burst1500과burst65536은200 Mb/s상한과각각1,500/65,536 B의burst를설정해각10초실행했다. burst는짧은순간에허용하는전송묶음크기이며ROS메시지크기가아니다. class약200 Mb/s와수신UDPpayload약193 Mb/s는서로다른계층의측정값이다. 현재조건의상한동작검사이며모든부하에서HTB부착비용이없다는시험은아니다.</p>'+HTB+FQ),
      7:toggle('초기 시운전 설명 · Cyclone 발견 실패와 후속 결과의 구분',CONDITIONS+RUNTIME+'<p>초기CycloneDefault는CYCLONEDDS_URI없이자동인터페이스선택을사용했다. pub.json의오류는insufficient matched subscribers before deadline이며attempted=0이다. Wi-FiRTPS패킷이없고유선차단계수는증가해유선경로선택이발견을막았다는해석을뒷받침한다. 후속에서는수정없는고정런타임과wlp2s0지정을함께적용해117/117받았다. 두변수를동시에바꾼재시험이므로그하나만으로원인을완전히분리하지않는다.</p>'+DEFINITIONS+HTB),
      8:toggle('고정 런타임 시운전 설명 · 공통 발행 조건·조건명·적용 범위',CONDITIONS+RUNTIME+DEFINITIONS)+toggle('Vendor의 proposal·ROS2Tuning 대응 · 적용한 것과 미적용 항목',VENDOR)+toggle('Static과 Fixed의 개발 위치 · sweep 결과 및 지터 해석','<p><b>Static은ROSPacer정적최적화의초기구현</b>이다. 현재생성기가입력으로계산한값을적용하며sweep최적값모음을가져온조건은아니다. <b>Fixed는정적최적화그자체가아니라Static에페이싱장치를추가한고정상한실험</b>이다. 적응형제어기개발과정에서추정기를제외하고장치동작을확인하는역할이다.</p><p>고정런타임결과에서CycloneFixed는지터22.109ms로Default47.635ms보다낮았지만Fast에서는Static16.162ms가Fixed19.215ms보다낮았다. Fixed가항상최악이거나최선은아니다. 상한이순간몰림을줄이는대신대기를추가할가능성이있지만이인과와성능우위는반복시험이필요하다.</p>'+HTB),
      9:toggle('역압 실험 설명 · bp·default100·design·flow_limit·수신/예정',bp),
      10:toggle('단절·복구 실험 설명 · 무엇을 차단하고 무엇을 비교했는가',outage),
      11:toggle('적응형 진단 설명 · 임시 가정·230회 갱신·Fixed와의 비교',adaptive),
      12:toggle('자기 부하·게이트 설명 · busy와tx의 정의 및 미확정 사항',selfload),
      13:toggle('참조 시험 설명 · idle·ap_only·relay·계수 단위',REFERENCE+RADIO),
      14:toggle('10번 독립 관측 설명 · 관측 장비·MAC 방향·HE·aggregation',REFERENCE+RADIO+'<p>10번은4·5번이송수신하는채널149의프레임을듣는별도관측자다. 4·5번에모니터를추가하지않아송신단말설정의영향을줄였다. HE는802.11ax의무선형식이다. A-MSDU는여러데이터단위를한프레임에묶는방식, A-MPDU는여러MAC프레임을한전송묶음에묶는방식, PPDU는물리계층전송묶음이다.</p><p>MAC화살표는해당무선홉의송신자→수신자이며응용데이터의최초발행자→최종구독자전체경로와는다르다. AP→5는4에서만든데이터를AP가하향중계하는홉이다. 관측wire bytes는radiotap계측헤더를뺀캡처프레임원래길이의합이며재전송도포함될수있다. 커널drop0은무선프레임전체를빠짐없이들었다는보장이아니다. 불완전캡처·airtime값/A-MPDUreference부재때문에전체공기시간합을승인하지않았다.</p>'),
      15:toggle('B2·C2 배치 요약 · 다른 AP의 간섭과 같은 AP의 혼잡',table(['조건','주 전송','경쟁 전송','의도적 경쟁 부하'],[('B2','4→AX1500→5','12→SR2→10','같은149번채널, 다른AP; 포화2초ON/2초OFF'),('C2','4→SR2→5','12→같은SR2→10','같은AP; 목표약0.9C₀ 경쟁UDP'),('C2 quiet','4→SR2→5','경쟁UDP 미실행','의도적주트래픽은한AP뿐; 주변AP전원을끈조건아님')])+'<p>B2와C2를둘다“같은포화시험”으로보면안된다. 공유기배치뿐아니라경쟁목표율과시간패턴도다르다. beta는다른트래픽의추정점유비, 조건부O는해당교정에맞춘유효비용이다. 가정변경의예측오차가20%안이어도자기부하게이트가미통과이므로정식모델승인이아니다.</p>'),
      16:toggle('B2 설명 · clean_otherAP_idle·포화 켜짐과 꺼짐',B2),
      17:toggle('C2 설명 · 같은 SR2 공유기·quiet·조건부 예측',C2+'<p>이표의미검증예측은raw busy해석을바꾸고수신PHY를입력한후계산한진단이다. B2/C2수신처리량측정은완료했지만모델입력전제를승인한것은아니다. PHY는무선변조전송률이고응용goodput과같지않다.</p>'),
      18:toggle('확인 필요 판정 설명 · 수행·미통과·범위 변경','<p>“수행”은해당시험/설정적용을실행했다는뜻이고“미통과”는확인하려던전제가승인되지않았다는뜻이다. proposal은Ubuntu24.04/Jazzy·세미들웨어를기획했으나사용자방침에따라Ubuntu22.04/Humble·Fast/Cyclone을우선했다. RPBench전체연동이나원문Vendor전체구성·Vendor-FC까지완료했다고해석하지않는다. 실행마다커밋과해시는남겼지만전체발전과정의모든run이한커밋인것은아니다. Zenoh운영점선정은후속이관이다.</p>'),
      19:toggle('종료·복원 설명 · 완료한 복원과 아직 남은 검증','<p><b>종료와복원은완료했다.</b> 실험프로세스·임시모니터·방화벽규칙을종료하고절전·CPU·소켓커널상한·qdisc·임시유선시계주소/소스를복원했다. qdisc는송신큐관리장치이며원래noqueue상태로돌렸다. 저장된NetworkManager/chrony설정파일과원래연구DDS설치는유지했다. survey채널귀속수정드라이버와MOK등록은의도적으로유지했다.</p><p>남은일은복원명령을실행하지못한것이아니라, busy/TX의포함관계와aggregation을반영한중계/O교정및별도자기부하·B2/C2자료로적응형모델을재검증하는일이다. MOK(서명모듈신뢰키)등록이나같은랜연결을반복하는것만으로이물리적계수해석이해결되지는않는다.</p>')}
    # Annotate MAC directions in the visible table, retaining the exact addresses.
    names={'b0:38:6c:7d:f5:74':'AX1500 공유기','3c:0a:f3:02:d9:3b':'4번 노트북','3c:0a:f3:02:e4:c7':'5번 노트북'}
    def direction(m):return '<td>'+m[1]+' ('+names[m[1]]+') → '+m[2]+' ('+names[m[2]]+')</td>'
    source=re.sub(r'<td>([0-9a-f:]{17}) -&gt; ([0-9a-f:]{17})</td>',direction,source)
    # Move lengthy diagnostic/cleanup raw JSON behind an adjacent toggle.
    for section,title in [(12,'적응형 시작 거부 원자료(JSON) 보기'),(19,'종료·복원 원자료(JSON) 보기')]:
        pattern=rf'(<h2 id="section-{section}".*?</h2>)(.*?)(?=<h[23]\b|</main>)'
        source=re.sub(pattern,lambda m:m[1]+re.sub(r'<pre>.*?</pre>',lambda p:toggle(title,p[0]),m[2],flags=re.S),source,flags=re.S)
    background_rows=[]
    for i in [1,2,3]:
        bg=load(BASE/f'c2/C2_{i}_background_server.json')
        streams=[r for interval in bg['intervals'] for r in interval['streams']]
        rate=8*sum(r['bytes'] for r in streams)/sum(r['seconds'] for r in streams)/1e6
        background_rows.append([f'C2_{i}',f'{rate:.3f}'])
    additions[17]+=table(['경쟁 12→10 전송','38초 전체 수신 평균 Mb/s'],background_rows)+'<p class="revision">위 경쟁 처리량은 별도 iperf 수신 로그의 전체 구간 평균이다. 주 4→5 측정의 30초 창과 정확히 같은 창은 아니다. 요청 약296.726 Mb/s와 실제 수신량은 다르며, 목표율을 채널의 실제100% 포화로 해석하지 않는다.</p>'
    source=add_section_notes(source,additions)
    common='<section class="common-conditions" id="common-conditions"><h2>정상 시운전의 공통 실험 조건</h2>'+CONDITIONS+toggle('조건 이름과 개발 위치 · Default·Vendor·Static·Fixed',DEFINITIONS)+toggle('Vendor의 출처와 실제 적용 범위',VENDOR)+'</section>'
    source=source.replace('<h2 id="section-8">',common+'<h2 id="section-8">',1)
    source=source.replace('<header>','<header>',1).replace('</header>','<p class="revision">측정:2026-10-12 · 설명 보완:2026-10-13 · 원자료 수치와 초기 실패는 보존</p></header>',1)
    source=source.replace('<nav aria-label="보고서 목차"><b>목차</b><div>','<nav aria-label="보고서 목차"><b>목차</b><div><a href="#common-conditions">공통 실험 조건</a>',1)
    css='''details.reader-note{margin:14px 0;border:1px solid #d8e2ef;border-radius:8px;background:#f8fafc;font-size:14px}details.reader-note>summary{padding:13px 16px;cursor:pointer;color:#24507d;font-weight:600}details.reader-note[open]>summary{border-bottom:1px solid #d8e2ef}.note-body{padding:2px 20px 16px;line-height:1.85}.note-body p{margin:14px 0}.note-body table{font-size:13px}.reference-badge{display:inline-block;font-size:14px;margin-left:8px;padding:4px 9px;color:#24507d;border:1px solid #c8d7e8;background:white;border-radius:5px}.reader-callout{padding:15px 18px;background:#edf5ff;border-left:4px solid #3d77b0}.revision{font-size:13px;color:#526b89}.formula{padding:15px;background:#eef3fa;line-height:1.9;overflow-x:auto}td{overflow-wrap:anywhere}td:first-child{min-width:140px}.reader-controls{display:flex;gap:10px;margin:16px 0}.reader-controls button{font:inherit;font-size:14px;border:1px solid #c8d7e8;background:#fff;padding:8px 13px;border-radius:6px;cursor:pointer}@media print{details.reader-note{break-inside:auto}.reader-controls{display:none}.reference-badge{font-size:11px}}'''
    source=source.replace('</style>',css+'</style>',1)
    source=source.replace('</nav>','</nav><div class="reader-controls"><button type="button" id="expand-notes">모든 설명 펼치기</button><button type="button" id="collapse-notes">모든 설명 접기</button></div><p class="revision">각 실험 바로 아래의 회색 설명을 펼치면 목적·조건·용어·가정·해석 한계를 볼 수 있습니다.</p>',1)
    source=source.replace('</body>','''<script>document.getElementById('expand-notes').addEventListener('click',()=>document.querySelectorAll('details.reader-note').forEach(d=>d.open=true));document.getElementById('collapse-notes').addEventListener('click',()=>document.querySelectorAll('details.reader-note').forEach(d=>d.open=false));</script></body>''',1)
    source=source.replace('후속 Cyclone Default','Cyclone Default').replace('후속에서는수정없는고정런타임과wlp2s0지정을함께적용해117/117받았다.','')
    REPORT.write_text(source,encoding='utf-8')
    (NOTES/'revision_receipt.json').write_text(json.dumps({'report':str(REPORT),'baseline':str(baseline),'data_unchanged':True,'new_measurements':False,'followup_source':'ros45_stock/cyclonedds_default','explanation_sections':len(additions),'details_count':source.count('<details ')},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(REPORT),'details':source.count('<details '),'bytes':REPORT.stat().st_size},ensure_ascii=False))


if __name__=='__main__':main()
