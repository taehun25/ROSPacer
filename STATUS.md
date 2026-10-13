# ROSPacer 구현 및 날짜별 검증 기록

ROSPacer 0.1 초기 구현이다. proposal IV의 정적 설정 생성, HTB+fq 송신 제어,
sender 통계 수집 및 적응식 계산을 구현했다. 적응형 Wi-Fi 성능 검증은 완료하지 않았다.

## 배치

| 노트북 | 역할 | 계정·현재 IP | NIC 인터페이스·드라이버 |
|---|---|---|---|
| 12 (HP) | Publisher, governor 실행 | csi2@192.168.0.3 | wlo1, iwlwifi |
| 10 (Lenovo) | Subscriber, 수신 로그 | csi@192.168.0.4 | wlp2s0, rtw89_8852be |

두 호스트 모두 Ubuntu 22.04.5 / ROS 2 Humble, Cyclone DDS 소스 0.10.5.
Fast DDS 시스템 패키지는 12=2.6.10, 10=2.6.11이다. W1에서는 양쪽에 동일한
2.6.11 DDS/RMW 라이브러리 사본을 별도 경로에서 로드했다. 시스템 패키지는 유지했다.
현재 SR2는 149번, 80 MHz, center 5775 MHz다. 이전 36번 자료는 구분해 보관한다.
4/5는 B2를 마친 뒤 AX1500(149번·80 MHz)에 연결되어 있으며 실험 프로세스가 없다.

두 노트북의 모든 코드·생성 XML·검사 결과·실험 로그는
`~/ros2_ws/src/large_data_1009/ROSPacer/` 아래에 있다.
실험 종료 후 governor나 ROS smoke node를 실행해 두지 않았다.

## 통과한 검사

- 로컬 모델·스키마·통계 reset·통계 누락 시 변경 방지 검사 9개 통과.
- 실제 12번에서 Fast DDS 2.6.10, Cyclone DDS 0.10.5가 생성 XML을 읽고 ROS 노드를 생성.
- 12→10 Wi-Fi, Reliable / KEEP_ALL, 1 MiB payload, 1 Hz, 샘플 3개, HTB+fq fixed pacing.
  입력 C=20Mbps는 제어기 개발값이며 링크 C0 측정값이 아니다.
- 최종 결과 폴더: `runs/smoke_20261010_164617/`.

| 미들웨어 | 수신 | fq drop | 발행 호출 최대 시간 | fq 누적 전송 byte |
|---|---:|---:|---:|---:|
| Fast DDS | 3/3 | 0 | 479.57 ms | 4,999,274 |
| Cyclone DDS | 3/3 | 0 | 498.32 ms | 3,583,790 |

fq bytes에는 RTPS 제어·헤더·재전송이 포함된다. 위 수치로 delivery 개선률이나 링크 goodput을 주장하지 않는다.
버스트 송신을 늦추며 publish 시간이 길어진 것은 역압의 초기 관측이다.
대량 샘플·장시간·과부하·단절에서 같은 경로와 전체 전달이 유지되는지는 별도 W1 검증이 필요하다.
10번은 기본 transport를 사용했고 ROS QoS만 Reliable/KEEP_ALL로 설정했다.
양쪽 정적 최적화의 비교 실험이 아니다. 호스트 시계를 맞추지 않아 E2E latency를 계산하지 않았다.

두 미들웨어 시험 후 12번 qdisc는 원래 noqueue로, 임시 rmem_max는 212992로 복원했다.
모든 시험 프로세스는 유한한 timeout/duration으로 종료한다.

## 발견·해결한 사항

Fast DDS 원본 XSD가 compile되지 않는 미정의 숫자 타입과 userTransports의
XSD/parser 불일치를 공식 소스로 확인했다. 원본은 보관하고 검증용 수정 사본을 분리했다.
Cyclone WHC high/low/high-init의 유효 범위를 함께 설정하도록 했다.
ROS smoke 메시지는 UInt8MultiArray를 사용한다.

fq flow_limit을 proposal의 하한 ceil(Qtx/MTU)로만 정했을 때
Fast DDS 82,094개, Cyclone DDS 34,877개의 qdisc drop을 관측했다.
그때는 publish 호출이 2.67/3.99 ms로 짧았고 많은 repair를 통해 3/3 수신했다.
샘플 버스트와 repair 여유를 수용하도록 한도를 늘린 후 위의 drop 0 및 publish 지연을 관측했다.
이 전후 차이는 qdisc 보관/드롭이 역압 경로를 끊을 수 있다는 W1 검증 대상으로 기록한다.
현재 큰 한도 선택의 최적성과 CPU/메모리 비용은 아직 검증하지 않았다.

## 다음 필수 작업

1. 두 NIC 모두 iw survey dump가 비어 있다. 12번에서 root로 읽어도 동일하다.
   busy/active/tx airtime 계수기를 제공하는 NIC/드라이버 또는 동등한 sender 측 관측 경로를 확보해야
   proposal 식 (7)을 실제 Wi-Fi에서 검증할 수 있다. 결측값을 0으로 채우지 않는다.
