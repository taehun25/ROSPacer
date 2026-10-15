# 송신 측 최소 PHY 교정 W1 통합

ROSPacer 패키지는 송신 호스트에만 필요하다. `sender-calibrate`가 송신 호스트에서
표준 SSH로 수신 호스트의 기존 `iw`와 유한 `iperf3` 서버를 실행하고, 송신 무선
통계와 교정 처리량으로 계수를 계산한다. RTT는 송신 Wi-Fi의 ping으로 측정한다.
수신 호스트에는 ROSPacer나 통계 피드백 프로그램을 설치하지 않는다. 표준 도구와
SSH 인증은 사전에 있어야 한다. 수신 PHY/UDP 참조 정보는 교정·검증에만 사용된다.

이번 송신4번에는 `/home/csilab/.local/bin/rospacer` 실행기를 설치했다. sudo의 PATH에
사용자 실행 경로가 없으면 `sudo /home/csilab/.local/bin/rospacer ...`로 실행한다.
Ubuntu의 기존 setuptools59 환경에서 인터넷 의존 없이 설치한 로컬 소스 실행기다.
송신 측에만 ROSPacer를 설치한다는 뜻은 수신 DDS 설정까지 무조건 기본값이라는 뜻이
아니다. 이번 성능 비교는 양쪽에 같은 계산 근거의 Static XML과 충분한 커널 버퍼를
적용한 시험이다. 수신 기본 XML/버퍼로 같은 성능을 보장한 시험은 아니다.

```
sudo rospacer sender-calibrate --dev wlp2s0 --source 192.168.0.4 \
  --peer 192.168.0.5 --peer-ssh csi@192.168.0.5 \
  --ssh-key /home/csilab/.ssh/id_ed25519_rospacer_cal \
  --known-hosts /home/csilab/.ssh/rospacer_cal_known_hosts \
  --host-key-alias 192.168.0.5 --out ./calibration --rmw fastdds --hz 30

sudo rospacer sender-validate --dev wlp2s0 --source 192.168.0.4 \
  --peer 192.168.0.5 --peer-ssh csi@192.168.0.5 \
  --ssh-key /home/csilab/.ssh/id_ed25519_rospacer_cal \
  --known-hosts /home/csilab/.ssh/rospacer_cal_known_hosts \
  --host-key-alias 192.168.0.5 --bundle ./calibration \
  --condition Clean --out ./validation-clean

sudo rospacer sender-govern --bundle ./calibration \
  --validation ./validation-clean/validation.json --out ./live --seconds 60
```

현재는 MT7921/channel149/80MHz, 단일 IPv4 수신자에 한정한 W1 프로토타입이다.
예시 주소·계정·인터페이스는 실제 배치에 맞춰 지정한다. 엄격한 SSH 호스트키 검사를
끄지 않는다. 수신 측 SSH 권한은 기존 iw와 제한된 시간/포트의 iperf 서버로 제한할
수 있다. 교정에 다른 실험이나 경쟁 부하가 섞이면 안 된다. iperf는 1400B UDP를
사용한다. 적용할 DDS는 생성된 XML의 정적 설정을 사용하는 별도 ROS 응용이다.

`sender-govern`에는 SSH 계정·키·수신 통계 입력이 없다. 로컬 active/busy/TX,
송신 바이트·패킷·재시도·PHY 및 고정 교정 파일만 사용한다. HTB/fq를 소유하고,
종료/SIGTERM과 독립 만료 감시에서 자신이 설치한 qdisc만 제거한다. 기존 root
qdisc가 있으면 보존하고 실행을 거부한다. sysctl/CPU/절전 설정은 이 제어 명령에서
변경하지 않는다. finite W1 실행은 최대 180초이며 기존 receiver-assisted는 유지한다.

## 검증과 범위

새 데이터에서 예측 오차 <=20%, 계산 가능 비율 >=95%를 검사한다. 동일한 고정
프로파일에서 하향 PHY만 상향 PHY로 바꾼 입력 비교를 별도로 기록한다. 이 비교는
수정 운용 모델에서 교정 입력의 필요성을 분리하며, 원래 TX<=busy 식 전체의 검증이
아니다. 계산 불가는 수치 오차20% 초과로 바꾸지 않는다. 검증 뒤 계수를 재조정하지 않는다.

교정 기본 UDP 소켓 요청은128KiB다. 통일한 W1 측정에는 `--socket-bytes 1048576`을
사용했고, 양쪽의 커널 rmem/wmem_max4MiB·절전off·CPU performance를 사전 준비했다.
소켓 요청1MiB를 선택할 때 해당 커널 상한이 필요하다. 이 설정을 제어기가 수신 측에서
상시 변경하는 것은 아니다. 실험 준비 설정은 종료/만료 시 원상복구한다.

교정 번들의 `env.bash`는 ROS 응용을 시작하는 **같은 셸**에서 source해야 생성 XML이
적용된다. `sender-govern`이 다른 프로세스의 DDS 설정을 자동으로 바꾸지는 않는다.
`sysctl.conf`는 필요한 커널 상한을 적은 적용 후보이며 교정 명령이 자동 적용하지 않는다.
기존 상한보다 낮추지 않고 사전 준비/복원 절차로 적용해야 한다. 이번 시운전은 별도의
유한 준비 감시 아래 양쪽4MiB 상한을 사용했고, 실제 로딩 DDS 라이브러리도 고정했다.

제어에는 최소 독립 Clean 통과가 필요하다. 추가로 전달한 B2/C2 검증 파일 중 하나라도
실패하면 제어 시작을 거부한다. 전달하지 않은 조건까지 승인되는 것은 아니다.
PHY 보정 잔차는 물리적 경쟁 점유율 beta_oth로 확정하지 않는다. 고정 하향 PHY가
변하는 수신 이동은 송신 측만으로 확실히 감지할 수 없으므로 운영자가 재교정해야 한다.
AP/채널/드라이버 변경은 시작 시 거부한다. 실행 중 결측·초기화는 상한 갱신을 보류한다.

`tools/w1_sender_local_smoke.py`는 송신 측에서 실행하는 별도 **실험 하네스**다.
수신 측의 이미 설치된 `tools/traffic.py` subscriber를 실행하고 종료 후 결과만 회수한다.
이는 ROSPacer 배치 의존성이나 실시간 수신 피드백이 아니다. 15초·두 반복 비교는 W1
시운전으로, 제안서 W2 E/F의 정식 통계적 성능 평가를 대체하지 않는다.
