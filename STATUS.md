# ROSPacer 구현 및 날짜별 검증 기록

## 2026-10-13 · W1 범위와 종료 재점검

원 proposal W1은 모델 입력·O 교정/비교·역압·최소 갱신기·시운전이다.
정식 Adaptive 우위/E/F 추종은W2 이후, full drain ablation은W4이므로 이번엔 제외했다.
새 B2 정상body64.59%/오류CRC후보91.72%; 입력 부족 보류를 재확인했다.
monitor 종료 후4의 ping/SSH 연결도 실패해 유선으로 회수·동일 AP 재연결 후 복구했다.
기존 SSH IPQoS 수정과 별개의 접속 단계 실패이며 exact firmware 원인은 미확정이다.
6개 캡처의 HE-LTF 기호 수/pre-FEC padding known 및 AMPDU last known은0이다.
raw LTF size1은 있지만 PPDU 전체와 intrinsic O의 독립 식별에는 부족하다.
4/5/12/10 qdisc·class·monitor·실험 프로세스·커널 버퍼 복원 재검사 전부 통과.
4/5 연구 DDS 각6개 실측 로드 해시 일치. 12/10은 동일 원본 비교 기준 없음.
원자료·환경·실제 dirty 소스 archive와 SHA 인덱스를 별도로 보존한다.
원자료: runs/w1_20261013_w1_closeout; 보고서: W1 항목별 상태점검_261013.html.

## 2026-10-13 · 4번 Wi-Fi SSH 수정 확인

5→4 SSH는 TOS0x10→0x08 전환 직후4→5 응답이 수신 캡처에 없어 재전송했다.
4 SSH 서버에 별도 drop-in IPQoS0x00을 적용하고 설정 검사·reload했다.
원래 lowdelay/throughput으로 잠시 되돌리면8초 timeout, 재적용하면 직접 Wi-Fi
SSH10회 연속 성공 및 양방향 각1MiB SHA 일치를 확인했다. 임시 PC tunnel과
추가 sshd/capture는 종료했다. NIC/DDS/qdisc 설정 변경 없음. AP 내부/driver의
정확한 손실 위치는 미확정이고 B2 passive CRC 누락이 해결됐다는 뜻은 아니다.
증거: runs/w1_20261013_ssh_repair; 진단 HTML의10절. 기존 미해결 영수증은 당시 기록.

## 2026-10-13 · Sender B2 관측 누락 진단 보강

6개 유효 CRC/control 진단과 실패 반복을 `runs/w1_20261013_sender_gap`에 보존했다.
B2에서 정상 body32.13%→오류 CRC 잠정 포함72.74%, HW FCS3765 증가를 관측했다.
호스트 kernel drop0; source TX0 observer도 누락이 남아 own-TX 단일 설명을 배제했다.
CTS에는 TA가 없고 RA=AP라 기존 필터에 누락됨을 확인했다. AP 제어 필터·FCS 진단·
RTS/CTS/BA 후보·FCS 가용성 로그를 실제 sender 경로에 추가했다. CRC 오류 byte는
추정에 쓰지 않는다. 보강 B2 RTS 개수 비율89.79%; 정상 body58.66%다.
NAV와 BA timestamp 차이99µs가 남아 airtime 대체/제어 승인은 보류한다.
강화 Fast/Cyclone shadow 각120/120수신·유효 추정47/19회, HTB 없음. 자동 검사52개 통과.
`validated=false`와 Receiver-assisted 경로를 유지한다. 세부 판정과 복원은 새 진단 HTML 참조.

## 2026-10-13 · Sender-only 프로토타입

Receiver-assisted를 유지한 별도 sender-local monitor/HE/MAC 추정 경로를 구현했다.
Fast/Cyclone 무경쟁 Static1MiB shadow는 각각76/44회 유효 추정, 각120/120 수신이었다.
B2 topology의 연속 경쟁 진단에서는 중계 관측 비율18.84%라 보류했다.
`adaptive-sender`는 미승인 프로파일의 HTB 설치를 거부한다. 정식 B2/C2 및 자동
HTB 성능 검증 완료로 처리하지 않는다. 모델·게이트·파서·복원 관련 전체48개 검사가 통과했다.
4/5/12/10의 유한 실험 종료와 임시 설정 복원은 `runs/w1_20261013_sender_only/final_restoration.json`에 있다.
자세한 조건과 한계는 [개발 기록](docs/sender-only-prototype.md)을 따른다.

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


