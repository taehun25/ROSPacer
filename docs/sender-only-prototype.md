# 송신 측 수동 관측 프로토타입 · 2026-10-13

Receiver-assisted의 `adaptive` 경로는 유지한다. 새 `sender-observe`는 송신
노트북 한 대에서 survey/station, 임시 동채널 monitor, radiotap/MAC 정보를
수집하는 shadow 모드다. 수신측 통계, UDP55910 피드백, 수신측 PHY를 입력으로
사용하지 않는다. `adaptive-sender`는 같은 추정값으로 기존 HTB/fq를 갱신하는
실행 경로지만, 별도 송신 측 교정 프로파일이 `validated=true`일 때만 설치한다.
현재 실험 프로파일은 `validated=false`다.

## 관측과 분리

- AP→수신 MAC의 **데이터** radiotap HE 정보를 사용해 하향 PHY를 계산한다.
  송신 측 station의 AP ACK 수신 속도를 하향 데이터 속도로 대체하지 않는다.
- AP→송신 MAC BlockAck와 수신 MAC→AP BlockAck를 따로 센다. 후자는 하향 전송
  교환을 나타내는 관측 대리값이며 정확한 PPDU 수라고 가정하지 않는다.
- A-MSDU 표시, MAC 프레임 길이, 재전송 플래그와 시퀀스를 기록한다. 반복 수신은
  PHY 직렬화 비용에 포함하지만 전달 바이트 대리값에서는 중복을 제거한다.
- AMPDU reference가 공유되지 않으면 그것을 PPDU 분리 성공으로 바꾸지 않는다.
- 원송신자 Addr3가 보이는 비 A-MSDU 프레임은 자신의 중계와 다른 송신자를
  구분한다. **암호화된 A-MSDU 내부 원송신자는 보이지 않는다.** 현재 시험은
  수신 MAC의 대용량 트래픽이 해당 송신자에게서만 온다는 명시적 운영 가정을
  사용한다. 같은 수신자에게 여러 송신자가 데이터를 보내는 일반 상황은 미검증이다.

## 운영 추정식

`relay = k_upBA * N(AP→sender BA) + Σ(observed MAC bytes / downlink PHY)
+ k_downExchange * N(receiver→AP BA)`

`beta_raw = (sender busy - idle_fraction * active_delta - relay) / active_delta`

현재 MT7921 교정 계약에서는 자기 TX를 raw busy에서 다시 빼지 않는다.
교환 비용 계수는 source-local 교정의 회귀값이며 물리 BA duration이나 intrinsic
PPDU overhead가 아니다. 하향 PHY와 송신 PHY·재시도·조건부 비용을 사용해 패킷
바이트당 서비스 비용 theta를 계산한다. 상한은 `min(0.9*C0, 0.9*(1-beta)/theta)`이다.
기존 C0는 사전 UDP 처리량 측정값이며 현재 monitor를 켠 상태의 용량을 새로
확정한 값은 아니다. 조건부 O를 대칭으로 나누는 가정도 독립 물리 식별 결과가 아니다.

## 결측과 적용 범위

캡처 drop, 낮거나 과도한 중계 바이트 관측 비율, 알 수 없는 PHY, peer에서 다른
송신자 관측, 범위 밖 AP/channel/kernel/driver/reader/payload는 보류 또는 설치
거부다. raw beta는 0으로 교체하지 않는다. 캡처 drop이 있었던 창은 거부하고
완전히 깨끗한 새 창에서는 회복할 수 있다. 관측 비율은 송신 바이트 대비 보이는
중계 바이트의 대리값이며 수신 성공률이나 완전한 프레임 포착을 증명하지 않는다.

현재 범위: 4→AX1500→5, 149/80MHz, MT7921, HE SU 약1201Mb/s 하향,
1MiB DDS, RELIABLE/KEEP_ALL/VOLATILE. MU/RU/DCM/STBC 또는 알려지지 않은
HE 필드는 추정하지 않는다. 하향 PHY 변경과 B2/C2의 정식 성능 검증은 별도다.
송신 중 수신 불가 구간 및 송신자가 듣지 못하는 hidden-node 트래픽도 남는 한계다.

## 실행

```bash
sudo python3 -m rospacer sender-observe --config sender-config.json \
  --seconds 38 --trace sender.csv
```

`sender-config.json`에는 Static 생성기 설정에 `native_reader` 경로와
`sender_radio_calibration`을 추가한다. Receiver-assisted 설정을 덮어쓰지 않는다.
임시 rpmon을 만들고 관측 중 송신 측 Wi-Fi 절전을 끈다. 종료/SIGTERM 시
monitor를 제거하고 원래 절전 상태를 복원하며 기존 Wi-Fi 채널을 변경하지 않는다.
shadow는 HTB를 설치하거나 변경하지 않는다. 독립 프로파일이 검증된 후에만
`govern --mode adaptive-sender`로 HTB 갱신을 실행할 수 있다.

코드: `rospacer/sender_radio.py`; 측정: `tools/w1_sender_probe.py`,
`tools/w1_sender_analyze.py`, `tools/w1_sender_fit.py`, `tools/w1_sender_smoke.py`.
원자료: `runs/w1_20261013_sender_only/`. v1 실패와 v2 수정 기록을 모두 보존한다.

## 실제 확인 결과

교정에 쓰지 않은 70/140Mb/s 자기 부하의 beta raw는 +0.864%/-0.967%였다.
관측 중 송신 Wi-Fi 절전을 끈 1MiB Static DDS shadow에서 Fast는 76회,
Cyclone은 44회의 유효 추정과 각각120/120 수신을 확인했다. 이는 HTB 갱신
횟수가 아니다. 유효 창에서 beta는 Fast -0.161%~2.307%, Cyclone
-0.345%~0.950%였다. 나머지는 warm-up·발행 없는 창·가시성·PHY 등의 보류다.