2. 두 미들웨어의 publish duration, ss socket memory, UDP error, tc drop, delivery를 함께 기록해
   W1 역압 경로를 장시간·과부하·단절에서 검증한다. Fast DDS blocking timeout도 처리해야 한다.
3. 12/10에서 C0, RTT, PHY rate, retry 및 relay 포함 여부를 식별하고 RTPS overhead를 캡처한다.
   초기 설정 생성기의 임시 C/o 값은 성능 평가에 그대로 쓰지 않는다.
4. 양쪽 XML·수신 버퍼 요청을 적용하는 경로와 제한된 10번 sudo는 10/11 추가 점검에서 확인했다.
   실제 socket accounting·버퍼 운영점의 최적성·오류 원인 분리는 계속 검증한다.
5. RTPS signature 분류기는 10/11 추가 점검에서 일반 UDP bypass를 확인했다.
   정확한 프로세스·토픽별 식별, 다른 DDS 흐름·단절·1:N에서의 경로는 별도 검증한다.
6. Default / Static / ROSPacer 비교는 같은 12/10 쌍에서 진행한다.
   adaptive 검증 후 1:N·다중 토픽·golden profile·자동 측정·Zenoh를 확장한다.

RP Bench는 ROSPacer 실행에 필수 의존성이 아니다. 현재 도구로 개발 검증을 할 수 있다.
논문용 반복 실험과 지표 집계를 위해 추후 RP Bench 또는 확장된 별도 측정기를 검토한다.

## 2026-10-11 추가 점검

10/30 Fast/Cyclone 초고, 11/04 학위논문, 11/30 Zenoh 포함 투고를 기준으로
[EXECUTION_PLAN.md](EXECUTION_PLAN.md)를 작성했다.
`lab_preflight.py`는 SSH로 점검 코드를 보내므로 최신 코드 배포 전에도 상태를 수집한다.
추가한 readiness 검사 4개를 포함해 로컬과 12/10 양쪽의 단위·XML 검사 총 13개가 통과했다.

12/10 접속과 SR2 연결을 재확인했다. 양쪽 qdisc는 noqueue이며 점검 시 matching
Pacer/traffic/iperf 프로세스가 없었다. `runs/preflight_20261011_113828/`에 보고서를 저장했다.
12번은 root survey도 여전히 비어 있다. Intel debugfs의 fw_system_stats는
`System stats not supported:99`를 반환했다. fw_rx_stats의 channel_load는 0이며
active/busy/tx 세 시간 계수기를 대체할 근거를 확보하지 못했다.
이를 대체 airtime 관측이라고 처리하지 않는다.