#### Sender-only 입력 충분성·안정성 추가 검증 (10/13 시작, 10/14 종료)

원자료 runs/w1_20261013_sender_validation. 고정 v2 프로파일 재교정 없음,
receiver 통계는 사후 참조만 사용, HTB 미적용 shadow. UDP 자기 부하0.2/0.5/0.8
각2회 정상 구간 계산100%, |beta|p95<=4.39%; 재연결 없는 종료 성공.
깨끗한 포화2회 용량 오차20.65%/19.74%로 첫 run 기준 초과.
B2 연속300Mb/s 요청 경쟁2회 관측 coverage 중앙91.3%, 계산 가능63.74/77.17%.
보류는 하향 PHY 교정 범위 이탈; 첫 캡처1201/1081/961Mb/s를 실제 읽었고
unknown PHY body0이었다. 관측 결측과 모델 적용 범위 문제를 구분한다.
DDS Fast/Cyclone 각120/120, 정상 구간 계산73.33/100%; 실제 runtime 해시 확인.
절전on→monitor off→종료on 전환 시험은 ping 성공·SSH 접속 시간 초과,
유선 NM 재연결로 복구. 종료 안정성 실패를 유지한다.
C2는10번 root AP전환 helper 미준비로 사용자 퇴근 제약에 따라 건너뛰었다.
56개 단위검사 통과. 네 장비 최종 설정 복원과 기존4/5 연구DDS 해시 일치 확인.
최종 IPv4 감사에서5 접속 불안정이 발생해 기존 Wi-Fi IPv6 link-local SSH로
4/5를 검사했다. 추가 root/인증 권한 없이 완료; IPv4 문제 자체는 미해결.
Sender-only validated=false와 Receiver-assisted를 유지한다. 자동제어 미승인.
보고서: W1 Sender-only 입력 충분성·안정성 검증_261013.html.

#### Sender-only 두 위치 PHY 교정 및 독립 재검증 (2026-10-14)

원자료 `runs/w1_20261014_sender_multiphy`. 두 위치의 UDP50/150/포화 및
DDS2개를 교정 자료로만 사용해 계수와 PHY 범위를 고정한 뒤9개 조건을 새로
검증했다. 추가 물리 이동은 불가했고 bitrate mask는 드라이버가-95로 거부했다.
TX power, 커널 모듈, Receiver-assisted, 기존 연구 DDS는 변경하지 않았다.
새 상향 입력은 같은 창의 byte/retry 가중 조화 평균. 명시된 OFDM ARP PHY는
읽되 알 수 없는 HE/HT/VHT와 CRC 실패는 승격하지 않는다.

직접 CRC-valid relay 관측 모델은 유지했다. 별도 송신 station byte 보존 후보는
관측 PHY/BlockAck 샘플을 요구하며 source station bytes/downPHY로 중계
직렬화 항만 대체한다. sole-source와 byte conservation 가정을 명시했다.
교정 C0=339.726891Mb/s, 유효 상향706.187~961.7, 하향1175.864~1201.980Mb/s.
대칭 O=2.350554us는 조건부 운용 비용이며 물리 독립 식별 결과가 아니다.

held-out 자기 부하0.2/0.5/0.8 계산 가용성21.98/20.88/0%, clean 포화1.08%,
B2 포화0%, C2 자기 부하25.81%/포화0%. 범위 이탈과 하향 샘플 부족을
보존했고 검증 자료로 범위를 넓히거나 계수를 다시 맞추지 않았다.
B2/C2 경쟁12→10은 실제 다른/같은AP 배치를 확인해 요청300Mb/s70초 실행.
clean/B2/C2 포화 실제 payload298.952/182.815/205.552Mb/s.
B2/C2 유효 추정0창이므로 예측 오차를 승인할 수 없다.
DDS Static 고정 런타임은 Fast122/122, Cyclone실제83/83(계획122).
Cyclone deadline으로39개 미시도, publish 최대5457.435ms; 오류/수신 손실 아님.
DDS 계산 가용성42.22/8.51%. 9개 모두95% 입력 기준 미통과, validated=false.
실제 HTB 자동제어는 실행하지 않았다. 60개 unittest 통과.

