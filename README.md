# ROSPacer 1.0

**기준일: 2026-10-15 · 패키지 버전: `1.0.0` · 백업 태그: `v1.0`**

ROS 2 대용량 DDS 통신을 Wi-Fi 환경에 맞추는 **정적 DDS 설정 생성기와 송신 측 페이싱 제어기**입니다. 이 버전은 W1 구현과 W2 3회 반복 실험을 마친 뒤, 추가 수정·최적화 전에 보존한 연구 스냅샷입니다.

> **현재 결론:** Static의 개선 효과는 여러 조건에서 관측됐습니다. Fixed·Adaptive의 Static 대비 종합 성능 우위는 확인되지 않았습니다. Adaptive가 실제 HTB 상한을 바꾸는 동작은 검증했지만, 전체 Drain Control·완전 전달·보편 물리 airtime 모델·다중 수신자 Adaptive를 완성했다고 주장하지 않습니다.

- 대상 환경: **Ubuntu 22.04 / ROS 2 Humble**.
- 우선 검증 미들웨어: **Fast DDS 2.6.11 / CycloneDDS 0.10.5**.
- `1.0`은 이 연구 백업의 버전명입니다. 기능별 검증 범위는 아래를 확인합니다.
- 기존 GitHub 구현의 후속 버전입니다. 별개의 프로젝트가 아니므로 `past/version0`로 옮기지 않고 Git 이력을 유지했습니다.
- 이전 작업 README는 [이력 문서](docs/history/README_before_W2_backup_20261015.md)에 보존했습니다. 그 문서의 초기 상태 설명은 현재 상태를 대신하지 않습니다.

버전 변경과 이전 원격 상태의 비교는 [1.0 보관 기록](docs/releases/ROSPacer-1.0-20261015.md)에 정리했습니다.

## 문서와 실험 결과

| 문서 | 내용 |
|---|---|
| [W2 최종 결과 HTML](docs/reports/W2_final_20261015.html) | 조건·정의·모든 비교군·단계별 제어·실패·복원. 저장소를 내려받아 브라우저로 열 수 있는 보관본 |
| [W2 동결 근거](reference/w2-20261015/README.md) | 207개 판정, 원본 집계 JSON, 실행별 요약, 소스 스냅샷과 체크섬 |
| [송신 측 최소 PHY 교정](docs/sender-local-minphy.md) | 현재 W2 Adaptive 경로의 설치 범위·교정·검증·실행 계약 |
| [송신 측 수동 관측 후보](docs/sender-only-prototype.md) | 초기 monitor 기반 후보와 관측 불충분 조건 |
| [DDS 피드백 관측 후보](docs/sender-protocol-observation.md) | ACKNACK/NACK_FRAG 후보. W2 최소 PHY 제어기와 구분 |
| [구현·실험 이력](STATUS.md) | 당시 관측·실패·복원 기록. 날짜별 기록이므로 최신 판정과 구분 |
| [실행 계획](EXECUTION_PLAN.md) | 단계·측정 지표·자동 실험의 실패 격리 정책 |
| [제3자 고지](THIRD_PARTY_NOTICES.md) | 포함한 벤더 XSD의 출처와 라이선스 |

## 1. 구성과 비교군

```text
메시지 크기·발행률·수신자 수·C0·RTT
                  │
                  ▼
       Static 설정 생성기 ───► 양쪽 DDS XML / 커널 설정 제안
                                      │
ROS Publisher ─► DDS ─► UDP 소켓 ─► HTB 상한 ─► fq ─► Wi-Fi / AP ─► Subscriber
                                      ▲
           송신 측 무선 통계 ─► 상한 추정·갱신
```

ROSPacer는 새 RMW나 메시지 중계 노드가 아닙니다. DDS 소스를 바꾸는 대신 벤더 XML과 송신 호스트의 Linux traffic control을 사용합니다.

| 이름 | 의미 |
|---|---|
| Default | 기본 DDS 동작 중심. 공통 QoS·Wi-Fi 인터페이스·발견·메모리 할당 정책은 적용한 시험 기준군 |
| Vendor | Fast: TCP와 큰 버퍼. Cyclone: 큰 버퍼와 권장 커널 조각화 설정 |
| Vendor-FC | Fast 전용. TCP 비교군에 비동기 발행·고정 FlowController 예산 추가 |
| **Static** | 메시지 크기·발행률·수신자 수·C0·RTT로 계산한 DDS 정적 XML. 외부 HTB 없음 |
| **Fixed** | Static + HTB/fq 고정 상한. 무선 상태에 따라 상한을 바꾸지 않음 |
| **Adaptive** | Static + 교정된 운용 모델로 약 200 ms마다 HTB 상한 갱신 |

