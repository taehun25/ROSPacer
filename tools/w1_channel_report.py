"""Report channel149 measurements separately from the preserved channel36 run."""
import html
import csv
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from deploy import ROOT

BASE = ROOT/"runs/w1_20261012_ch149"
OUT = ROOT.parent/"html 파일 모음/결과/W1 149채널 B2 추가 검증_261012.html"


def read(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def esc(value):
    return html.escape(str(value))


def table(headers, rows):
    return '<div class="scroll"><table><tr>'+''.join('<th>'+esc(s)+'</th>' for s in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+esc(s)+'</td>' for s in row)+'</tr>' for row in rows)+'</table></div>'


def num(value):
    return '미측정' if value is None else f'{value:,.2f}'


def main():
    cal = read(BASE/'calibration_ready/summary.json', {})
    c2 = read(BASE/'competition/summary.json', [])
    b2_folder = BASE/('b2_fixedperiod' if (BASE/'b2_fixedperiod').exists() else 'b2')
    b2 = read(b2_folder/'summary.json', {})
    end = read(BASE/'end_receipt.json', {})
    restored = bool(end) and all(r.get('rc') == 0 and json.loads(r.get('stdout', '{}')).get('restored') for r in end.values())
    trials = b2.get('trials', read(b2_folder/'progress.json', []))
    stage = read(BASE/'stage_sources.json', {})
    when = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M KST')
    body = '<h1>W1 · 채널149 추가 교정 및 B2</h1><p>갱신 '+when+'</p><p><strong>W1 전체 완료 아님.</strong> 기존 36번 측정과 새 149번 결과를 구분하여 보존한다.</p>'
    body += '<section><h2>장비·채널 조건</h2><p>SR2 BSSID b0:38:6c:7e:35:f4, AX1500 BSSID b0:38:6c:7d:f5:74가 모두 149번(5745 MHz)에서 관측됐다. 12/10의 SR2 실제 연결은 80 MHz, 중심5775 MHz다. B2에서는 4/5가 AX1500에 연결되어야 하며 그 연결 정보는 additional_pair.json에 기록한다. 두 AP의 근거리 수신 세기도 AP 스캔에 보존했다.</p>'
    body += '<p>기본 교정과 C2 당시 12/10은 Wi-Fi 절전 off, CPU performance다. 4/5의 전원·송신 전력 설정은 기록하며 변경하지 않는다. 다른 주변 149번 AP도 관측되어 외부 트래픽이 0인 환경이라고 주장하지 않는다.</p></section>'
    body += '<section><h2>기본 교정</h2>'+table(['조건', '수신 payload Mb/s'], [(r['name'], num(r.get('receiver_bps', 0)/1e6)) for r in cal.get('trials', [])])
    c0 = cal.get('C0_UDP_receiver_median_bps')
    body += '<p>UDP30초×3 중앙값 C0='+num(c0/1e6 if c0 else None)+' Mb/s. TCP30초, ping200회 및 동시 무선·소켓·커널 관측을 보존했다. UDP b=0은 포화 부하이며 유실을 포함한 수신 byte/seconds다. PHY 용량·무손실 보장 전송률·DDS goodput과 동일하지 않다. iperf3 3.9 end-summary bytes=0 문제 때문에 수신 interval byte로 계산한다.</p><pre>'+esc('\n'.join(cal.get('ping', {}).get('stdout', '').splitlines()[-3:]))+'</pre></section>'
    errors = []
    for name in ['udp1', 'udp2', 'udp3']:
        path = BASE/'calibration_ready'/(name+'_10_telemetry.jsonl')
        if path.exists():
            rows = [json.loads(s) for s in path.read_text().splitlines()]
            errors.append((name, rows[-1]['udp_global']['RcvbufErrors']-rows[0]['udp_global']['RcvbufErrors']))
    body += '<section><h2>교정 입력의 한계</h2>'+table(['조건', '10번 전역 UdpRcvbufErrors 증가'], errors)+'<p>수신 기본 버퍼는 212992 B이며 포화 UDP의 수신 버퍼 오류가 증가했다. 전역 카운터이므로 다른 UDP 프로세스의 영향 가능성은 남지만, 유실 수와 대조할 수 있도록 iperf 원문을 보존했다. 위 C0를 순수 airtime 링크 용량으로 식별하지 않는다. B2/C2의 수신 버퍼 조건은 유지한다. 수신 버퍼를 충분히 키운 별도 교정과 모델 입력 정의 확인이 필요하다.</p></section>'
    buffered = read(BASE/'calibration_1mib/summary.json', {})
    if buffered:
        buffered_rows = []
        for r in buffered.get('trials', []):
            path = BASE/'calibration_1mib'/(r['name']+'_10_telemetry.jsonl')
            rows = [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
            delta = rows[-1]['udp_global']['RcvbufErrors']-rows[0]['udp_global']['RcvbufErrors'] if rows else None
            buffered_rows.append((r['name'], num(r.get('receiver_bps', 0)/1e6), delta))
        body += '<section><h2>별도 1 MiB 소켓 교정</h2>'+table(['조건', '수신 payload Mb/s', '10번 UdpRcvbufErrors 증가'], buffered_rows)+'<p>iperf -w1048576을 명시하고 커널 상한을 임시로 1 MiB로 올렸다. 기존 C2/B2의 기본 버퍼 조건과 구분한다. 이 결과가 모든 조건의 무선 몫 또는 무손실 보장 전송률이라는 주장은 하지 않는다. 커널 상한 복원 영수증은 buffer_calibration_restoration.json에 보관했다.</p></section>'
    body += '<section><h2>C2 · 동일 AP 경쟁 트래픽</h2>'+table(['조건', '12→10 수신 Mb/s', '5→4 요청 Mb/s'], [(r['trial'], num(r['receiver_bps']/1e6), num(r['contender_requested_bps']/1e6)) for r in c2])+'<p>4/5는 SR2에 연결하고 5→4에 0.9C0 UDP 부하를 넣는다. 무선 시간 계수기 결측으로 모델 추정 몫과 20% 오차 기준은 판정하지 못한다.</p></section>'
    wifi = read(BASE/'wifi_probe/summary.json', [])
    if wifi:
        body += '<section><h2>실제 Wi-Fi · HTB 200 Mb/s</h2>'+table(['조건', 'UDP 수신 payload Mb/s', 'HTB class 정상 구간 Mb/s', 'fq drop 최대', '종료 root'], [(r['name'], num(r['C_receiver_Mbps']), num(r.get('class_steady_Mbps')), r.get('fq_drop_max'), ','.join(q['kind'] for q in r['root_after'])) for r in wifi])+'<p>각10초, 명시1 MiB 소켓의 별도 진단이다. baseline이200 Mb/s를 넘고, HTB class의 byte 증가율로 상한을 확인한다. payload 수신률은 IP/UDP·링크 헤더 등으로 class 전송률보다 작다. 한 번의 단기 관측이며 모든 조건의 상한 정확도 또는 DDS 역압 의미론을 입증하지 않는다. 커널 상한은 진단 종료 후 복원한다.</p></section>'
    body += '<section><h2>B2 · 별도 AP의 같은 채널 트래픽</h2>'+table(['조건', '12→10 수신 Mb/s', '동시에 진행한 성공 burst 수', '대략적 시각 대응 오차(s)'], [(r['trial'], num(r['receiver_bps']/1e6 if r.get('receiver_bps') else None), r.get('successful_contender_bursts_overlapping_call', '집계 대기'), num(r.get('campaign_clock_mapping_uncertainty_s'))) for r in trials])
    body += '<p>5→4 UDP b=0을 요청2초 전송·4초 시작 간격으로 반복한다. 초기 구현은 종료 뒤2초 휴지하여 협상 시간까지 더해 주기가 약4.4초였다. 첫3회는 b2 폴더에 보존했고 보정한 반복은 b2_fixedperiod에 별도 저장한다. 실제 전송 길이는 burst별 interval JSON과 단조 시각 로그로 검증한다. 관리 PC는 AX1500에서 유한 시간 작업을 준비하고 SR2로 복귀한 뒤 본 링크를 측정한다. 각 burst 및 전체 작업 모두 종료 시간 제한이 있다.</p>'
    if b2:
        bursts = b2['contender']['bursts']
        ok = sum(r.get('rc') == 0 and not r.get('error') for r in bursts)
        body += '<p>간섭 source 성공 burst '+str(ok)+'/'+str(len(bursts))+'개. 호스트 시계 간 지연을 계산하지 않았다. SSH 왕복 시간으로 단조 시계를 대략 대응한 것은 캠페인 동시 진행 확인용이며, proposal의 0.2 ms 시계 자격을 충족하는 근거가 아니다.</p>'
    else:
        body += '<p><strong>B2 아직 완료 아님:</strong> '+esc(stage.get('status', '추가 장비 연결·실행 대기'))+'</p>'
    bp_rows = []
    for path in sorted(BASE.glob('*_bp_*/summary.json')):
        r = read(path)
        pub = read(path.parent/'12/pub.json', {})
        start = pub.get('measurement_started_ns', 0)/1e9
        end_time = pub.get('measurement_ended_ns', 0)/1e9
        points = []
        for row in csv.DictReader((path.parent/'12/govern.csv').open()):
            for c in json.loads(row['class_json']):
                if c.get('handle') == '7ac0:10' and start+3 <= float(row['monotonic_s']) <= end_time-1:
                    points.append((float(row['monotonic_s']), c['bytes']))
        rate = 8*(points[-1][1]-points[0][1])/(points[-1][0]-points[0][0])/1e6 if len(points)>1 else None
        m = r['metrics']
        bp_rows.append((r['name'], r.get('calibration_label'), num(r['C0_Bps']*8/1e6), f"{m['requested']}/{m['publish_succeeded']}/{m['unique_received']}", num(m['publish_duration_ms']['p50']), num(rate), r['telemetry']['12']['fq_drop_max']))
    if bp_rows:
        body += '</section><section><h2>149번 · 새 교정값의 W1 역압</h2>'+table(['run', '교정 입력', 'C0 Mb/s', '예정/발행 성공/수신', 'publish p50 ms', 'HTB class Mb/s', 'fq drop'], bp_rows)+'<p>1 MiB/KEEP_ALL/30초, 요청0.8C0와 HTB0.5C0, flow_limit100/설계 값을 비교한다. 별도1 MiB 소켓 교정값을 입력으로 사용한다. 동일 run의 소켓 메모리·publish·UDP 오류·qdisc 로그를 보존한다. 대기만 관측된다고 전체 인과 경로나 모든 조건의 완전 전달을 입증한 것은 아니다.</p>'
    body += '</section><section><h2>복원·남은 항목</h2><p>12/10 설정 복원: <strong>'+('확인' if restored else '세션 진행 중 또는 최종 확인 대기')+'</strong>.</p><p>active/busy/tx 통계, AP 중계 보정, 자기 부하 검증, 검증된 시간 동기, B2/C2의 모델 예측 오차 판정은 여전히 미달성이다. 새로운 채널 조건은 무선 시간 계수기 결측을 해결하지 않는다. 적응형 제어를 완료했다고 표시하지 않는다.</p><pre>'+esc(json.dumps(stage, ensure_ascii=False, indent=2))+'</pre></section>'
    import os
    body += '<p><a href="'+Path(os.path.relpath(BASE, OUT.parent)).as_posix()+'">149번 원자료 폴더</a> · <a href="W1 구현 전제 검증_261012.html">기존 36번 W1 보고서</a></p>'
    style = 'body{font-family:Segoe UI,Malgun Gothic,sans-serif;color:#203248;background:#f2f5f8;line-height:1.7}main{max-width:1080px;margin:auto;padding:28px}section{background:white;border-radius:12px;padding:24px;margin:22px 0}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #dce4ed;text-align:left}th{background:#eaf0f7}.scroll{overflow:auto}pre{white-space:pre-wrap;font-size:13px;overflow-wrap:anywhere}h1{color:#163a59}a{color:#246995}'
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>W1 채널149 B2</title><style>'+style+'</style><main>'+body+'</main></html>', encoding='utf-8')
    state = {'report': str(OUT), 'w1_complete': False, 'C0_bps': c0, 'C2_trials': len(c2), 'B2_summary_available': bool(b2), 'restoration_verified': restored}
    (BASE/'report_state.json').write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(state, ensure_ascii=True))


if __name__ == '__main__':
    main()