상태 승계 절전on SSH 실패는 재현됐다. 새 연결 준비 무부하6회/부하3회,
독립 UDP7개 종료 ping/SSH는 성공. 최종 절전on 복원 시IPv4/IPv6 SSH 실패가
다시 발생했고 유선으로 절전off만 적용하자 SSH 복구; AX 새 연결+절전on 후
IPv4/IPv6 모두 성공했다. 영구 원인 해결로 주장하지 않는다.
최종4/5 절전on·CPUpowersave·버퍼212992·noqueue 복원, 임시50.1/50.2·monitor·
프로세스·실험 inhibit 제거.12/10 SR2 복귀와 임시 AX 프로파일 제거 확인.
기존 연구 DDS와 모듈 해시 일치, 네 장비 최종 감사 모두 통과.
보고서: `W1 Sender-only PHY·접속·C2 재검증_261014.html`.

#### 송신 호스트 RTPS 관측과 결측 대응 후보 (2026-10-14)

추가 Wi-Fi 장치 없음에 따라 `rospacer/sender_protocol.py`를 새로 구현했다.
일반 managed 송신 인터페이스의 DATA_FRAG와 자연 DDS ACKNACK/NACK_FRAG를
읽는다. 사용자 정의 수신 통계 피드백/monitor/Receiver-assisted 입력은 사용하지
않지만 자연 reader 피드백을 허용하는 입력 계약 변경이다. 원래 wireless-only
beta/theta/PHY/aggregation 모델의 관측 충분성 해결로 취급하지 않는다.
기존 Receiver-assisted와 무선 sender_radio.py는 유지했다.

원자료 `runs/w1_20261014_sender_bounded`. Static XML·고정 DDS 런타임으로
4→AX→5, 1MiB RELIABLE KEEP_ALL VOLATILE, 4/20Hz20초의9회 유한 시험.
v1 개발1회, 사전 고정 v2 검증6회, v2 꼬리 문제 수정 후 사전 고정 v3 새2회다.
전9회 발신 순번100% 관측·캡처drop0·scope error없음·거짓 완료확인0개.
실제 라이브러리 closure해시 일치, 종료 Wi-Fi SSH9회 성공.
수신 앱 순번은 종료 후에만 대조하며 온라인 입력으로 쓰지 않았다.

Fast v2 mask79/80·load399/400 및 v3 새mask79/80·load399/400 누적 확인.
실제 앱 수신은각80/80·400/400이고 마지막1개는미확정으로 유지했다.
나머지실행은관측/확인/수신집합일치. 사전95%비율게이트와100%정확일치
검사를별도로기록하며,확인비율만으로자동제어를승인하지않는다.
v2 종료후꼬리때문의과도감소를원자료에보존했다. v3는단일마지막표본이
ACKbase와같고missing/최근NACK가없으면보류한다. v3 mask입력가림구간
감소23회,두v3시험종료후backoff0회. 꼬리를수신성공/혼잡없음으로승격하지
않는다. 단일실제손실도보류될수있으므로완전한손실탐지보장이아니다.

200ms shadow권고만생성, HTB는설치하지않았다. ACK lag는첫조각→ACK시간이며
종단콜백지연아님; ACK창바이트율은확인진행률이며링크용량아님.
이후보의B2/C2·동적경쟁·장기결측·liveHTB성능비교는이번에수행하지않았다.
원래무선-only Sender-only 및자동제어승인은계속보류한다.

74개unittest통과.4/5원래절전on·CPUpowersave·버퍼212992·noqueue복원,
임시관리IP·실험프로세스·소유감시/억제기제거,연구DDS/모듈해시유지확인.
12/10과AP설정은변경하지않았다.소스스냅샷/버전별freeze/pcap/CSV/해시보존.
보고서: `W1 송신 측 프로토콜 관측·결측 대응_261014.html`.

#### ACK 실제HTB·B2/C2 및 최소 수신PHY 보정 (2026-10-14)

원자료 `runs/w1_20261014_ack_live`. 수신5에새통계프로그램을추가하지않는
배치요구를유지했다.송신4의ACK관측기와유한HTB실험경로를구현하고4→AX→5,
12→SR2→10 B2 /12→AX→10 C2,각DDS의Fixed대ACK를측정했다.
1MiB RELIABLE KEEP_ALL VOLATILE,Static XML,30Hz30초900개요청,경쟁UDP300Mb/s
요청90초.실제발행/경쟁률과수신을분리해기록한다.수신순번은사후참조만사용.