Static은 sweep의 최고 성능 행을 복사한 설정이 아니라 모델 입력으로 계산한 설정입니다. 생성기는 전송 단위·피드백·보관량·버퍼·상한 등을 계산하며, 개별 설정의 기여는 별도 ablation으로 평가해야 합니다.

### 현재 Adaptive의 입력 계약

W2에서 사용한 것은 **초기 수신 PHY 교정 후 실행 중 송신 측만 관측하는 최소 PHY 교정 모델**입니다. ACKNACK 제어 후보와 다릅니다.

1. `sender-calibrate`: 송신 호스트에서 교정·계수 계산·RTT 측정·파일 생성을 수행합니다. 교정 중에는 기존 SSH/`iw`/`iperf3`로 수신 단말의 PHY와 참조 처리량을 얻습니다.
2. `sender-validate`: 계수를 고정한 뒤 독립 조건에서 예측 오차와 계산 가능 비율을 확인합니다.
3. `sender-govern`: 실행 중 수신 SSH나 통계 피드백을 사용하지 않습니다. 송신 측 `active/busy/TX`, 바이트·패킷·재시도·PHY와 교정 파일로 HTB를 제어합니다.

**수신 단말에 ROSPacer나 상시 통계 피드백 에이전트를 설치하지 않습니다.** 수신 단말에는 DDS 응용과 교정에 사용할 기존 표준 도구·SSH가 필요합니다. 수신 DDS XML과 커널 버퍼까지 기본값을 유지한다는 뜻은 아니며, 이번 성능 비교에서는 양쪽 설정을 적용했습니다.

현재 검증 범위는 MT7921 계열의 확인한 드라이버 통계, 채널 149/80 MHz, 고정 AP와 단일 수신자입니다. 수신 위치·PHY 조건 변경은 재교정 대상이며, 최초 교정까지 포함하는 엄밀한 순수 Sender-only 또는 물리적 전체 airtime 추정이라고 부르지 않습니다. 기존 Receiver-assisted와 관측 후보 코드는 연구 이력을 위해 유지합니다.

## 2. 설치와 하드웨어 없는 확인

일반 Python 모델·프로파일 생성·검사는 ROS 노드 실행 없이 사용할 수 있습니다. ROS 송수신과 qdisc 실험은 Linux 및 해당 ROS/DDS 환경이 별도로 필요합니다.

```bash
git clone https://github.com/taehun25/ROSPacer.git
cd ROSPacer
git checkout v1.0

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[validation]'

python -m rospacer --version
python -m rospacer --help
python -m unittest discover -s tests -v
python tools/verify_w2_backup.py
```

`--version`은 `1.0.0`입니다. 백업 직전 로컬 검사 106개가 통과했습니다. 일부 실행기 검사는 Windows 전용이며 Linux에서는 건너뜁니다. 이 검사가 실제 Wi-Fi/ROS/성능 검증을 대체하지는 않습니다. GitHub Actions는 Python 3.10 / Ubuntu 22.04에서 CLI와 모델·XML 검사를 실행하도록 구성했습니다.

### 정적 XML 생성 예

다음은 **설명용 입력값**이며 W2의 실측 최적 설정을 뜻하지 않습니다. 주소와 인터페이스는 실제 배치에 맞게 바꿉니다.

```bash
python -m rospacer plan \
  --rmw fastdds --payload 1MiB --rate 20 --readers 1 \
  --share 200Mbps --rtt 20ms --tau 1s \
  --dev wlp2s0 --address 192.168.0.4 --peer 192.168.0.5 \
  --out profiles/fastdds

# Cyclone은 --rmw cyclonedds와 별도 출력 폴더를 사용합니다.
python -m rospacer validate \
  --xml profiles/fastdds/middleware.xml \
  --schema reference/fastdds-2.6.10-local-validation.xsd
```

생성 파일은 `middleware.xml`, `env.bash`, `sysctl.conf`, `governor.json`입니다. `plan`은 파일을 만들 뿐 DDS·sysctl·qdisc를 자동 적용하지 않습니다. XSD 통과와 설치된 DDS의 실제 XML 파서 통과는 별개입니다. 위 Fast 예제는 원본 XSD의 미정의 타입과 파서 대응을 보정한 로컬 검증용 사본을 사용합니다. 이를 수정 없는 2.6.11 공식 XSD 검증이라고 표시하지 않습니다. 정확한 차이는 `THIRD_PARTY_NOTICES.md`에 있습니다.

