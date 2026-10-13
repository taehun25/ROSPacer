# W1 무선 입력 검증: 2026-10-13

4→5 MT7921, Ubuntu22.04/Humble, 6.8.0-138, AX1500
BSSID b0:38:6c:7d:f5:74, 149번/80MHz, 1MiB에 한정한 운용 교정이다.
`mt7921-AX149-80-1MiB.json`은 이 범위의 native 입력 gate를 통과한 프로파일이다. 잘못된 AP는 qdisc 설치 전에 거부한다.
서명 survey 수정 드라이버의 srcversion과 native reader SHA도 고정한다.
기존 일반 입력 경로의 미승인 gate를 해제하는 프로파일이 아니다.

기존 TX<=busy 전제는 polling0/50/200/1000/2000ms, AP-only/relay 반복,
역방향에서 모두 반증됐다. raw busy에서 자기 TX를 다시 빼지 않는다.
AP 응답 BA와 수신 RX bytes/MPDU/AMPDU/AMPDU bytes, 수신 PHY로
자기 부하의 관측 busy를 교정한다. RX duration의 미갱신0은 사용하지 않는다.
RX byte coverage는 standalone MPDU 누락을 보정한다. 추정 PPDU 비용은
effective 운용 계수이며 물리적 프리앰블 자체의 시간이 아니다.

AP-only/idle과 relay 연속/묶음8조건만으로 교정하고 계수를 고정했다.
고정 후 재측정 DDS 자기 부하6조건은 rawβ=-0.243%..3.141%, |β|<=5%였다.
Fast 요청0.8C0에서는 예정478개 중418개 발행·418개 수신으로, 요청률 달성은 아니다.
새 B2 3회 용량오차8.698%..10.795%, 고정 후 새 C2 3회0.108%..2.953%로 <=20%였다.
처음 C2는 계수 고정 전에 수집되어 보조 자료로 남겼고, 최종 C2는 계수 고정 후 새3회다.
SR2 byte 정규화는 이전 경쟁 없는 quiet만 사용해 고정했고 새 C2에 다시 맞추지 않았다. AX 프로파일을 SR2에서 그대로
승인하지 않는다. 다른 AP/driver/payload/방향에는 재검증이 필요하다.

실제 govern adaptive native 분기와 유선 receiver feedback도 시험했다.
Fast/Cyclone 각120/120 수신, 최종 갱신154/106회, 중앙값200.50/200.51ms였다.
feedback을 먼저 종료해 각각51회 stale hold를 확인했고 qdisc를 noqueue로 복원했다.
hold는 마지막 유효 cap 유지다. 동적 경쟁 추종, drain, fixed 대비 성능은 후속 범위다.
AP→4 BA 참조12,959개에서24Mb/s·32µs, effective BA31.754µs와 약0.77% 차이를 확인했다.
HE duration/LTF 정보가 부족해 전체 HE/PPDU airtime과 intrinsic O는 독립 식별하지 못했다.
원 proposal 식 그대로의 W1 전체 승인이나 보편 adaptive 승인으로 인용하지 않는다.

원자료는 runs/w1_20261013_radio_input_retry, SHA는 evidence-index.json에 있다.
실행 당시 working-tree SHA와 최종 커밋은 각 provenance/summary로 구분한다.
재현 순서는 counter campaign → aggregation fit → 별도 DDS/B2/C2 → native smoke다.
4/5 power/wire guards와12/10 UDP worker는 유한 실행 후 복원한다.
일반 sudo 정책을 확대하지 않았고 원래 연구 DDS 설치와 signed survey 모듈은 유지했다.