이 경로 검토에 사용한 원본은
[Linux v6.8 iwlwifi debugfs.c](https://github.com/torvalds/linux/blob/v6.8/drivers/net/wireless/intel/iwlwifi/mvm/debugfs.c)다.
일부 장치의 시스템 통계 읽기 기능이 존재하는 것과 현재 펌웨어에서 지원되는 것은 별개다.

이 예비 점검 시 양쪽 Fast DDS 버전 차이와 10번 sudo 제한은 유지됐다.
12번 chrony tracking이 첫 점검에서 timeout이었으나 재조회에는 Normal을 반환했다.
10번은 Not synchronised다. 따라서 현재 E2E 지연값을 계산하지 않는다.

`runs/linkpilot_20261011_114208/`에서 12→10 TCP iperf3 예비 측정을 3회 수행했다.
각 회 2초 omit 뒤 10초를 측정했으며 receiver 처리량은 89.59, 97.25, 105.92 Mb/s다.
quiet link 검증과 DDS goodput 측정은 아니며 이 값으로 모델 교정을 완료했다고 주장하지 않는다.
동일 예비 측정의 ping은 20개 중 19개 수신, RTT min/avg/max=27.986/199.763/1051.614 ms다.
평균 4ms라는 prototype 입력과 실제 환경의 차이가 크므로 링크 안정성·전원 절약 등을
먼저 조사하고 교정한다. 원인으로 단정하지 않는다.
추가 조회에서 양쪽 Wi-Fi power save가 on임을 확인했다. 이번 점검에서는 변경하지 않았다.
링크 예비 측정은 qdisc/sysctl을 바꾸지 않았고 각 iperf server에는 25초 timeout을 두었다.

## 2026-10-11 W1 지표·분류기·수신 설정 점검

두 노트북에 발행 실패를 보존하는 JSONL 로그, 요청 샘플 기준 지표 계산기,
ss/UDP/qdisc/class/driver telemetry를 배치했다. 단위·XML·준비 상태·지표·class 출력
검사 총 19개가 로컬과 12/10에서 통과했다. Ubuntu tc의 HTB class가 `-j`에도
text를 반환하는 것을 확인해 text parser를 추가하고 원문을 보관했다.

10번은 이미 sudo 그룹이었다. 사용자 실행으로 `tools/enable_receiver_sudo.sh`의
제한된 정책을 설치한 뒤 `sudo -n`의 지정된 rmem_max 및 iw 명령을 확인했다.
처음 후보 문법은 12번 visudo에서 검사했고, 설치 스크립트는 10번에서도 후보 및
전체 sudoers 문법을 확인한다. 정책은 rmem_max 1048576/212992와 조회 명령에 한정한다.
10번 root survey도 여전히 빈 출력이다. 관리자 권한 확보가 airtime 통계 지원을 만들지는 않는다.

모든 아래 DDS 시험은 Reliable/KEEP_ALL, payload 1MiB, 개발 입력 C=20Mbps,
fixed HTB+fq다. 이 C는 실측 교정값이 아니며, adaptive 제어 시험이 아니다.
요청 5Hz는 응용 부하 약 41.94Mbps로 개발 상한보다 크다.

| 결과 폴더 | 미들웨어·수신 transport | 요청 Hz | 실제 발행 Hz | 발행 성공 / 요청 | 수신 / 요청 | 10번 UDP RcvbufErrors 증가 |
|---|---|---:|---:|---:|---:|---:|
| smoke_20261011_210701 | Fast DDS, 수신 기본 | 5 | 2.09 | 3/12 | 3/12 | 312 |
| smoke_20261011_211449 | Cyclone DDS, 수신 기본 | 5 | 1.72 | 12/12 | 12/12 | 38 |
| smoke_20261011_212630 | Fast DDS, 양쪽 XML | 5 | 2.17 | 2/12 | 0/12 | 0 |
| smoke_20261011_212630 | Cyclone DDS, 양쪽 XML | 5 | 2.01 | 12/12 | 12/12 | 0 |
| smoke_20261011_212934 | Fast DDS, 양쪽 XML | 1 | 1.00 | 6/6 | 6/6 | 0 |

Fast DDS의 두 5Hz 시험은 `RCLError: Failed to publish: cannot publish data`로 종료했다.
실패까지의 짧은 구간에서 계산한 실제 Hz이며 안정 처리량을 나타내지 않는다.
수신자 기본 조건의 성공 발행 기준 전달률 3/3=100%와 요청 기준 3/12=25%를 함께
보존한다. Cyclone도 12/12라는 수치만으로 요청 5Hz를 유지했다고 해석하지 않는다.
전역 UDP 카운터 변화에는 다른 프로세스가 포함될 수 있고, 발행 오류 원인은 아직 확정하지 않았다.
수신 XML·커널 상한·부하 등 조건과 시간이 다르므로 위 표를 개선률이나 벤더 순위로 사용하지 않는다.

양쪽 XML 시험에서 ROS python3 소켓의 ss skmem rb2097152와 tb131072를 확인했다.
이는 요청한 1MiB/64KiB와 Linux accounting 값의 차이를 보여 주며,
실제 available queue 용량이나 메시지 보관량이 정확히 그 값이라는 주장은 아니다.
양쪽 XML 시험의 qdisc drop 최대값은 0이다. 종료 후 양쪽 rmem_max는 원래 212992로,
12번 root qdisc는 noqueue로 복원했다. 시계 미동기화로 E2E latency는 계산하지 않았다.

분류기를 IPv4 IHL=5, IP 조각 없음, UDP 페이로드 `RTPS` magic match로 변경했다.
지정 peer와 SPDP 목적지의 RTPS는 7ac0:10으로, 나머지는 7ac0:20으로 보낸다.
양쪽 XML Cyclone 시험의 RTPS class 누적 최대값은 14,273,062 B이며
원문은 governor CSV의 class_json에 있다. DDS 프로세스·토픽별 분류는 아니다.

`runs/classifier_20261011_213052/`에서 4Mbps 개발 입력의 fixed governor를 실행하고
같은 peer로 일반 UDP 20Mbps/6초를 송신했다. RTPS class 최대 0 B,
bypass class 최대 15,445,152 B로 일반 UDP bypass를 확인했다.
iperf3 3.9의 server end summary는 interval에서 byte 수신이 있는데도 bytes=0을
기록했으므로 여기서 수신 goodput을 인용하지 않는다. 원본 client/server JSON을 보존했다.
시험 후 noqueue 복원, sysctl 미변경을 확인했다. 일반 UDP 한 종류에 대한 점검이며
모든 UDP·터널·보안 RTPS 경로를 검증한 것은 아니다.

## 2026-10-12 W1 장비 측정 및 남은 전제

원자료는 `runs/w1_20261012_163000/`, 보고서는 상위 디렉터리의
`html 파일 모음/결과/W1 구현 전제 검증_261012.html`에 보관했다.
W1 전체 완료 상태가 아니다. 미수행 항목과 실패한 초기 run도 보존했다.

12→10 UDP iperf3 30초 3회 수신 처리량은 23.13/21.74/22.55 Mb/s이며
중앙값 C0는 22.5489 Mb/s다. TCP 30초는 61.46 Mb/s, ping 200회는
200회 수신, 평균 RTT 45.857 ms다. iperf3 3.9 receiver end-summary의
bytes=0 문제 때문에 보존한 수신 interval의 byte/seconds로 계산했다.
무선 airtime 계수기가 없어 외부 채널 점유율이 0인 교정이라고 주장하지 않는다.

1 MiB/KEEP_ALL/30초, 요청 0.8C0, HTB 0.5C0 조건에서 Fast DDS와
CycloneDDS의 fq flow_limit=100/1490을 각각 측정했다. Fast는 각 run에서
발행 실패 19회를 기록했다. Cyclone의 교정 후 두 run은 성공·수신 33/33이지만
예정 65개를 모두 발행하지 못했다. publish 대기, 소켓 메모리, qdisc를 함께
수집했으며, UdpSndbufErrors와 fq drop이 0이라는 사실을 기다림만 존재한다는
증거로 사용하지 않는다. HTB에서 publish까지의 전체 인과 경로는 아직 확정하지 않았다.

패킷 캡처에서 Cyclone의 첫 DATA_FRAG에 68 B 헤더가 있어 기존 1408 B
fragment가 IP 단편화되는 것을 발견했다. 생성값을 1404 B로 수정하고
Static/fixed 캡처에서 사용자 IP 단편화 0을 확인했다. Fast Vendor의 XML
namespace와 기본 메모리 정책 문제도 수정했다. 양쪽 Default/Vendor/Static/fixed
시운전은 각각 17/17 수신했다. Vendor는 구현한 기능 범위의 시운전이며
proposal 전체 Vendor 설정 및 adaptive ROSPacer의 검증 완료를 뜻하지 않는다.

4/5를 같은 SR2 AP에 연결해 5→4 배경 부하를 넣은 C2에서 12→10 수신은
9.26/9.51/9.61 Mb/s였다. 추정값이 없으므로 모델 오차 20% 기준은 판정하지 못했다.
다른 AP AX1500은 149번, SR2는 36번이어서 B2 같은 채널 간섭 조건이 아니다.
사용자가 다른 AP 관리자 계정을 확인하지 못해 채널 변경 및 B2는 미수행이다.
36이라는 번호 자체가 필수인 것이 아니라 두 AP의 채널 대역이 겹쳐야 한다.

veth에서 HTB 200 Mb/s와 두 burst를 진단했지만 실제 Wi-Fi의 200 Mb/s 상한은
검증하지 못했다. 현재 무선 처리량이 그보다 낮다. Wi-Fi에서 상한 200 Mb/s를
부착한 10초 시운전은 baseline 22.74, burst 1500 B 22.16, burst 65536 B
22.45 Mb/s였다. 단기 관측이며 처리량 무손실을 보장하는 통계적 근거가 아니다.

plan/golden, 도착 간격 지터, 단절 후 첫 수신 지표, 라이브러리/소스 근거를
보강했다. Golden XML은 양쪽 실제 노드와 publisher 생성에 성공했다.
자동 검사 20개가 통과했다. 10번 시계 미동기화와 12번 불충분한 시계 근거로
E2E 지연을 계산하지 않았다. active/busy/tx 확보, AP 중계 보정과 자기 부하
검증, B2, 모델 예측 오차, 실제 무선 200 Mb/s 검증이 남는다. Zenoh는 후속 단계다.

종료 영수증과 최종 조회에서 12/10 qdisc=noqueue, rmem_max/wmem_max=212992,
Wi-Fi 절전 on, CPU powersave 복원을 확인했다. 단절 실험의 방화벽 규칙과
커널 진단용 임시 장치는 제거했다. 4/5의 유한 시간 경쟁 트래픽도 종료됐다.

## 2026-10-12 채널149 B2 및 구현 수정

사용자가 SR2를149번으로 변경한 뒤 두 AP 모두149번·80 MHz, 중심5775 MHz임을
실제 연결에서 확인했다. 현재12/10과 관리 PC는 SR2,4/5는 AX1500이다.
AX1500에서4번 IP는192.168.0.4,5번은192.168.0.5다. 같은 IP 대역의 두 AP를
방문할 때 기존 SSH host key를 엄격히 확인해 장비를 구분했다.
4/5는 저장된 프로파일로 자동 이동했고, 연결 확인 실패 시 복귀하는 감시자를 사용했다.

원자료는 `runs/w1_20261012_ch149/`, 추가 보고서는 상위 디렉터리의
`html 파일 모음/결과/W1 149채널 B2 추가 검증_261012.html`이다.
기본 버퍼212992 B에서 UDP30초×3 중앙값158.72 Mb/s, TCP30초211.78 Mb/s,
ping200/200, 평균 RTT18.011 ms였다. UDP의 수신 버퍼 오류가 증가하여 이 값을
순수 링크 용량으로 식별하지 않는다. 별도1 MiB 소켓 교정에서는 UDP217.39/
219.18/222.92 Mb/s, 세 회의 수신 버퍼 오류 증가0을 확인했다. TCP는157.08 Mb/s다.
버퍼·시간 조건이 다른 TCP 두 수치를 개선률로 해석하지 않는다.
1 MiB 교정에 PHY·재시도를 맞춘 조건부 유효 O는10.30 µs이며 intrinsic 비용이 아니다.

C2의0.9×158.72 Mb/s 경쟁 트래픽에서12→10 수신은69.55/72.49/71.23 Mb/s였다.
B2 초기 구현은 iperf 협상 비용 때문에 반복 주기가약4.4초였다. 원문을 보존하고
4초 시작 간격으로 보정한3회를 별도로 수행했다. 간섭 source40/40 burst 성공,
시작 간격 중앙값4.004443초, UDP전송 중앙값2.000091초, 주기 초과0회다.
AP2유휴168.21 Mb/s, B2수신126.14/120.63/118.28 Mb/s다. 시각 대응은
SSH 왕복 시간의 대략적 대응으로 동시 진행만 확인했고 E2E지연 자격이 아니다.

실제 무선의1 MiB 소켓·10초 진단에서 unshaped229.83 Mb/s,
HTB200 Mb/s의 burst1500/65536 B에서 payload193.03/192.77 Mb/s였다.
class 정상 구간은199.9972/199.9957 Mb/s, fqdrop0, 종료noqueue다.
36번의 veth 진단과 구분하며, 한 번의 단기 관측을 모든 조건의 정확도 보장으로 쓰지 않는다.

새1 MiB 교정값219.18 Mb/s, 요청0.8C0, HTB0.5C0로 역압을 다시 확인했다.
Fast 두 한도에서 예정628개 중 성공·수신44/44 및41/41, 발행 실패6 및10회다.
Cyclone1404 B/fq100에서는 재전송INFO_DST 헤더72 B 때문에 UDPpayload1476 B가
IP단편화되어 분류기 우회가 발생했다. 이 결과는 상한검증 근거에서 제외한다.
초기 전송만 본 이전1404 B 교정이 재전송 경로까지 보장하지 않았음을 기록한다.

RTPS20+INFO_TS12+INFO_DST16+DATA_FRAG36=84 B를 보수적으로 예약해 현재
fragment1388 B를 생성한다. 수정 후 두 한도에서 성공·수신358/358 및357/357,
발행 실패0, publish p50약83 ms, class109.45/109.35 Mb/s, fqdrop0이다.
두 첫15초 캡처의 IP단편화0, tcpdump kernel drop0, 전체 run bypass약0.003 Mb/s다.
이 표본에서 큰fq한도의 성능 우월성은 입증하지 않았다. 자동검사21개가 통과했다.

12/10의 qdisc=noqueue, rmem_max/wmem_max=212992, 절전on, CPU powersave를
최종 확인했다.4/5의 iperf·worker·기존 campaign도 모두 종료 상태다.
무선 active/busy/tx, AP중계·자기부하 보정, 검증된 시간동기와 E2E지연,
B2/C2모델 오차 및 적응형 실험은 여전히 미달성이다. 기존36번 비교군 시운전을
149번의 성능 비교로 재사용하지 않는다. Zenoh는 사용자 순서에 따라 후속이다.

## 4·5번 survey 채널 귀속 수정 준비

4/5의 실제 접속은 AX1500 채널149/80MHz지만, 현재 UDP 트래픽의 survey 계수는
36번 항목으로 누적되는 현상을 재현했다. 과거 값만 남은 상태가 아니다.
mt7921의 채널 컨텍스트 경로에서 survey 저장 위치가 이동하지 않는 공개 결함과
소스를 대조했으며, 정확한 Ubuntu linux-hwe-6.8 136/138 소스에 수정안을 backport했다.
각 노트북의 실행 커널용 의존 모듈5개가 빌드·서명되었다. 원본 드라이버는 유지 중이다.
소스 아카이브·Ubuntu diff는 공식 dsc의 SHA256과 일치하고, 컴파일러 GCC12의 로컬
설치 패키지는 해당 노트북의 APT SHA256과 대조했다. GCC12 및 의존 패키지4개를 설치했다.
개인 서명 키는 각 장비의 root 전용 디렉터리에만 있고, 공개 인증서는 모듈 서명 전용이다.

두 장비 모두 SecureBoot enabled/lockdown integrity이며, 새 MOK 키는 아직 미등록이다.
설치된 mokutil은 `is not enrolled`에서도 종료값0이므로 종료값만으로 등록을 판정하지 않는다.
MOK 부팅 화면의 사용자 등록이 선행되어야 적용할 수 있다. 등록 요청·드라이버 교체·재로딩은
아직 실행하지 않았다. 재부팅으로 실행 커널이 달라지면 해당 버전으로 다시 빌드한다.
원본 모듈을 보존하는 별도 설치 경로와180초 미확인 자동 복구 guard를 준비했고,
미등록 키·커널 불일치·변조 모듈 거부 fault 검사3개가 통과했다. 실제 적용·복구·계수기
정확도는 미검증이다. 이 준비만으로 적응형 입력 확보나 W1 완료를 주장하지 않는다.
원자료/안내: `runs/w1_completion_readiness/survey_driver_fix/status.html`.

### 4번 적용 후 현재 상태

사용자가4번의 MOK 등록을 완료했다. 재부팅 후 실행 커널은138로 변경되어 해당 버전으로
재빌드·서명했다. mokutil은 등록된 키에 종료값1과 `is already enrolled`를 반환하는 것도
실측해0/1을 허용하면서 명시적 출력으로 판정한다. 이 경우를 포함한 fault 검사5개가 통과했다.
처음 두 적용은 장치 및 NetworkManager의 준비 시점 때문에 재연결이 실패해 원본으로 자동
복구되었다. 실제 WiFi 복귀를 확인한 뒤, NM의 안정 상태까지 대기하는 방식으로 보완했다.
세 번째 적용은 모듈5개의 실제 로드 srcversion 일치, WiFi 재연결, 계수기 검사 후 확인했다.

4→5 UDP100 Mb/s5초의 전·후7.359초 구간에서149번active/busy/tx는7359/1325/2437 ms
증가했고149번에in-use가 표시되었다.36번의 모든 시간 계수 증분은0이다.35개 단조 증가
표본의 수집 간격 중앙값207.6 ms, 최대228.1 ms다. 수신 interval bytes/time은98.70 Mb/s,
iperf 손실률0.094%다. 서버 end.sum.bytes=0은 계산에서 제외했다.
4번의 채널 귀속 결함은 해결됐으며, 수정 모듈은 현재138 커널의updates/rospacer-survey에
유지된다. 원본 모듈은 보존되었고, guard 및 iperf는 종료됐다.4/5는power_save on/noqueue다.
5번의 MOK는 아직 미등록이며 원본 드라이버를 사용한다. busy가tx보다 작은 실제 관측 때문에
busy의 자기송신 포함 여부를 가정하지 않는다. 통계 의미·AP 중계·자기 부하 보정과 적응형
모델 정확도는 추가 교정이 필요하다. 시간 동기화 및 W1 전체는 여전히 미완료다.

## 2026-10-12 4·5번 후속 W1 측정

위의 5번 미등록 상태는 당시 기록이다. 이후 사용자가 두 장비의 MOK 등록을 완료했고,
현재 두 장비 모두 kernel6.8.0-138의 서명 모듈5개를 로드해 srcversion을 확인했다.
양방향 probe에서149번 계수 증가/36번 증분0을 확인했다. 원본 드라이버는 보존한다.

원자료는 `runs/w1_20261012_radio45/`, 최신 보고서는 상위 폴더의
`html 파일 모음/결과/W1 4·5번 유선 동기화 및 계수기 검증_261012.html`이다.
UDP1400B·1MiB소켓·30초×3의 수신 중앙값326.893Mb/s,
TCP282.678Mb/s, ping200/200·평균18.545ms다. UDP3의RcvbufErrors52건도 보존했다.
유선50.2→50.1 chrony는 상대 시계만 검증하며 UTC 기준이 아니다.
run별 tracking/sources/ntpdata와 범위·연속성·오차한계를 검사해 지연을 계산한다.
지터는 proposal의 |연속 도착 간격−요청 발행 주기|p99로 추가했다.

기존 연구용 수정 DDS가 실제 로드되는 것을 발견해 해당8회는 별도 보존했다.
공식 FastDDS2.6.11/RMW6.2.10 closure와 수정 없는 CycloneDDS0.10.5/RMW closure를
격리 경로에 복제하고 실제 maps 해시를 매 실행 대조했다. 기존 연구 설치는 유지한다.
고정 런타임의 Default/Vendor/Static/fixed8회는 모두117/117수신,
시계 보고 오차 한계0.082ms 이하였다. CycloneDefault는 WiFi인터페이스만 지정했다.
FastVendor의 실제 WiFi TCP payload와 Static/fixed의IP단편화0을 캡처로 확인했다.

새138커널의 실제WiFi에서 HTB class199.9999/199.9918Mb/s,
burst1500/65536B, fqdrop0, 종료noqueue를 확인했다.
W1역압30초·1MiB·KEEP_ALL·발행0.8C0·HTB0.5C0를 두 DDS/두 fq한도로 수행했다.
Fastfq100의drop 및UdpSndbufErrors966599건, 설계한도는둘 다0이었다.
성공·수신은Fast117/117,414/414 및Cyclone178/178,536/536이며 예정은각936개다.
실제 발행 감소와 원래 요청 부하를 구분한다. ss수집 간격 중앙값약100.1ms였다.

5초 peerUDP 양방향drop 후 Cyclone의 첫도착0.0578s와 proposal1초이동창p95복구
3.993s를 구분했다. Fast는 첫도착1.594s이며 관측 창의p95복구는미달(검열)이다.
B2는유휴390.468,간섭300.954/298.302/297.405Mb/s였고 수신 버퍼 오류0이었다.
C2는SR2로가드이동 후 유휴3회중앙값329.696,혼잡220.068/240.958/226.146Mb/s다.
C2유휴3회의마지막에RcvbufErrors59건을 기록했다. 종료 후4/5는AX1500에 복귀했다.

rawbusy<tx 때문에 기존 식(7)의 전제가 자기 부하0.2..0.8에서 성립하지 않는다.
자기TX를 다시 빼지 않는 후보 해석과 실제 수신PHY를 사용한 B2오차8.55..11.86%,
C2오차1.33..6.00%는 진단용 조건부 계산이다. 자기부하 잔차와O의 독립 검증은미완료다.
4의동시monitor참조는AP중계 프레임을 포착했으나 전체하향 캡처는불완전하다.
일반 adaptive의 검증 게이트는 유지하며 거부/qdisc불변을 실제 확인했다.
별도 bounded진단 모드는0.9C0 ceiling 아래에서200ms주기로각230회갱신·보류0,
두 DDS각156/156수신했다. 이 결과를 정식 모델승인이나 성능우위로 쓰지 않는다.

10의독립 관측을 준비했다. monitor인터페이스 광고 및 dumpcapcapabilities는확인했지만
자동rfmon은실제실행에서unsupported로 실패했고 원래인터페이스는그대로였다.
10의일반rootPython은원격비대화형sudo정책에막혀 사용자에게 가드의로컬실행을 요청했다.
가드는시작신호를120초기다린 뒤45초만4·5MAC을캡처하고 임시monitor를삭제한다.
코드해시c04f9e7fac6a6452e8cdf8781114ecc5a73b85bfcd38e6018e9b8155fa0a599e를
전송 후대조했다. MOK나일반root권한추가부여는하지않는다.

최종조회에서4/5실험프로세스종료,임시방화벽규칙없음,qdiscnoqueue,
AX1500복귀를 확인했다. 최초전원세션은복원확인후종료했고 phase2는1시간자동복원가드다.
독립관측을위해 유선관리·runtimechrony는유지중이다. W1정식통과판정은보류이며
Zenoh는사용자순서에따라후속이다. 자동검사32개통과,각실행의커밋/소스SHA와설정/시계를저장했다.

### 2026-10-12 독립 관측 완료 및 최종 복원

10번의 독립 HE 모니터 캡처를 `independent10_retry`에서 45초 수행했다.
처음 경로에서는 제어기 시작 대기 초과를 관측했고, 나중에 동일 marker 경로에
나타난 빈 pcap도 별도 보존했다. 새 경로와 준비 후 자동 시작 순서로 재측정했다.
캡처는 9,364프레임, HE 데이터 3,984개, 커널 drop0이었다. AP→5 데이터539개 중
A-MSDU535개, 관측 wire bytes 약5.33MB였고 실제 relay payload는 약99.99MB였다.
단위가 다르고 재전송이 포함되므로 정확한 캡처율로 쓰지 않는다. 모든 데이터에
계산된 airtime과 A-MPDU reference가 없어 전체 PPDU airtime은 독립 식별하지 못했다.
제어기 수정본은03519be에 고정했고 실행 시 working-tree SHA를 별도 보존했다.
초기 측정의 Pair provenance는7fb2af3이며 새 source trace와 함께 해석해야 한다.

모니터를 추가하지 않은4번의 AP직접 전송8초에서 busy0.585초,tx5.671초,
중계8.34초에서 busy2.066초,tx3.960초였다. 기존tx≤busy 전제는 실제 장비에서
성립하지 않는다. AP중계가 busy에 반영된다는 정성적 근거와 aggregation 관측은
확보했지만, 식(7)의 정량 차감·자기부하 잔차·intrinsic O 승인은 미통과다.
수신5번 station rx duration도 자기부하0.2/0.4/0.6 동안 증분0으로 남아,
그 값을 실제 airtime0으로 대체할 수 없다. 기존 adaptive 검증 게이트를 유지한다.

4/5 session_independent10을 종료하고 양쪽 baseline 복원true를 확인했다.
Wi-Fi 절전on, CPU powersave, rmem/wmem212992, root qdisc noqueue, 실험 프로세스 종료,
임시 방화벽 규칙 없음, AX1500 연결을 확인했다. 4번 runtime chrony source와5번
임시 유선 허용·수동 주소를 제거하고4번의 유선 연결을 비활성화했다. 저장된
NetworkManager/chrony 설정 파일은 수정하지 않았다.10번 w1mon 삭제와SR2 연결 유지,
제어PC의SR2 복귀도 확인했다. 서명된 survey 수정 드라이버와MOK 등록은 유지했다.

갱신 보고서는 `html 파일 모음/결과/W1 4·5번 유선 동기화 및 계수기 검증_261012.html`.
W1 전체를 통과로 표시하지 않는다. 후속은 장비별 busy/TX 입력 계약과 aggregation을
반영한 중계 비용 교정, 별도 데이터로 자기부하/B2/C2 재검증이다. 정확한 airtime
합의 독립 검증에는 완전한 HE/PPDU 메타데이터 관측 경로가 필요하다.


### 2026-10-13 무선 입력 재검증 및 native 교정 adaptive

현재 4→5 MT7921/138커널/149번80MHz에서 polling0/50/200/1000/2000ms,
idle/AP-only/relay 반복 및5→4 방향을 확인했다. busy<TX는 읽는 주기와 무관하게
부하에서 반복됐다. raw busy를 TX-inclusive 총 airtime으로 사용하지 않는다.
수신 PHY와 native RX byte/MPDU/AMPDU/AMPDU byte, 송신측 RX BA로 운용 보정을
교정했다. native RX duration의 미갱신0은 제외하고 음수β는 보존했다.
연속부하만으로 만든 후보는 burst에서 실패했고 실패 자료도 보존한다.

고정 교정 후 새 DDS 자기 부하6조건 rawβ=-0.243%..3.141%, |β|<=5% 통과.
Fast0.8 요청478개 중418개 발행·418개 수신으로 요청 부하 달성과 구분한다.
새 B2 3회 오차8.698%..10.795%, 별도 C2 3회2.239%..5.415%, 모두<=20%였다.
C2는 계수학습에 사용하지 않은 자료지만 계수 고정 전에 수집했다.
SR2 byte 정규화는 quiet만 사용했다. 현재 AX 프로파일을 SR2에서 그대로 승인하지 않는다.

정상 govern adaptive의 새 native 교정 분기를 실제 실행했다. 유선 receiver feedback
200ms, 약3초 창,0.9C0 ceiling, 잘못된 신원/범위/결측을 거부한다.
Fast/Cyclone 각120/120수신, 갱신106/121회, 중앙값200.27/200.51ms;
feedback을 먼저 종료해 각51회 stale hold와 qdisc 복원을 확인했다.
기존 diagnostic 기록을 정식 승인으로 바꾸지 않았고 미교정 입력 gate도 유지한다.
자동검사38개 통과. 4/5 power/wire 최종복원true, 남은 실험프로세스 없음;
절전on, CPU powersave, rmem/wmem212992, noqueue, AX1500, 임시주소 삭제를 확인했다.
12/10 경쟁 프로세스 종료 및 rmem/wmem212992 복원도 확인했다.

독립 BA32µs 참조와 effective BA31.754µs는 약0.77% 차이다. HE duration/LTF가
부족해 전체 PPDU airtime과 intrinsic O는 독립 식별하지 못했다. 수정 운용 모델의
현재 장비 검증은 통과하지만 원식의 W1 전체 승인·다른 장비 일반화·adaptive 성능
우위/동적 추종/drain 완료라고 표시하지 않는다. 새 지연도 시계 미승인으로 분석 제외.
원자료: runs/w1_20261013_radio_input_retry. 버전 관리된 근거: reference/w1-20261013.
보고서: html 파일 모음/결과/W1 실험결과/W1 무선 입력 추가 검증_261013.html 및
html 파일 모음/W1 보고서.html. source SHA와 source commit은 구분해 저장한다.


#### 최종 시간 순서 보강: 고정 후 C2 새3회

최종 점검에서 기존 C2의 수집 순서가 계수 고정 전임을 확인하여, 계수와 SR2 quiet
정규화를 유지한 채 c2_aggregation_confirmation 새3회를 추가했다. 실측
205.693/209.491/205.775Mb/s, 고정 모델 오차0.108/2.953/0.212%, 모두<=20%다.
기존 C2는 보조 자료로 보존하며 최종 판단에 새3회를 사용한다.
교정에 쓰지 않은 DDS 자기부하·B2·C2의 최종 자료 모두 계수 고정 후 수집됐다.

AP/채널 범위 확인을 qdisc 설치 전에도 수행하도록 보강했다. 실제 장비에서
미승인 profile과 잘못된 AP 모두 거부·qdisc 불변을 확인했다. 자동 검사39개 통과.
보강된 최종 native_adaptive_final에서 Fast/Cyclone 각120/120 수신,
갱신154/106회, 중앙값200.50/200.51ms, feedback 중단 후각51회 hold, qdisc 복원.
phase4 power/wire도 종료하고4/5복원true·남은 실험프로세스없음을 다시 확인했다.
현재 장비의 수정 운용 모델만 범위 내 승인하며 전체 HE/PPDU airtime·intrinsic O의
독립 식별과 보편 adaptive 성능 판정은 계속 구분한다. 원자료와 버전 관리된 근거는
동일한 경로에 보존한다. 최신 보고서의 C2와 제어기 표는 이 최종 결과를 따른다.
