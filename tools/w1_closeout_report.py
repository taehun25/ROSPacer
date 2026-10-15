"""Map the requested checklist to original W1 requirements and new evidence."""
import html
import json
from deploy import ROOT
BASE=ROOT/'runs/w1_20261013_w1_closeout'
NAME='W1 항목별 상태점검_261013.html'
def table(headers,rows):
    return '<div class="scroll"><table><tr>'+''.join('<th>'+x+'</th>' for x in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</table></div>'
def link(name,title):return '<a href="../../../ROSPacer/runs/w1_20261013_w1_closeout/'+name+'">'+title+'</a>'
def main():
    audit=json.loads((BASE/'current_restoration_audit.json').read_text())
    air=json.loads((BASE/'airtime_identifiability.json').read_text())
    b2=json.loads((BASE/'sender_b2_post_ssh/gap_analysis.json').read_text())
    keep=json.loads((BASE/'preservation.json').read_text())
    s='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>W1 항목별 상태점검 · 2026-10-13</title><style>
body{font:16px/1.75 system-ui,sans-serif;background:#f3f6fa;color:#24364d;margin:0}main{max-width:1120px;margin:24px auto;padding:30px;background:white;border-radius:10px}h1{font-size:28px}h2{margin-top:32px;border-bottom:1px solid #d4dfeb;padding-bottom:6px}table{border-collapse:collapse;width:100%;font-size:14px;margin:18px 0}th,td{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid #d6dfeb}th{background:#edf2f8}.scroll{overflow:auto}.status{padding:18px;background:#fff3d7;border-left:4px solid #af7c20}details{border:1px solid #d4dfeb;margin:16px 0;border-radius:6px}summary{padding:12px;cursor:pointer;background:#f6f8fb;font-weight:650}details>div{padding:16px}code{overflow-wrap:anywhere}a{color:#175d99}i{font-family:Cambria,serif;font-style:italic}@media(max-width:650px){main{padding:18px;margin:0}h1{font-size:24px}}
</style></head><body><main><h1>W1 항목별 상태점검</h1><p>2026-10-13 · 원 proposal 일정과 실제 증거를 대조한 추가 점검</p>
<div class="status"><b>목록 전체가 W1 미완료인 것은 아니다.</b><p>종료·복원은 이번 점검에서도 통과했다. 물리 airtime 독립 식별의 정보 부족과 Sender-only B2 입력 부족은 새 자료로 확인했다. 정식 성능 비교·동적 추종·전체 Drain 평가는 이번 요청의 W1 범위에서 실행하지 않았다. 현재 자료로 원식 기반 Sender-only 제어를 승인하지 않는다.</p></div>
<h2>1. 요청 항목과 원 제안서 일정</h2>'''
    s+=table(['요청 항목','W1 해당 범위','현재 상태·이번 처리'],[
        ['전체 HE/PPDU airtime·단일 물리 O 독립 식별','W1은 C₀에 O를 맞추고 HE 프리앰블·확인응답 계산값과 비교(e-calib). 전체 PPDU/보편 물리 O의 완전 독립 식별은 별도 요구','운용 비용 교정은 기존 완료. 독립 물리 비교는 정보 부족: 실제6개 캡처의 HE/AMPDU 필드를 재검사'],
        ['다른 AP·driver·payload 일반화','범위 밖 일반화의 완성은 W1 일정에 없음. W1은 시험 장비·조건별 교정과 전제 확인','이번 W1 요청에서는 확대 실험하지 않음. AX149/80·MT7921·1MiB 프로파일 범위를 유지'],
        ['원래 Sender-only 실현 가능성','확인 필요 B의 하향 속도·중계 포함과 W1 자기 부하/B2/C2 입력 확인에 해당','새 B2 진단 실행·자료 회수. 정상 CRC 관측64.6%로 기존80% 게이트 미달; 원식 적용·자동 갱신 계속 보류'],
        ['Adaptive 대 Static/Fixed 정식 성능 비교','W1은 비교군 시운전. E·F 판정/P0는 W2, 나머지는 W3','짧은 기능 시운전만 기존 증거로 유지. 정식 우위·CI 비교는 이번 실행 범위 제외'],
        ['경쟁 변화 실시간 송신율 추종','최소200ms 갱신 동작은 W1. F의0/0.5C₀/0.9C₀/0 일정 추종 성능은 W2','기존 갱신·결측 hold 기능 확인 유지. 정식 F 성능 시험은 제외'],
        ['전체 Drain Control 동작','W1 최소 HTB/fq·큐·갱신기와 구분. D/ROSPacer−drain 성능·ablation은 W2~W4','기존 짧은 단절 시운전을 전체 Drain 검증으로 인정하지 않음. 이번 확대 구현/시험 제외']])
    s+='<p>기준 위치: <a href="../../../연구 프로포졸 자료/WirelessXML_Proposal (2).html">WirelessXML_Proposal (2).html</a>의 확인 필요 B·C, 링크 교정과 W1 측정(e-calib), 비교군(e-arms), 실험 매트릭스(e-matrix), W1~W4 일정. 사용자가 정한 Fast/Cyclone 우선 순서에 따라 Zenoh는 이전 합의대로 후속 단계다.</p>'
    s+='<h2>2. 물리 airtime 식별에 필요한 필드 재검사</h2>'
    rows=[]
    for r in air['captures']:
        c=r['counts'];rows.append([r['pcap'],c['crc_valid_peer_data'],c.get('GI_known',0),c.get('LTF_symbol_count_known',0),c.get('pre_FEC_padding_known',0),c.get('AMPDU_last_known',0)])
    s+=table(['캡처','정상 CRC AP→5 데이터','GI known','LTF 기호 수 known','pre-FEC pad known','AMPDU last known'],rows)
    s+='<details><summary>왜 LTF·PPDU와 O를 독립 확정할 수 없는가</summary><div><p>known은 해당 수치를 driver가 알고 제공했다고 표시하는 비트다. 이번 데이터는 GI가 알려져 있고 raw LTF size는1(1×)이지만, LTF 기호 수와 pre-FEC padding known은 모든 검사 캡처에서0이었다. 결측 수치를0개/0시간이라고 해석하지 않는다. AMPDU 마지막 표시와 신뢰할 전체 PPDU 경계도 확보되지 않았다. reference가 거의 모든 MPDU에서 다르다고 각각 별도 PPDU였다고 간주하지 않는다.</p><p>PHY 전송률과 byte 수로 얻는 serialization은 payload 전송 시간의 대리값이다. HE preamble·ACK·SIFS·padding·aggregation 전체의 독립 airtime과 다르다. 한 C₀ 교정은 상향·하향의 가중 서비스 비용을 맞출 수 있지만 두 물리 O와 aggregation 효과를 분리하는 독립 관측을 추가하지 않는다. 대칭 O 분할은 가정이며 독립 식별이 아니다.</p><p>이번 검사는 설치 커널의 ieee80211_radiotap.h 정의를 환경 기록에 함께 저장했다. 현재 정보만으로 이 항목을 완료로 바꿀 수 없으며, 필요한 정보를 제공하는 관측 장치/driver 경로 또는 모델의 명시적 범위 변경이 필요하다.</p></div></details>'
    s+='<h2>3. 새 Sender-only B2 진단</h2>'
    ca=b2['control_diagnostic']['4']['counts'];cr=b2['control_diagnostic']['5']['counts']
    s+=table(['지표','새 결과','해석'],[
        ['정상 CRC body / 송신 station byte',f"{b2['good_body_coverage']*100:.2f}%",'현재 profile 게이트80%에 미달. 제어 입력 부족'],
        ['CRC 오류 후보를 잠정 포함',f"{b2['all_candidate_body_coverage']*100:.2f}%",'정상 수신률/유효 입력이 아님. 오류 주소·길이도 잠정값'],
        ['4번 AP→5 RTS / 5번 오프라인 참조 RTS',f"{ca['peer_rts_good']}/{cr['peer_rts_good']} = {ca['peer_rts_good']/cr['peer_rts_good']*100:.2f}%",'개수 비교; 독립 PPDU airtime을 제공하지 않음'],
        ['RTS-CTS-BA 후보',ca.get('peer_rts_cts_ba_candidates',0),'수동 교환 진단량'],
        ['BA timestamp−NAV 중앙값',str(b2['control_diagnostic']['4']['rts_to_ba_minus_nav_us_median'])+' µs','예약시간을 airtime으로 그대로 적용하지 않음'],
        ['HW FCS 오류 증가',b2['low_level_delta']['dot11FCSErrorCount'],'라디오 전체의 캐시 계수; 우리 프레임만의 오류 아님'],
        ['kernel capture drop','0','호스트 큐 drop은 없음. 공중 포착 완전성을 의미하지 않음']])
    s+='<details><summary>조건·종료 후 연결 문제·검증 범위</summary><div><p>주4→AX1500→5, UDP100Mb/s 요청8초. 경쟁12→SR2→10, UDP300Mb/s 요청48초. 두 AP149/80MHz. 같은 라디오 monitor·FCS 진단을 사용했다. 이 연속 경쟁 진단은 proposal의2초 ON/2초 OFF 정식 B2와 구분한다. CPU 상태와 순간 RF 환경도 앞선 run과 같다고 가정하지 않는다.</p><p>측정은 끝났지만 monitor 삭제·절전 복원 후4번이 ping/SSH 접속 단계에서 응답하지 않아 회수가 실패했다. 유선 관리 주소를 잠시 복원해 양쪽 원자료를 회수했고, 같은 AX 프로파일 재연결 후 직접 SSH를 복구했다. monitor 삭제·절전on은 로그에 남아 있었고 dmesg에는 관련 메시지가 없었다. 내부 firmware/driver 원인을 확정하지 않았다. 앞서 수정한 IPQoS의 인증 후 SSH 멈춤과 별도 증상으로 기록한다.</p><p>100Mb/s 요청 부하는 링크 포화 측정이 아니므로 이 run으로 최대 용량 오차20% 통과를 주장하지 않는다. 동일 라디오 companion 관측의 실행·종료 안정성과 B2 가시성도 Sender-only 승인 전에 해결해야 한다. Receiver-assisted 기존 자료와 코드, validated=false sender gate를 유지한다.</p></div></details>'
    s+='<h2>4. 종료·복원 및 기존 연구 설치 점검</h2>'
    rows=[]
    labels={'noqueue':'Wi-Fi root noqueue','no_htb_classes':'HTB class 없음','no_monitor':'임시 monitor 없음','no_experiment_processes':'실험 프로세스 없음','buffers_212992':'rmem/wmem212992','no_owned_wired_ips':'임시50.x 주소 없음','research_dds_unchanged':'기록된 연구 DDS 해시 일치'}
    for h,checks in audit['checks'].items():
        rows.append([h]+['확인' if checks.get(k) else ('비교 기준 없음' if k=='research_dds_unchanged' else '대상 아님') for k in labels])
    s+=table(['노트북']+list(labels.values()),rows)
    s+='<p>4·5번의 기존 연구 DDS/RMW 라이브러리는 각각6개의10/12 실제 로드 경로/해시와 현재 파일을 대조해 모두 일치했다. 12·10은 위 비교 기준에 연구 라이브러리 경로가 없으므로 같은 해시 검사를 했다고 표시하지 않는다. 이번 요청에서 DDS 설치·업그레이드를 수행하지 않았다. Wi-Fi 절전on, 임시 유선 주소 제거, noqueue를 확인했다. 4번의SSH 전용 IPQoS 수정은 문제 해결 설정으로 유지한다.</p>'
    s+='<h2>5. 원자료·소스·환경 보존</h2>'
    s+=table(['항목','보존'],[['W1 파일 SHA-256 인덱스',f"{keep['file_count']:,}개 파일"],['실제 현재 소스 snapshot',keep['source_snapshot_sha256']],['git 기준',keep['git_commit']+'; dirty source='+str(keep['dirty_source'])],['환경','4/5/12/10 kernel·module·AP/interface·qdisc·버퍼·프로세스·radiotap 정의']])
    s+='<p>현재 소스 archive와 git commit을 함께 보존했다. dirty 소스를 commit과 동일하다고 표시하지 않는다. 과거 run의 실제 소스 해시는 유지하며 이번 archive로 과거 실행 코드를 대체하지 않는다. 인덱스에 있는 파일의 존재와 무결성 보존은 모든 과거 측정의 유효성을 승인한다는 뜻이 아니다.</p>'
    s+='<p>'+' · '.join(link(n,t) for n,t in [('current_restoration_audit.json','현재 복원 검사'),('airtime_identifiability.json','HE 필드 식별 검사'),('sender_b2_post_ssh/gap_analysis.json','새 B2 진단'),('preservation.json','보존 영수증'),('evidence_sha256.json','파일 해시 인덱스'),('current_source.tar.gz','현재 소스 archive')])+'</p>'
    s+='</main></body></html>'
    dest=ROOT.parent/'html 파일 모음/결과/W1 실험결과'/NAME;dest.write_text(s,encoding='utf8')
    for p in [ROOT.parent/'html 파일 모음/W1 보고서.html',dest.parent/'W1 보고서.html',dest.parent/'W1 무선 입력 추가 검증_261013.html',dest.parent/'W1 송신 관측 누락 진단_261013.html']:
        if not p.exists():continue
        old=p.read_text(encoding='utf8')
        if 'id="w1-scope-closeout"' in old:continue
        href=('결과/W1 실험결과/' if p.parent==ROOT.parent/'html 파일 모음' else '')+NAME
        block='<p id="w1-scope-closeout"><a href="'+href+'">W1 항목별 상태점검: 일정 범위·새 B2·물리 입력 한계·최종 복원</a></p>'
        marker='</main>' if '</main>' in old else '</body>';p.write_text(old.replace(marker,block+marker,1),encoding='utf8')
    print(dest)

if __name__=='__main__':main()