ROS 응용을 실행하는 같은 셸에서 `source profiles/fastdds/env.bash`를 실행해야 XML이 적용됩니다. 수신 쪽 XML은 수신 주소·역할에 맞춰 별도로 생성·적용합니다. 실행 중인 다른 프로세스의 설정을 governor가 자동으로 바꾸지 않습니다. `golden`은 링크를 측정하지 않은 배치용 프로파일이며 용량·복구 보장을 생성하지 않습니다.

### Fixed 실행 예

```bash
mkdir -p runs/fixed-demo
sudo .venv/bin/python -m rospacer govern \
  --config profiles/fastdds/governor.json --mode fixed \
  --seconds 60 --trace runs/fixed-demo/govern.csv
```

HTB/fq 변경에는 권한이 필요합니다. 이 예는 기존 root qdisc를 덮어쓰는 설치 명령이 아닙니다. 제어기는 자기 소유 qdisc를 구분하고 기존 사용자 qdisc가 있으면 시작을 거부합니다.

### 교정·독립 검증·Adaptive 실행 예

아래는 검증 범위에 맞는 장비에서 사용하는 명시적 예시입니다. `<...>` 인자는 실제 배치 값으로 바꿔야 합니다. 수신 호스트의 기존 SSH 호스트키·인증과 `iw`·`iperf3`가 준비돼 있어야 합니다. ROSPacer 자체가 일반 root 권한이나 SSH 인증을 새로 부여하지는 않습니다.

```bash
sudo .venv/bin/python -m rospacer sender-calibrate \
  --dev wlp2s0 --source 192.168.0.4 --peer 192.168.0.5 \
  --peer-ssh '<user>@192.168.0.5' \
  --ssh-key '<private-key-path>' --known-hosts '<known-hosts-path>' \
  --host-key-alias 192.168.0.5 \
  --socket-bytes 1048576 --rmw fastdds --hz 30 \
  --out runs/calibration-demo

sudo .venv/bin/python -m rospacer sender-validate \
  --dev wlp2s0 --source 192.168.0.4 --peer 192.168.0.5 \
  --peer-ssh '<user>@192.168.0.5' \
  --ssh-key '<private-key-path>' --known-hosts '<known-hosts-path>' \
  --host-key-alias 192.168.0.5 --socket-bytes 1048576 \
  --bundle runs/calibration-demo --condition Clean \
  --out runs/validation-clean-demo

sudo .venv/bin/python -m rospacer sender-govern \
  --bundle runs/calibration-demo \
  --validation runs/validation-clean-demo/validation.json \
  --mode adaptive --seconds 60 --out runs/adaptive-demo
```

소켓 1 MiB를 요청하는 예시이므로 충분한 커널 상한이 필요합니다. 실제 W1/W2에서는 양쪽 버퍼·절전·CPU 조건을 준비하고 종료 시 복원했습니다.

독립 검증은 예측 오차 20% 이내·계산 가능 비율 95% 이상을 확인합니다. Clean만 전달한 실행이 B2/C2까지 승인한 것은 아닙니다. 조건별 검증 파일은 `--validation`을 반복해 전달합니다. 실패·결측을 0으로 채우지 않으며, 미적격 조건에서는 시작 거부 또는 상한 보류를 기록합니다. `sender-govern`은 유한 실험용으로 1회 최대 180초입니다. 자세한 내용은 [송신 측 문서](docs/sender-local-minphy.md)를 확인합니다.

## 3. HTB/fq와 지원 범위

```text
Wi-Fi root HTB 7ac0:
├── 7ac0:10  대상 RTPS의 합산 상한
│   └── fq 7ac1:  소켓별 큐, nopacing
└── 7ac0:20  관리 SSH/TCP·일반 UDP 등 bypass
```

현재 분류 대상은 지정 peer 또는 SPDP multicast로 보내며 UDP payload 첫 4바이트가 `RTPS`인 IPv4 패킷입니다. IPv4 헤더 20 B, IP 단편화 없음을 전제로 합니다. 같은 목적지의 다른 RTPS 흐름도 포함하며 ROS 토픽별 분류는 아닙니다. TCP Vendor군을 같은 HTB로 제어한 시험이 아닙니다. IPv6, IP option, DDS Security, VPN, 여러 토픽의 일반성은 검증하지 않았습니다.

