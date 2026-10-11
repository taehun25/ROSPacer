# 2026-10-10 구현 및 검증 기록

ROSPacer 0.1 초기 구현이다. proposal IV의 정적 설정 생성, HTB+fq 송신 제어,
sender 통계 수집 및 적응식 계산을 구현했다. 적응형 Wi-Fi 성능 검증은 완료하지 않았다.

## 배치

| 노트북 | 역할 | 계정·현재 IP | NIC 인터페이스·드라이버 |
|---|---|---|---|
| 12 (HP) | Publisher, governor 실행 | csi2@192.168.0.3 | wlo1, iwlwifi |
| 10 (Lenovo) | Subscriber, 수신 로그 | csi@192.168.0.4 | wlp2s0, rtw89_8852be |

두 호스트 모두 Ubuntu 22.04.5 / ROS 2 Humble, Cyclone DDS 소스 0.10.5.
Fast DDS apt 라이브러리는 12=2.6.10, 10=2.6.11이므로 정식 비교 전 통일이 필요하다.
현재 SR2는 36번, 80 MHz, center 5210 MHz다.
다른 공유기 쪽 4/5에는 이번 개발에서 접속·적용하지 않았다.

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
4. 10번 sudo를 사용해 필요한 수신 버퍼를 적용하고 실제 SO_RCVBUF 및 XML 적용을 확인한다.
   현재 csi 계정의 sudo -n은 비밀번호를 요구한다.
5. 실제 DDS 소켓만 분류하도록 traffic classifier를 검증한다.
   현재는 peer 방향의 IPv4 UDP 전체와 SPDP를 제어하므로 같은 peer의 iperf UDP까지 포함한다.
   정식 경쟁 트래픽 실험 전에 이를 해결해야 한다.
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

양쪽 Fast DDS 버전 차이와 10번 sudo 제한은 유지된다.
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
