"""Build a self-contained evidence report without claiming failed gates passed."""
import argparse
import csv
import html
import json
from pathlib import Path
import statistics
import subprocess
import sys
from deploy import ROOT
from w1_packets import inspect
sys.path.insert(0,str(ROOT))
from rospacer.metrics import analyze_pair,recovery_metric


def load(p,default=None):
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def esc(v):return html.escape(str(v))
def num(v):return '미확정' if v is None else f'{v:,.3f}'
def table(head,rows):return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(v)+'</th>' for v in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);a=p.parse_args()
    base=ROOT/'runs'/a.run;derived={'processing_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'campaigns':{},'scope':'measured evidence; failed gates remain failed'}
    cal=load(base/'calibration/summary.json',{});radio=load(base/'radio_evidence.json',{})
    body='<h1>W1 · 4·5번 계수기와 유선 시계 검증</h1><p>기준일 2026-10-12 · Ubuntu22.04 / ROS2 Humble · Fast DDS 우선, CycloneDDS 우선 · Zenoh는 사용자 순서에 따라 후속.</p>'
    body+='<div class="status"><b>W1 전체 통과 아님.</b> 두 장비의 survey 채널 귀속과 상대 시계 동기화는 확보했다. 기존 식(7)의 자기송신·AP중계 전제는 자기 부하 측정에서 통과하지 못했다. 적응형 성공이나 모델 오차20% 통과를 주장하지 않는다.</div>'
    body+='<h2>장비와 교정</h2><p>4(csilab)→5(csi)가 주 측정 쌍이다. 둘 다 mt7921e, 실행 커널6.8.0-138-generic이며 각 장비에서 MOK 등록 후 서명 모듈5개를 로드했다. 원본 모듈은 보존했다. 149번 in-use의 계수가 증가하고36번 시간 계수 증분은0인 것을 양방향100Mb/s probe로 확인했다.</p>'
    body+='<p>AX1500SR 두 AP는149번·80MHz이다. 주 AP는 AX1500(b0:38:6c:7d:f5:74), B2 경쟁 AP는 SR2(b0:38:6c:7e:35:f4). C2에는 주 쌍도 SR2로 이동하고 종료 후 AX1500으로 복귀한다. 12→10은 유한 시간 경쟁 트래픽만 보낸다.</p>'
    body+=table(['교정','수신 payload Mb/s','수신 버퍼 오류 증가'],[(r['name'],num(r.get('receiver_bps',0)/1e6),r.get('udp_error_delta_5',{}).get('RcvbufErrors')) for r in cal.get('trials',[])])
    body+='<p>UDP1400B·30초×3·1MiB 소켓의 수신 중앙값='+num(cal.get('C0_receiver_median_bps',0)/1e6)+'Mb/s. 이는 이 조건의 수신 처리량이며 무손실 용량이나 DDS goodput 보장이 아니다. UDP3의52건 수신 버퍼 오류도 보존했다. iperf3 서버의 end.bytes=0 대신 수신 interval bytes/time을 쓴다.</p>'
    ping=load(base/'calibration/ping.json',{});body+='<pre>'+esc('\n'.join(ping.get('stdout','').splitlines()[-3:]))+'</pre>'
    body+='<h2>상대 시계와 지표</h2><p>4의 유선192.168.50.2가5의192.168.50.1을 chrony로 참조한다. 저장된 NetworkManager 프로파일은 수정하지 않았다. 5의 기존 유선 자동 연결로 원격 접속이 끊긴 뒤 사용자가 연결만 비활성화했고, 수동 관리 주소와 자동 복구 guard로 제어를 복원했다.</p>'
    body+='<p>5는 local stratum10 기준이다. UTC 정확도가 아니라 두 단말 사이의 상대 시계를 검증했다. 각 run에서 wired source 선택, 실제 NTP 유선 주소, Normal 상태, 표본 연속성 및 시간 범위를 검사하고 |system correction|+root delay/2+root dispersion의 합이1ms 이하일 때만 종단 지연을 계산한다. 목표는0.2ms다. 부하 중 별도130표본의 최대 상대 오차 한계는0.081ms였다.</p>'
    body+='<p>지연은 payload에 기록한 발행 직전 wall time부터 수신 콜백 wall time까지다. 직렬화·DDS·큐 대기를 포함한다. proposal 도착 간격 지터는 |연속 고유 도착 간격−요청 발행 주기|의p99로 계산한다. 도착 간격 표준편차도 별도 저장한다. 복구 시간은 복구 후1초 이동 창의 지연p95가 단절 전p95의2배 이하가 되는 첫 시점이다(최소3표본); 첫 패킷 도착 시각과 구분한다.</p>'
    probe=load(base/'wifi_probe/summary.json',[])
    body+='<h3>현재138커널의 실제 WiFi200Mb/s 검사</h3>'+table(['조건','UDP payload Mb/s','HTB class Mb/s','fqdrop'],[(r['name'],num(r.get('receiver_Mbps')),num(r.get('class_steady_Mbps')),r.get('fq_drop_max')) for r in probe])
    body+='<p>기본값,burst1500B,burst65536B를 각각10초 진단했다. 진단 UDPport55311만 추가 분류했고 종료noqueue를 확인했다. 해당 큐의 IP packet byte 상한과 수신 UDPpayload 처리량을 구분한다.</p>'
    for campaign in ['ros45','ros45_stock','ros45_stock_bp','ros45_stock_outage','ros45_stock_adaptive_diagnostic']:
        folder=base/campaign
        if not folder.exists():continue
        rows=[];evidence={}
        for f in sorted(folder.glob('*/summary.json')):
            r=load(f);d=f.parent;pub=load(d/'4/pub.json');sub=load(d/'5/sub.json');metrics=analyze_pair(pub,sub,r.get('clock'));packets={}
            for h in ['4','5']:
                capture=d/h/'wifi.pcap'
                if capture.exists():packets[h]=inspect(capture)
            e={'execution_commit':r.get('commit'),'metrics':metrics,'clock':r.get('clock'),'pinned_runtime_check':r.get('pinned_runtime_check'),'packets':packets,'telemetry':r.get('telemetry'),'restoration':r.get('restoration'),'qdisc_after':r.get('qdisc_after')}
            trace=d/'4/govern.csv';pubstart=(pub.get('measurement_started_ns') or 0)/1e9;pubend=(pub.get('measurement_ended_ns') or 0)/1e9
            if trace.exists():
                counters=[];trace_rows=list(csv.DictReader(trace.open()))
                for line in trace_rows:
                    for cl in json.loads(line['class_json']):
                        if cl.get('handle')=='7ac0:10' and pubstart+3<=float(line['monotonic_s'])<=pubend-1:counters.append((float(line['monotonic_s']),cl['bytes']))
                e['steady_HTB_class_Mbps']=8*(counters[-1][1]-counters[0][1])/(counters[-1][0]-counters[0][0])/1e6 if len(counters)>1 else None
                if r.get('adaptive_diagnostic_only'):
                    caps=[float(line['cap_packet_Bps'])*8/1e6 for line in trace_rows];ticks=[float(line['monotonic_s']) for line in trace_rows]
                    e['adaptive_diagnostic']={'samples':len(trace_rows),'updated':sum(line['status']=='updated' for line in trace_rows),'holds':sum(line['status']=='hold' for line in trace_rows),'cap_min_Mbps':min(caps),'cap_max_Mbps':max(caps),'update_interval_median_s':statistics.median(b-a for a,b in zip(ticks,ticks[1:])),'model_qualified':False}
            if 'outage' in r:e['recovery']=recovery_metric(sub,r['outage'],r.get('clock'));e['outage']=r['outage']
            evidence[r['name']]=e;lat=metrics['end_to_end_latency_ms'] or {}
            rows.append([r['name'],str(metrics['unique_received'])+'/'+str(metrics['requested']),num(metrics['actual_publish_hz']),num(lat.get('p50')),num(lat.get('p95')),num(lat.get('p99')),num(metrics['arrival_jitter_ms']['p99']),num((r.get('clock') or {}).get('relative_error_bound_ms')),num(e.get('steady_HTB_class_Mbps'))])
        derived['campaigns'][campaign]=evidence
        body+='<h2>'+esc(campaign)+'</h2>'
        body+='<p>'+('기존 연구용 DDS 수정본의 동작 확인으로만 보존한다. 공식 기본 설정의 성능으로 해석하지 않는다. Cyclone Default의 자동 인터페이스 선택 실패도 보존했다.' if campaign=='ros45' else '격리된 고정 DDS/RMW 라이브러리를 사용했고 실제 로드 해시를 매 실행 대조한다. Fast DDS2.6.11은10번의 공식 ROS 패키지 closure, CycloneDDS0.10.5는4번의 수정 없는 소스 빌드 closure다. 기존 연구 설치는 유지한다.')+'</p>'
        body+=table(['조건','수신/예정','실제 발행Hz','지연p50ms','p95ms','p99ms','지터p99ms','시계한계ms','HTB class Mb/s'],rows)
        if campaign.endswith('_bp'):
            body+='<p>1MiB·KEEP_ALL, 발행 요청0.8C0, HTB packet rate0.5C0,30초. ss를 포함한 telemetry0.1초, fqflow100과 설계 한도를 비교한다. 성공 발행 전달률만으로 발행 부하 감소를 숨기지 않는다. HTB/소켓 대기와DDS 보관함의 연쇄는 소스 및 오류와 함께 판단한다.</p>'
            body+=table(['조건','publish실패','publishp95ms','sockett최대','socketw최대','SndbufErrors','fqdrop최대'],[(name,e['metrics']['publish_failed'],num(e['metrics']['publish_duration_ms']['p95']),e['telemetry']['4']['skmem_max'].get('t'),e['telemetry']['4']['skmem_max'].get('w'),e['telemetry']['4']['udp_delta'].get('SndbufErrors'),e['telemetry']['4']['fq_drop_max']) for name,e in evidence.items()])
        if campaign.endswith('_outage'):body+=table(['조건','단절 실제s','첫 도착s','proposal복구s','단절 전p95ms'],[(name,num((e['outage']['outage_ended_monotonic_ns']-e['outage']['outage_started_monotonic_ns'])/1e9),num(e['recovery'].get('first_arrival_after_restore_s')),num(e['recovery'].get('recovery_s')),num(e['recovery'].get('baseline_p95_ms'))) for name,e in evidence.items()])
        if campaign.endswith('_adaptive_diagnostic'):
            body+='<div class="status">제한된 적응형 진단만 수행했다. 일반 adaptive의 검증 게이트는 유지한다. rawbusy가자기TX를 제외한다고 가정하고 수신단말 PHYsnapshot을 쓰며,0.9C0 상한 아래에서만 갱신한다. 이 실행으로 자기부하 잔차나intrinsic O가 검증됐다고 판정하지 않는다.</div>'
            body+=table(['조건','갱신/표본','보류','주기중앙값s','상한최소Mb/s','상한최대Mb/s'],[(name,str(e['adaptive_diagnostic']['updated'])+'/'+str(e['adaptive_diagnostic']['samples']),e['adaptive_diagnostic']['holds'],num(e['adaptive_diagnostic']['update_interval_median_s']),num(e['adaptive_diagnostic']['cap_min_Mbps']),num(e['adaptive_diagnostic']['cap_max_Mbps'])) for name,e in evidence.items()])
    body+='<h2>자기 부하와 적응형 게이트</h2><p>UDP1400B의 조건부 유효 O='+num(radio.get('conditional_O_s',0)*1e6)+'µs. actual receiver RX PHY를 하향 입력으로 사용했다. 송신 단말의 RX PHY를 수신 단말 하향률로 대체하지 않는다. 이O를 DDS1472B/RTPS 헤더 비용으로 옮기지 않았다.</p>'
    body+=table(['자기부하ρ','busy/active','tx/active','식(7)β 원값','busy가자기TX제외 가정 시β'],[(r['rho'],num(r['busy_fraction']),num(r['tx_fraction']),num(r['proposal_beta_unclipped']),num(r['alternative_excludes_self_tx_beta_unclipped'])) for r in radio.get('selfload',[])])
    body+='<p>송신 측busy&lt;tx가 재현돼 기존0≤tx≤busy≤active 전제를 만족하지 않는다. busy의 자기TX 제외를 가정하면 음수는 줄지만 자기 부하에 따라 잔차가 달라져 AP중계 보정과0 근처 조건을 통과했다고 판정할 수 없다. 음수를0으로 잘라 통과로 처리하지 않는다. 수치 수정으로 그럴듯한 결과를 만들지 않았다.</p>'
    refusal=load(base/'adaptive_refusal.json',{});body+='<pre>'+esc(json.dumps(refusal,ensure_ascii=False,indent=2))+'</pre><p>실제 장비에서 적응형 시작 거부와qdisc 불변을 확인했다. 유효하지 않은 계수로 HTB상한을 갱신하는 시험은 완료 근거에서 제외한다.</p>'
    semantics=load(base/'semantics/summary.json',{})
    body+='<h3>공유기 직접 전송과 AP중계의 참조 시험</h3>'+table(['구간','active s','busy s','tx s','stationTX bytes'],[(name,num(semantics[name]['delta']['active_s']),num(semantics[name]['delta']['busy_s']),num(semantics[name]['delta']['tx_s']),semantics[name]['delta']['bytes']) for name in ['idle','ap_only','relay'] if name in semantics])
    body+='<p>임시 passive monitor는4·5 MAC만 대상으로38초 캡처했고 삭제를 확인했다. AP→5 데이터 프레임은 중계 구간에서 포착됐으나 전체 프레임에 비해 불완전하다. busy와tx의 차감 관계에 대한 근거이며, 모든 AP airtime의 정확한 합을 얻은 것으로 해석하지 않는다. 10번의 독립 monitor 캡처를 준비했다. 자동rfmon 전환은현재dumpcap에서 실패했으며, 임시 인터페이스의 직접 생성은 sudo 정책 때문에 사용자의 로컬 실행이 필요하다.</p>'
    body+='<h2>B2 · C2</h2>'
    for label in ['b2','c2']:
        result=load(base/label/'summary.json',{})
        body+='<h3>'+label.upper()+'</h3>'+table(['측정','수신Mb/s','송신버퍼오류','수신버퍼오류'],[(r['name'],num(r['receiver_bps']/1e6),r.get('udp_error_delta_4',{}).get('SndbufErrors'),r.get('udp_error_delta_5',{}).get('RcvbufErrors')) for r in result.get('trials',[])])
    body+=table(['조건','측정','조건부Oµs','가정 변경의 미검증 예측Mb/s','미검증 오차%','정식 예측'],[(r['condition'],r['trial'],num(r.get('conditional_O_s',0)*1e6),num(r.get('alternative_unqualified_prediction_bps',0)/1e6),num(r.get('alternative_unqualified_error_percent')),'자기부하 게이트 미통과') for r in radio.get('model_conditions',[])])
    body+='<p>가정을 바꾼 계산은 진단용 counterfactual이며 정식 모델 검증 결과가 아니다. 수신 PHY 입력을 추가해도busy/tx 전제의 실패를 고치지는 못한다. B2/C2의20% 오차 판정을 통과한 것으로 쓰지 않는다.</p>'
    body+='<h2>확인 필요 항목별 답</h2>'+table(['항목','판정·근거'],[
        ['survey채널 귀속','4·5 모두149번 귀속 수정·실제 로드srcversion·양방향 증분 확인'],
        ['시간 동기','유선 상대 시계 확보; run별0.2ms 목표/1ms 제외 규칙 적용; UTC 보장 아님'],
        ['기본 교정','동일 절차 UDP30초×3/TCP30초/ping200와 동시200ms 무선 통계'],
        ['plan/golden/XML/손계산','기존 구현·실제 파서·XSD 검증 유지. 200Mb/s 예제alpha·이산 샘플 한도 차이를 이전 evidence.json에 기록'],
        ['HTB/fq200Mb/s·burst','기존12/10 actualWiFi에서 class199.997Mb/s,burst1500/65536과drop0 확인. 현138커널 결과는 새probe 영수증으로 구분'],
        ['W1 역압','0.8C0 대0.5C0 동시publish/ss/errors/qdisc; Fast 오류/timeout 분기와Cy blocking+retry 소스를 대조. 무손실 무기한 대기라고 결론내리지 않는다'],
        ['송신 소켓·fq','캡처 DATA_FRAG 사용자 sourceport와ss socket점유를 보존. UDPfq는packet hash로분류하므로socket개수=flow개수로 가정하지 않는다'],
        ['자기TX/AP중계','자기부하0.2..0.8 시험 수행; 기존 식 전제 미통과, 의미 검증 남음'],
        ['B2/C2 모델오차','측정과 진단용 계산을 기록; 정식 오차는 입력 전제 실패로 미확정'],
        ['적응형','일반 adaptive 게이트 거부 유지. 제한된 해석의 diagnostic에서각230회 갱신·보류0·156/156수신 확인. 정식 모델승인과구분'],
        ['비교군·지표','고정 런타임의Default/Vendor/Static/fixed 시운전 및latency/jitter/복구지표; fixed를adaptive ROSPacer로 부르지 않는다'],
        ['Vendor기능','Fast LARGE_DATA는WiFi TCP payload 캡처로 확인. CycloneVendor는native 단위/WHC+1MiB 송신/10MiB 수신 buffer이며 전체벤더 최적화 아님'],
        ['Zenoh','사용자 우선순위에 따라 Fast/Cyclone 이후로 이관']])
    restoration=load(base/'final_receipt.json',{})
    body+='<h2>종료·복원과 남은 일</h2><pre>'+esc(json.dumps(restoration,ensure_ascii=False,indent=2))+'</pre>'
    body+='<p>남은 선행 작업은10번의 독립 프레임 관측으로시간계수의물리적 의미·AP 중계·aggregation을 대조하고 모델의 자기부하 잔차를 확정하는 것이다. 후보 해석의B2/C2 오차는20%안이지만, 이 조건부 계산을 일반 adaptive의 정식 모델승인으로 바꾸지는 않았다. 랜케이블이나 MOK 등록을 반복할 필요는 없다.</p>'
    body+='<p>기존12/10 역압·200Mb/s·단절 자료는 runs/w1_20261012_ch149 및 이전 보고서에 보존했다. 장비·커널·버퍼·런타임이 다른 결과를 성능 개선률로 합치지 않는다.</p><p>측정 코드와설정/버전/교정/시계/원자료는 '+esc(str(base))+'에 있다. 보고서 처리 커밋 '+derived['processing_commit']+'.</p>'
    body+='<p>근거: <a href="https://docs.kernel.org/6.8/driver-api/80211/cfg80211.html#c.survey_info">Linux survey_info</a>, <a href="https://chrony-project.org/doc/4.2/chronyc.html">chrony4.2 tracking/ntpdata</a>, <a href="https://fast-dds.docs.eprosima.com/en/2.6.x/fastdds/use_cases/large_data/large_data.html">Fast DDS2.6 large-data</a>. 실제 버전 소스 발췌는 기존W1 evidence.json에 보존했다.</p>'
    style='body{font:16px/1.65 "Malgun Gothic",sans-serif;background:#f5f7fb;color:#192438;margin:0}main{max-width:1180px;margin:32px auto;padding:32px;background:white}h1{font-size:30px}h2{margin-top:40px;border-bottom:2px solid #dfe6f0}p{max-width:1040px}.status{padding:18px;background:#fff1db;border-left:5px solid #ba7500}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;margin:18px 0;font-size:14px}th,td{padding:10px;text-align:left;border-bottom:1px solid #dfe6f0;vertical-align:top}th{background:#eaf0fa;white-space:nowrap}pre{background:#f1f4f8;padding:16px;overflow:auto;font:13px/1.5 Consolas,monospace}a{color:#165aba}'
    report=ROOT.parent/'html 파일 모음/결과/W1 4·5번 유선 동기화 및 계수기 검증_261012.html';report.write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>W1 4·5번 추가 검증</title><style>'+style+'</style><main>'+body+'</main></html>',encoding='utf-8')
    (base/'derived_report.json').write_text(json.dumps(derived,indent=2,ensure_ascii=False),encoding='utf-8');print(str(report))


if __name__=='__main__':main()