초기Cyclone B2는1346B송신복합RTPS를320B로잘라뒤제어헤더를놓쳐확인0으로
보류됐다.전체MTU를해석·제어원자료를보존하도록보강하고새B2재시험을수행했다.
최종ACK B2 Fast345/345,Cyclone416/416;C2 Fast346/346,Cyclone238/238 확인/수신.
최종4조건관측순번100%,거짓확인0,캡처drop0,scope error없음.초기실패는보존.
경쟁미성립C2 Cyclone848/848는제어효과/성능비교에서제외했다.

B2 두DDS와최종C2 Fast는상한변경0회. C2 Cyclone는116회변경했지만Fixed393개
대ACK238개로발행량이줄었다.입력정확도와적응성능을동일시하지않는다.
가림증명시험은91회실제변경·220/300개발행/220개수신으로부하감소를보존한다.
단일쌍·실제경쟁률차이·무변경조건의처리량차이를정식개선율로인용하지않는다.

대안`peer_phy.py`/`apply-peer-phy`는표준iw수신PHY1200.9Mb/s를교정파일로받고
운용중수신통계daemon을요구하지않는다.원래모델의교정입력연결과범위gate를
구현했다.첫source-only 패킷당중계비용후보는새clean 잔차-0.06~-0.09로실패했다.
`minphy_radio.py` v2는송신TX시간·상/하향PHY비율·재시도및같은창의가중조화평균
상향PHY를사용한다.원교정자료만으로계수를고정하고새3조건을독립검증했다.
예산예측오차clean9.982%,B2 2.918%,C2 1.628%,각계산가능100%.원식의TX<=busy는
강제하지않고현재MT7921의raw busy 자기TX제외계약을명시한다.

clean 점유율잔차중앙0.103/p95절대값0.117로자기/다른트래픽분해는미완료다.
잔차를물리beta_oth로확정하지않는다.유효중계/서비스비용은조건부운용계수이며
PPDU airtime/intrinsic O 식별이아니다.용량예산gate와원래점유율gate를구분한다.

`minphy_live.py`는해시일치·예산gate·명시적experimental flag가있는유한실험만
허용한다.수신PHY는고정교정값,운용중입력은송신통계뿐이다.새C2 시운전에서
Fast690/690,Cyclone850/850수신(각900개계획),계산305/315회,실제HTB187/197회
변경,정상구간계산100%,fq drop0.최소보정의현재장비예비동작근거이며
Receiver-assisted 대체성능·전체W1·원래무선-only 모델승인으로승격하지않는다.

84개unittest통과.주소/권한/경쟁TCP시작/SSH실패를원자료에보존하고미성립조건을
제외했다.4/5관리에는IPv6+임시유선,SR2관리에는기존IPv6 link-local을사용했다.
최종네장비모든복원감사통과:4/5원래절전on·CPUpowersave·버퍼212992·noqueue,
임시관리주소/실험프로세스/감시·억제기제거,12/10 SR2와원래버퍼복귀·임시AX
프로파일제거.기존연구DDS와모듈해시유지.Receiver-assisted 기존경로는보존한다.
보고서: `W1 ACK 기반 Sender-only B2·C2 검증_261014.html`.

#### 2026-10-14 송신 측 단독 교정·제어 W1 통합

`sender-calibrate`, `sender-validate`, `sender-govern`을 송신 패키지에 통합했다.
4번에 /home/csilab/.local/bin/rospacer 설치, 계수 계산·RTT 측정·Static XML 생성·HTB
제어 모두4번 실행이다. 수신에는 새 ROSPacer/통계 에이전트를 설치하지 않았으며 기존
SSH/iw/iperf3만 교정에 사용한다. 수신의 제한된 교정 공개키는 유지하고 임시 측정 키는 제거했다.
실험 하네스도4번에서 실행, 수신5번은 기존 traffic.py subscriber만 사용했다.