T1 설계의 `fq flow_limit=1490`과 전체 `limit=5960`은 **패킷 개수**입니다. 바이트나 ROS 메시지 수가 아닙니다. Fixed의 고정 상한, Adaptive의 갱신 상한, 응용 goodput, PHY 속도는 서로 다른 양이므로 구분해 기록합니다. 종료·SIGTERM·독립 만료 감시의 복원 경로를 유지합니다.

## 4. W2 동결 결과 — 2026-10-15

종료 시각은 **2026-10-15 22:22:32 KST**입니다. 전체 207개 항목을 처리했으며 정상 측정 198건, T3 Adaptive 범위 보류 6건, Cyclone 소켓 버퍼 제거 조건의 XML 기동 오류 3건입니다. 네 장비 모두 복원 성공과 root qdisc `noqueue`가 기록됐습니다.

| 공통 조건 | 내용 |
|---|---|
| 데이터 | `std_msgs/msg/UInt8MultiArray`, 1 MiB 무작위 데이터, 순번·발행 시각 |
| QoS | RELIABLE·KEEP_ALL·VOLATILE |
| 시간 | 워밍업 10초, 본 측정 60초(F는 80초), drain 30초 |
| 비교군 | Default / Vendor / Static / Fixed / Adaptive, Fast는 Vendor-FC 추가 |
| 반복 | 각 3회. 표는 run 통계 중앙값이며 p99도 run별 p99의 중앙값 |
| T1 | 송신 4 → 수신 5 |
| T3 | 송신 4·5가 각각 수신 12·10에 복사. 수신 합계는 최대 발행 수의 두 배 |
| F | 같은 AP 경쟁 UDP를 20초씩 0 → 0.5C0 → 0.9C0 → 0 |
| P0 | 저부하, Clean, 같은 AP 경쟁 C2, 다른 AP 동채널 간섭 B2, 수신 무선 단절 D3, 버퍼 제거 비교 |

T1 E 33건은 원래 배치에서 유지했고, 보수 후 165건을 새로 측정했습니다. 이전 F/T3 결과와 섞지 않았습니다. W2의 T1 교정 C0는 368.750 Mb/s입니다.

| 조건·DDS | Static의 Default 대비 goodput | p99 지연 | 도착 간격 지터 p99 |
|---|---:|---:|---:|
| E·Fast | −0.4% | −14.3% | −22.6% |
| E·Cyclone | +41.8% | −15.2% | −28.9% |
| F·Fast | +8.4% | −9.5% | −20.0% |
| F·Cyclone | +70.9% | −41.1% | −50.5% |

- Static은 여러 조건에서 Default나 Vendor보다 나았지만 모든 조건·지표에서 항상 최선은 아닙니다. Fast Vendor는 E에서 Static보다 goodput가 높은 반복이 있었습니다.
- **Fixed/Adaptive의 Static 대비 종합 성능 우위는 확인되지 않았습니다.** F의 Static/Adaptive goodput는 Fast 188.95/150.78, Cyclone 225.44/180.98 Mb/s였습니다.
- Adaptive의 HTB 상한은 경쟁 때 내려가고 경쟁 종료 후 회복했습니다. 동작 확인과 성능 우위는 다릅니다. 3초 관측창·평활·큐/소켓/DDS 상호작용의 원인 분리가 남습니다.
- T3는 송수신 쌍 108개의 시계 기준이 모두 미충족이므로 종단 지연을 비교에서 제외합니다. 첫·마지막 콜백 구간율을 합산한 기존 goodput/Jain도 지속 링크 성능으로 사용하지 않습니다.
- D3는 회복 시간과 발행/수신 수를 함께 평가합니다. 지연이 낮아져도 관측 종료까지 미수신이 있는 run과 발행분을 수신했어도 지연 회복 기준을 충족하지 못한 run이 있었습니다.
- 현재 Static의 유효성을 보여 주는 탐색적 근거이며 전체 Drain Control, 보편 모델, 5회 반복, 95% 신뢰구간 결정 게이트의 완료를 뜻하지 않습니다.

결과와 정의는 [최종 HTML](docs/reports/W2_final_20261015.html)을 확인합니다. 전체 pcap·시계열 텔레메트리·설치 DDS 바이너리는 Git에 포함하지 않고 로컬 `runs/`에 유지합니다. 집계 JSON, 207개 요약, 당시 소스 tar와 SHA-256은 `reference/w2-20261015/`에 보관합니다.