별도 SR2 AP의12→10 연속300Mb/s 경쟁 진단(B2 topology)에서는 source busy가
68.81%였지만 source 송신 대비 중계 body 관측 비율이18.84%라 추정을 거부했다.
주 부하는100Mb/s 요청으로, 포화 최대 용량 측정이 아니다. 원 proposal의 B2
2초ON/2초OFF와 구분한다. 정식 B2/C2 예측 오차, 성능 비교, HTB 갱신 승인은
미완료다. 현재 자료로 일반 Sender-only가 불가능하다고 판정하지 않으며, 현재
수동 관측 경로의 충분성도 승인하지 않는다.

기록: `html 파일 모음/결과/W1 실험결과/W1 송신 측 수동 관측 프로토타입_261013.html`.

## 2026-10-13 B2 누락 진단 보강

`runs/w1_20261013_sender_gap/`에 유효6개 run과 실패 반복을 보존한다.
같은 라디오 monitor에 `fcsfail`을 추가했다. B2 한 창은 정상 CRC body
관측32.13%, CRC 오류 헤더/길이를 잠정 포함한 진단72.74%였고 하드웨어
dot11FCSErrorCount가3765 증가했다. 모든 유효 source 캡처는 kernel drop0이다.
이는 공중 프레임 포착 완전성을 뜻하지 않는다. source TX0 observer B2에도
정상68.73%/CRC 후보84.73%의 관측 부족이 남아 own-TX만으로 설명할 수 없다.

기존4·5 MAC 필터는 RA=AP만 있는 CTS를 제외했다. AP 관련 제어 프레임을
추가하고 CTS/ACK 뒤의 FCS/padding을 TA로 오인하지 않도록 수정했다.
CRC 정상 RTS/CTS의 timestamp 차이와 NAV 감소를 함께 검사해 후보를 기록한다.
새 B2에서 source RTS1046/receiver 오프라인 참조1165=89.79%의 개수 비율,
RTS-CTS1035/완결 BA 후보784를 얻었다. 정상 data body 관측은58.66%다.
정밀 동기화되지 않은 개수 비교를 정확한 물리 포착률로 읽지 않는다.
NAV와 RTS→BA timestamp 중앙값 차이99µs가 남아 airtime 입력으로 승인하지 않는다.

live sender CSV에 control_diagnostic, crc_diagnostic와 radio-wide FCS counter
delta/availability를 추가했다. 오류 CRC byte는 추정 coverage/serialization에
포함하지 않는다. 결측 카운터는0으로 만들지 않는다. 강화한 Fast/Cyclone
무경쟁 DDS shadow는 각각120/120수신, 유효 추정47/19회였다. HTB 변경 없음.
자동 검사52개 통과. 상세 결과/접속 실패/복원은 `W1 송신 관측 누락 진단_261013.html`.
새 계수 fitting이나 sender adaptive 승인은 수행하지 않았다. `validated=false` 유지.

## 참고

### 2026-10-14 두 위치 교정과 held-out 재검증

`runs/w1_20261014_sender_multiphy`의8개 교정 run만으로 두 후보를 고정했다.
원래 직접 중계 byte 관측 모델과 별도 source-station-byte-conservation-v1
후보를 구분한다. 후자는 송신 byte/downlink PHY로 serialization을 대체하며,
CRC-good MPDU≥128, body sampling0.25~1.1, peerBA≥32, 알려진PHY, capture drop0을
계속 요구한다. 수신MAC에 대용량 발신자가 하나라는 조건 및 사후 byte conservation
검증이 필요하다. 누락된 프레임이나 CRC 오류를 관측 성공으로 승격하지 않는다.
수신 통계는 오프라인 교정/검증에만 쓰며 온라인 피드백에는 사용하지 않는다.

상향 PHY는 같은 창의 byte·retry 가중 조화 평균으로 변경했다. OFDM RATE/CHANNEL
필드가 명시된 작은 ARP 프레임은 PHY를 읽되, 알 수 없는 HE를 RATE로 추측하지 않는다.
교정의 유효 범위는 상향706.187~961.7/하향1175.864~1201.980Mb/s로 좁았다.
비트율 강제 명령은 드라이버에서 거절됐고 추가 이동은 불가했다.
독립9조건의 입력 가용성이 모두95% 기준에 실패했다. B2/C2 포화는 유효 추정0창.
검증 이후 범위 확대나 계수 재교정 없이 두 프로파일 모두 validated=false 유지.
장비·PHY 범위 밖 Sender-only 불가능성을 증명한 결과는 아니며, 현 관측 경로의
연속성·적용 범위 부족에 대한 반증이다. 신뢰할 입력을 확보한 뒤 새 교정/새 검증이 필요하다.

새 연결 준비 단기 접속 시험은 통과했으나 최종 절전on 복원 후 SSH timeout이
재현됐다. 절전off로 원격 복구하고 AX 새 연결 후 원래 절전on까지 복원했다.
접속의 영구 원인을 해결했다고 부르지 않는다. Receiver-assisted와 연구 DDS는 유지한다.

## 원문 참고 링크

- https://docs.kernel.org/driver-api/80211/cfg80211.html
- https://wireless.docs.kernel.org/en/latest/en/developers/documentation/radiotap.html
- https://www.radiotap.org/fields/HE.html
- https://android.googlesource.com/kernel/common/+/refs/tags/android14-5.15-2024-05_r23/include/net/ieee80211_radiotap.h