최초242.509Mb/s 교정은B2 오차37.30%로 실패했다. 기본버퍼·수신 절전조건 자료를 보존했다.
양쪽절전off/CPU performance, 커널버퍼상한4MiB, UDP소켓1MiB로 사전조건을 통일한 새
교정348.909Mb/s와 실제RTT19.580ms로 계수를 고정했다. 새Clean/B2/C2 오차는
13.6754%/2.2268%/5.0752%, 계산가능100%, 검증후재교정 없음. C2 두 실패는TCP
제어연결에서 데이터 미시작; 리슨상태확인 보강 뒤 r1을 새로 수행해 기록했다. 같은
수정모델의 하향=상향 입력도 세조건에서20%안이므로 수신PHY 필요성을 단정하지 않는다.
원TX<=busy 식 전체의 조건부 도입 절차를 소급완료했다고 주장하지 않는다.

C2 실제비교는15초/30Hz/계획450개, 두역순반복, Static/Fixed/Adaptive, 두DDS로12회다.
모든실행 실제라이브러리 경로/해시 고정closure와일치. 발행한메시지는전부수신되었으나
요청450개대비실제발행량을 보존한다. Cyclone Adaptive133/139, Fixed213/204,
Static219/209개로 적응형처리량/지터우위가없었다. Fast는반복변동이크다.
모든Adaptive 정상발행구간계산100%, 실제HTB124/140/122/122회변경, 모든HTB실행fqdrop0.
예측게이트통과는DDS성능우위가아니다. W2 E/F/정식통계비교, 물리점유율분해는미완료다.

실제SIGTERM과SIGKILL만료복원, 실패검증으로시작거부를확인했다.89개검사통과.
네장비noqueue/버퍼212992/임시프로세스없음,4/5절전·CPU·연구DDS보존,
12/10원래SR2프로파일복원모두true. 유선관리주소를추가하지않았다.
원자료 runs/w1_20261014_sender_integrated, 신규HTML W1 송신 측 단독 교정·제어 통합 검증_261014.html.


#### 2026-10-15 W2 케이스 격리 실패 정책

사용자 지시에 따라 연속 운영 실패 3회 전체 중단을 제거했다. 각 케이스 최대 2회 시도 후 네 장비 환경 복구 확인 시 skipped_failed로 보존하고 다음 케이스로 진행한다. 정상 측정에 집계하지 않으며, 낮은 성능은 재시도하지 않는다. 프로세스·SSID/MAC·noqueue·커널 기준값·guard 생존 확인이 두 차례 정리 뒤에도 실패할 때만 공유 환경 보호 중단한다. 모든 시도의 case_isolation.json과 attempts.json을 보존한다.

현재 시도 완료 후 안전 경계에서 복원·재준비하여 12:29 KST PID 41728로 재개했다. 정상 36건·범위 보류 6건을 유지한다. 새 guard session_policy 네 대 준비 완료, 실제 환경 감사 모두 통과. 실험 프로토콜·교정값·기존 원자료는 유지했다. 진입점 시뮬레이션에서 3개 케이스 연속 실패 후 다음 실행, 공통 환경 실패 시 복원·중단, 나쁜 성능 측정의 유지가 통과했다.

12:32 KST 실측 확인: 새 정책의 첫 T1 F Fast DDS Adaptive r1은 1508/1508 수신, measured. 종료 후 네 장비 case_isolation 감사 모두 true, failure_policy_action=continue. 유효 측정 37건으로 증가했다. 전체 unittest 106개 통과.


#### 2026-10-15 22:22 W2 3회 배치 종료

finished_with_skipped_cases, pending=0. measured198(T1 E 원본33+새165), T3 Adaptive blocked_scope6, Cyclone Static−F4 XML ns0 기동 오류 skipped_failed3. 네 장비 guard 복원 모두 성공, noqueue·errors[] 확인, PC runner 종료. 새 최종 HTML W2 실험 최종 결과 보고서_261015.html 및 runs/w2_20261015_resume1/final_analysis_261015/analysis.json 생성. 결과 입력 해시·원자료 불변 검증. T1/F·P0 Static 개선 관측, Fixed/Adaptive Static 대비 종합 우위 없음. T3 지연108개 쌍 검증 미충족·기존 도착구간 처리량/Jain 제외. D3 지연 회복과 미수신·미회복을 분리 보고. 연구 전체/5회 반복/Drain Control 완료로 승격하지 않음.