## 5. 자동 실험 하네스와 실패 처리

`tools/w2_runner.py`, `w2_protocol.py`, `w2_traffic.py`, `w2_worker.py`는 W2 자동 실행기를 구성합니다. Windows 제어 PC에서 네 장비를 관리하고 Linux 계측·유한 작업·복원 감시를 조합합니다.

**연구실의 장비 ID·연결·준비된 campaign에 의존하는 하네스이며, clone 직후 다른 환경에서 바로 실행하는 범용 벤치가 아닙니다.** 준비·시운전·교정·T3/AP 전환 검증 마커와 세션 정보가 필요합니다. `tools/w2_*prepare/rearm/recover*.py`에는 당일 일회성 작업용 스크립트도 있으므로 기존 실험에 무조건 다시 실행하지 않습니다.

- 성립한 저성능 run은 결과로 유지하며 성능이 나쁘다는 이유로 재실행하지 않습니다.
- 케이스별 운영 실패는 최대 2회 시도한 뒤 환경 정상 확인 시 `skipped_failed`로 남기고 다음 케이스로 갑니다.
- 연속 3회 실패만으로 전체를 중단하던 이전 조건은 제거했습니다.
- 잔류 프로세스, MAC/SSID, `noqueue`, 커널 기준값, 준비 감시 생존을 확인합니다. 두 차례 정리 후에도 공통 환경을 확인할 수 없으면 중단·복원합니다.
- `blocked_scope`는 입력 모델의 미적격 범위이며 성공이나 0처리량으로 바꾸지 않습니다.
- 각 시도·실패·`case_isolation.json`·복원 기록을 보존합니다.

## 6. 디렉터리 구성

```text
rospacer/                  모델·XML·Linux shaper·교정/검증/제어·관측 후보
  model.py                 정적 설정 계산
  profiles.py              Fast/Cyclone XML 및 XSD 검증
  linux.py                 HTB/fq 소유권·분류·복원
  sender_minphy.py          현재 sender-calibrate/validate/govern
  minphy_radio.py           유효 비용을 쓰는 제한된 운용 모델
  sender_protocol.py       DDS 피드백 관측 후보
  sender_ack_live.py       ACK 기반 유한 제어 후보와 복원 감시
  sender_radio.py           송신 측 monitor 관측 후보
  native_radio.py          이전 Receiver-assisted 진단 경로
  metrics.py, clock.py     지표와 시계 게이트
examples/                  설명용 생성 설정(실측 최적값 아님)
tools/                     W1/W2 계측·분석·배포·복원·보고서 도구
tests/                     하드웨어 없는 검사
docs/                      입력 계약·이전 README·이동 가능한 결과 HTML
reference/                 벤더 XSD·라이선스·동결 W1/W2 근거
.github/workflows/         CLI·모델·XML CI
runs/, profiles/, tmp/     로컬 생성물. Git 제외
```

보고서 생성기는 원래 `runs/`를 입력으로 사용합니다. Git의 요약 근거만으로 전체 pcap·측정 로그를 복원할 수는 없습니다. `archive_w2_backup_20261015.py`도 원래 연구 PC의 완료 campaign으로부터 보관본을 만드는 도구입니다. `verify_w2_backup.py`는 Git에 포함된 파일만으로 검증할 수 있습니다.

## 7. 후속 작업

1. 페이싱 자체의 비용과 추정기의 비용을 분리하는 소규모 검증.
2. Cyclone 버퍼 제거 XML 보수·실제 런타임 확인·빠진 run 재측정.
3. T3 고정 측정창 집계와 필요한 시계 보완, D3 미수신·재발견·보관 동작 분석.
4. 핵심 비교의 추가 반복·신뢰구간으로 W2 페이싱 유지 여부 판정.
5. 판정 후 Static 중심 또는 수정 Adaptive의 적절한 W3 확장. Zenoh는 후속 범위.

이 최적화·기능 변경을 넣기 전의 상태가 이번 **ROSPacer 1.0 / `v1.0` / 2026-10-15**입니다.

## 라이선스

ROSPacer 자체 코드의 배포 라이선스는 아직 지정하지 않았습니다. `reference/`의 벤더 자료는 각 원본 저작권·라이선스를 따릅니다. Fast DDS/CycloneDDS 라이브러리를 ROSPacer 자체 구현으로 배포하지 않습니다. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 확인합니다.
