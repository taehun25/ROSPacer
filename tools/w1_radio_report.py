"""Render evidence-based 13 October radio addendum and refresh W1 status."""
from pathlib import Path
import csv
import hashlib
import html
import json
import re
import subprocess
from w1_fq_explanation import fq_explanation

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runs/w1_20261013_radio_input_retry'
DEST=ROOT.parent/'html 파일 모음'
NAME='W1 무선 입력 추가 검증_261013.html'
SENDER_NAME='W1 송신 측 수동 관측 프로토타입_261013.html'
E=html.escape


def load(name):return json.loads((BASE/name).read_text(encoding='utf8'))
def table(headers,rows):
    cls=' class="math-symbols"' if headers==['기호','의미'] else ' class="model-coefficients"' if headers==['계수','값','의미'] else ''
    return '<div class="scroll"><table'+cls+'><thead><tr>'+''.join('<th>'+E(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+E(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def note(title,body):return '<details><summary>'+title+'</summary><div class="note">'+body+'</div></details>'
def raw(path,label=None):return '<a href="../../../ROSPacer/runs/'+BASE.name+'/'+path.replace('\\','/')+'">'+E(label or path)+'</a>'
def write_section(source,identifier,body):
    pattern=r'(<h[23] id="'+re.escape(identifier)+r'">.*?</h[23]>).*?(?=<h[23] id=|</main>)'
    source,count=re.subn(pattern,lambda m:m[1]+body,source,flags=re.S)
    assert count==1,identifier
    return source


def model_equations():
    """Native MathML: fraction/subscript/accent layout without a CDN or JS."""
    def row(*parts):return '<mrow>'+''.join(parts)+'</mrow>'
    def ident(value):return '<mi>'+E(value)+'</mi>'
    def number(value):return '<mn>'+str(value)+'</mn>'
    def op(value):return '<mo>'+E(value)+'</mo>'
    def sub(base,label):return '<msub>'+base+'<mtext>'+E(label)+'</mtext></msub>'
    def hat(base):return '<mover accent="true">'+base+'<mo>^</mo></mover>'
    def frac(top,bottom):return '<mfrac>'+row(top)+row(bottom)+'</mfrac>'
    def par(*parts):return row(op('('),*parts,op(')'))
    def minimum(*parts):return row('<mi mathvariant="italic">min</mi>',op('('),*parts,op(')'))
    def math(body,label):return '<math xmlns="http://www.w3.org/1998/Math/MathML" display="block" aria-label="'+E(label)+'"><mstyle mathvariant="italic">'+row(body)+'</mstyle></math>'
    def line(label,body):return '<div class="eq-row"><div class="eq-label">'+label+'</div><div class="eq-scroll">'+math(body,label)+'</div></div>'
    d=ident('Δ');dr=sub(d,'rx');q=ident('q');rb=sub(ident('B'),'RX');rp=sub(ident('P'),'RX');mp=sub(ident('N'),'MPDU');ap=sub(ident('N'),'AMPDU');ab=sub(ident('B'),'AMPDU');ba=sub(ident('N'),'BA')
    ppdu=sub(hat(ident('N')),'PPDU');visible=sub(hat(ident('T')),'self-visible');beta=sub(hat(ident('β')),'other, raw');theta=hat(ident('θ'));down=sub(ident('R'),'dn');up=sub(ident('R'),'up');ip=sub(ident('L'),'IP');frame=sub('<mover accent="true"><mi>L</mi><mo>¯</mo></mover>','frame')
    at=sub(ident('A'),'tx');aligned='<msubsup><mi>X</mi><mtext>rx</mtext><mtext>aligned</mtext></msubsup>'
    formula='<style>a{overflow-wrap:anywhere}.equations{padding:12px 20px;background:#edf2f8;border:1px solid #d8e2ef;border-radius:8px;margin:18px 0}.eq-row{display:grid;grid-template-columns:155px minmax(0,1fr);gap:18px;align-items:center;padding:17px 0;border-bottom:1px solid #d6e0ec}.eq-row:last-of-type{border-bottom:0}.eq-label{font-size:14px;font-weight:600;color:#405977}.eq-scroll{overflow-x:auto;padding:8px 3px}.eq-scroll math{font-family:"Cambria Math","STIX Two Math",serif;font-size:21px;margin:0;width:max-content;min-width:0}.equation-notes{font-size:14px;border-top:1px solid #d6e0ec;padding-top:12px}.equation-notes p{margin:8px 0}@media(max-width:700px){.eq-row{grid-template-columns:minmax(0,1fr);gap:5px}.equations{padding:10px 14px}.eq-scroll math{font-size:19px}}@media print{.equations{break-inside:auto}.eq-row{break-inside:avoid}.eq-scroll{overflow:visible}.eq-scroll math{font-size:15px}}</style><div class="equations" id="model-equations">'
    formula+=line('관측 구간',row(d,op('='),at,par(sub(ident('t'),'1')),op('−'),at,par(sub(ident('t'),'0'))))
    formula+=line('수신 통계 구간 정렬',row(aligned,op('='),d,sub(ident('X'),'rx'),op('×'),frac(d,dr)))
    formula+=line('AMPDU 바이트 coverage',row(q,op('='),minimum(number(1),op(','),frac(ab,row(ident('k'),op('×'),rb)))))
    formula+=line('PPDU 수 추정',row(ppdu,op('='),ap,op('+'),mp,op('×'),par(number(1),op('−'),q)))
    formula+=line('자기 부하의 관측 busy',row(visible,op('='),sub(ident('h'),'BA'),ba,op('+'),ident('γ'),frac(row(rb,op('−'),number(14),rp,op('+'),number(50),mp),down),op('+'),sub(ident('h'),'PPDU'),ppdu))
    formula+=line('다른 트래픽 점유율',row(beta,op('='),frac(row(sub(ident('T'),'busy'),op('−'),sub(ident('f'),'idle'),d,op('−'),visible),d)))
    numerator=row(par(number(1),op('+'),ident('ν')),par(sub(ident('O'),'up'),op('+'),frac(ip,up)),op('+'),sub(ident('O'),'dn'),op('+'),frac(ip,down))
    formula+=line('단위 바이트당 운용 비용',row(theta,op('='),frac(numerator,frame)))
    formula+=line('평활 전 송신 상한',row(sub(ident('c'),'target'),op('='),minimum(number('0.9'),sub(ident('C'),'0'),op(','),frac(row(number('0.9'),par(number(1),op('−'),beta)),theta))))
    formula+='<div class="equation-notes"><p><em>β</em>의 음수값은 그대로 기록하며, 자기 TX를 다시 빼지 않는다.</p><p>200ms마다 입력을 수집·갱신하고 약3초 관측 창을 사용한다. 위 상한에 EMA 0.7/0.3을 적용한다.</p></div></div>'
    symbols=[['Δ / Δrx','송신/수신 active 계수의 구간 증분(s). X는 수신 바이트 또는 개수 통계이며 ΔXrx는 원시 구간 증분이다.'],['BRX / PRX','구간을 정렬한 수신 rx_bytes / rx_packets.'],['NMPDU / NAMPDU / BAMPDU','구간을 정렬한 수신 rx_mpdu_cnt / rx_ampdu_cnt / rx_ampdu_bytes_cnt.'],['NBA','송신 단말이 수신한 BlockAck의 rx_ba_cnt 구간 증분.'],['q / N̂PPDU','coverage 비율 / standalone MPDU 보정을 포함한 추정 PPDU 수.'],['Rup / Rdn','송신 단말의 TX PHY / 수신 단말의 RX PHY 속도(B/s).'],['ν','송신 retries 증분 / packets 증분.'],['LIP / L̄frame','평균 IP 패킷 바이트 / 평균 station frame 바이트. LIP=L̄frame−14.'],['fidle / Tbusy','무부하 busy 비율 / 송신 단말의 raw busy 구간 증분(s).'],['ctarget / C₀','평활 전 송신 상한 / 교정 처리량(B/s).']]
    italic_style='<style id="equation-italics">.eq-scroll math,.eq-scroll math *{font-style:italic}.math-symbols td:first-child,.model-coefficients td:first-child{font-family:"Cambria Math","STIX Two Math",serif;font-style:italic}</style>'
    return italic_style+formula+note('수식 기호와 코드 통계 이름',table(['기호','의미'],symbols))


def capacity_validation_note():
    """The offline UDP capacity predictor differs from the SKB governor."""
    theta='''<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><mstyle mathvariant="italic"><mrow><msub><mover accent="true"><mi>θ</mi><mo>^</mo></mover><mtext>UDP</mtext></msub><mo>=</mo><mfrac><mrow><mo>(</mo><mn>1</mn><mo>+</mo><mi>ν</mi><mo>)</mo><mo>(</mo><msub><mi>O</mi><mtext>cal</mtext></msub><mo>+</mo><mfrac><mn>1428</mn><msub><mi>R</mi><mtext>up</mtext></msub></mfrac><mo>)</mo><mo>+</mo><msub><mi>O</mi><mtext>cal</mtext></msub><mo>+</mo><mfrac><mn>1428</mn><msub><mi>R</mi><mtext>dn</mtext></msub></mfrac></mrow><mn>1400</mn></mfrac></mrow></mstyle></math>'''
    capacity='''<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><mstyle mathvariant="italic"><mrow><msub><mover accent="true"><mi>C</mi><mo>^</mo></mover><mtext>UDP</mtext></msub><mo>=</mo><mfrac><mrow><mn>1</mn><mo>−</mo><msub><mover accent="true"><mi>β</mi><mo>^</mo></mover><mtext>other, raw</mtext></msub></mrow><msub><mover accent="true"><mi>θ</mi><mo>^</mo></mover><mtext>UDP</mtext></msub></mfrac></mrow></mstyle></math>'''
    body='<p><b>이 표의 오프라인 처리량 예측은 UDP payload 단위다.</b> 4절의 식은 실제 제어기의 qdisc 바이트 단위 송신 상한식이다. 두 식을 같은 θ 또는 같은 비용 계수로 읽으면 안 된다. 자기 부하 busy 보정과 β 추정은 공유하지만, 처리량·패킷 바이트 단위와 비용 계수는 구분한다.</p>'
    body+='<div class="eq-row"><div class="eq-label">UDP 바이트당 비용</div><div class="eq-scroll">'+theta+'</div></div><div class="eq-row"><div class="eq-label">수신 처리량 예측</div><div class="eq-scroll">'+capacity+'</div></div>'
    body+='<p>UDP payload는1400B, IP/UDP를 포함한 크기는1428B다. Rup/Rdn은B/s이고, ν는송신 retries/packets다. Ocal은quiet 교정에서 고정한 <code>O_saturated_split_retry_s</code>: B2의AX1500은2.460741µs, C2의SR2는4.376449µs다. 경쟁 측정값을 맞추기 위해 다시 교정하지 않았다.</p><p>예측B/s에8을 곱해표의bit/s로 변환하고, 오차는 |예측−실측|/실측이다. 용량 자체를 비교하므로 여기에는여유 계수0.9를 곱하지 않는다. 실시간 제어는4절의별도상·하향운용비용과평균station frame bytes를 사용하고0.9여유·0.9C₀상한·EMA를 적용한다.</p>'
    return note('처리량 오차표의 실제 예측식 · 제어 상한식과 단위 구분',body)


def main():
    out=DEST/'결과/W1 실험결과';out.mkdir(parents=True,exist_ok=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dd=load('dds_confirmation/aggregation_analysis.json')['rows'];trials=load('dds_confirmation/summary.json')['trials'];ddt={r['name']:r for r in trials}
    c2_label='c2_aggregation_confirmation' if (BASE/'c2_aggregation_confirmation/aggregation_analysis.json').exists() else 'c2_scheduled'
    smoke_label='native_adaptive_final' if (BASE/'native_adaptive_final/summary.json').exists() else 'native_adaptive_smoke'
    b2=load('b2_aggregation_confirmation/aggregation_analysis.json')['rows'];c2=[r for r in load(c2_label+'/aggregation_analysis.json')['rows'] if r['name']!='quiet'];smoke=load(smoke_label+'/summary.json')['trials'];p=load('frozen_aggregation_coverage_profile.json');pk=load('frozen_radio_profile_v3_packet.json')
    c2_range=f"{min(r['error_fraction'] for r in c2)*100:.3f}~{max(r['error_fraction'] for r in c2)*100:.3f}%"
    restored=load('final_restoration.json');assert all(restored[h]['power']['restored'] and restored[h]['wire']['restored'] and not restored[h]['remaining_jobs'] for h in ['4','5'])
    title='W1 무선 입력 추가 검증 · 2026-10-13'
    style='body{margin:0;background:#f4f6fa;color:#203047;font:16px/1.8 "Malgun Gothic",sans-serif}main{max-width:1120px;margin:30px auto;background:white;padding:32px}h1{font-size:30px}h2{margin-top:38px;border-bottom:2px solid #dde5ef}table{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}td,th{padding:10px;border-bottom:1px solid #dce4ed;text-align:left;vertical-align:top}th{background:#edf2fa}.scroll{overflow:auto}.status{padding:18px;background:#fff1db;border-left:5px solid #b27719}details{border:1px solid #d4deeb;border-radius:8px;margin:16px 0;background:#f8fafc}summary{padding:12px;cursor:pointer;font-weight:bold}.note{padding:0 18px 14px}code{font:13px/1.6 Consolas,monospace;overflow-wrap:anywhere}pre{background:#edf2f8;padding:16px;white-space:pre-wrap;overflow-wrap:anywhere}a{color:#165aba}.muted{color:#587086;font-size:14px}li{margin:9px 0}@media(max-width:700px){main{margin:0;padding:18px}}@media print{main{margin:0;padding:0}details{break-inside:auto}table{font-size:10px}.scroll{overflow:visible}}'
    s='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>'+style+'</style></head><body><main><h1>'+title+'</h1>'
    s+='<p class="muted">4→5 주 측정 · 12→10 경쟁 트래픽 · Ubuntu 22.04/Humble · MT7921 · kernel 6.8.0-138 · 두 AP 149번/80MHz</p>'
    s+='<div class="status"><b>수정한 장비별 무선 입력 모델: 검증 범위에서 통과</b><p>교정에 쓰지 않은 DDS 자기 부하 6조건과 B2·C2 각 3회를 통과했다. 교정값을 고정한 뒤 측정했고, 경쟁 조건을 보정 계수의 학습에 사용하지 않았다. Fast DDS와 CycloneDDS의 실제 200ms 제어 갱신 및 결측 보류도 확인했다.</p><p><b>기존 proposal의 식을 그대로 승인한 것은 아니다.</b> 단일 패킷 고정 비용과 tx≤busy의 해석은 장비와 맞지 않았다. 새 계수는 운용 교정값이며 전체 HE/PPDU airtime의 독립 식별은 아직 완료하지 못했다. 이 한계를 포함해 W1을 조건부 판정한다.</p></div>'
    s+='<h2>1. 무엇을 끝냈고, 무엇이 달라졌나</h2>'
    s+=table(['항목','판정','근거'],[
        ['읽는 주기 원인 검사','완료','무부하와 약 100Mb/s에서 0(전후만), 0.05, 0.2, 1, 2초를 비교. 부하 중 모두 busy<TX; 5→4에서도 재현'],
        ['busy/TX 포함 관계','기존 전제 반증·운용 계약 확정','TX 전체가 raw busy에 포함된다는 가정은 사용하지 않음. AP 직접 전송에서도 busy<TX; 중계 시 busy 증가'],
        ['AP 응답·aggregation 보정','교정 완료','AP-only 3부하와 relay 연속/묶음 8조건으로 별도 교정; 수신 단말의 native RX 통계와 PHY 사용'],
        ['독립 자기 부하','6/6 기준 통과','실제 1MiB DDS; |β̂oth|≤5% 기준. 실제 발행량을 사용하고 음수 잔차를 보존'],
        ['독립 B2·C2','각 3/3 오차 기준 통과','각 30초, 중앙의 약 23초 수신 처리량. 예측 오차≤20%'],
        ['수정 adaptive 기능','두 DDS 확인','일반 adaptive의 교정 프로파일 분기에서 갱신·피드백 결측 보류·종료 복원. 기존 diagnostic 경로와 별개'],
        ['정확한 물리 airtime·보편 모델','미완료/미승인','HE duration/LTF 정보와 완전한 PPDU 관측이 없어 전체 airtime과 intrinsic O는 확정 불가'],
    ])
    s+='<h2>2. busy &lt; TX의 원인과 재현</h2><p>이 장비의 <code>busy</code>는 raw 채널 바쁨 계수이고 <code>TX</code>는 자기 송신 계수다. 드라이버는 별도 하드웨어 레지스터에서 읽어 각각 누적한다. MT_MIB_SDR9→cc_busy, MT_MIB_SDR36→cc_tx이며 busy에 TX를 합산하는 코드가 아니다. 레지스터 이름만으로 포함 관계를 확정하지 않고 다음 실측과 대조했다.</p>'
    for folder in ['polling','semantics']:
        rows=[]
        for r in load(folder+'/summary.json')['trials']:
            d=r['deltas'][r['sender']];rows.append([r['name'],f"{d['active_s']:.3f}",f"{d['busy_s']:.3f}",f"{d['tx_s']:.3f}",'—' if r.get('receiver_Mbps') is None else f"{r['receiver_Mbps']:.3f}"])
        s+=table(['조건','active s','busy s','TX s','수신 Mb/s'],rows)
    s+=note('idle·AP-only·relay·읽는 주기의 뜻과 해석','<p><b>idle</b>: 시험 UDP를 보내지 않는 기준 상태. AP beacon·관리 패킷 등까지 완전히 없는 상태라는 뜻은 아니다. <b>AP-only</b>: 4번이 공유기 주소의 닫힌 UDP 포트로 전송한다. 5번으로 사용자 데이터가 중계되지 않으므로 송신과 AP 응답의 영향을 분리한다. <b>relay</b>: 4→AP→5 사용자 데이터 전송. 읽는 주기 0은 시작/종료에만 읽는 조건이다.</p><p>AP-only에서 busy≈0.695초, TX≈6.63~6.72초가 반복되었고 relay에서는 busy≈2.45~2.46초로 늘었다. 주기 변화와 무부하 시험으로 과도한 polling이나 단순 지연 갱신만으로 이 역전을 설명하기 어렵다. <b>이 구성에서 raw busy는 전체 자기 TX를 포함하는 총 airtime이 아니며, AP 응답과 하향 중계는 반영된다</b>는 운용 계약을 사용한다. firmware 내부의 모든 CCA 상태 분류까지 해독한 결과는 아니다.</p>')
    s+='<p>원자료: '+raw('polling/summary.json')+' · '+raw('semantics/summary.json')+' · '+raw('source_reference/mt792x_mac.c','실제 커널 계열 소스 발췌')+'</p>'
    s+='<h2>3. 왜 aggregation을 반영해야 하나</h2><p>동일한 평균 UDP 부하라도 1ms 연속 송신과 100ms 묶음 송신의 busy 기여가 달랐다. 연속 부하용 보정만 적용한 별도 burst 시험에서는 자기 부하 잔차가 −8.87~−14.75%로 실패했다. 이 실패를 감추거나 β를 0으로 잘라 통과시키지 않았다.</p><p>수신 단말의 <code>rx_ampdu_cnt</code>만 쓰면 묶이지 않은 MPDU가 빠진다. 저부하 연속 전송에서 AMPDU byte/전체 RX byte 비율이 약 0.41까지 내려갔다. 따라서 전체 RX byte·MPDU·AMPDU·AMPDU byte를 함께 사용했다. <code>rx duration</code>은 실제 부하에서도 증분 0인 사례가 있어 제어 입력에서 제외했다.</p>'
    s+=note('MSDU·MPDU·A-MSDU·A-MPDU·PPDU 용어','<p><b>MSDU</b>는 MAC에 전달되는 상위 계층 데이터 단위, <b>MPDU</b>는 전송되는 MAC 프레임이다. <b>A-MSDU</b>는 여러 MSDU를 한 MPDU에 묶고, <b>A-MPDU</b>는 여러 MPDU를 한 PHY 전송 묶음에 넣는다. <b>PPDU</b>는 프리앰블과 데이터 등을 포함한 PHY 전송 단위다. ROS 1MiB 메시지 하나는 많은 RTPS/UDP 패킷으로 나뉘므로 ROS 메시지 수, IP 패킷 수, MPDU 수, PPDU 수는 같지 않다.</p><p>native 통계의 RX byte는 단말이 받은 데이터, MPDU/AMPDU 계수는 하드웨어 MIB 통계다. 바이트 정의·padding·재전송 때문에 비율이 1을 조금 넘을 수 있다. 이를 실제 aggregation 비율이라고 그대로 해석하지 않고 raw 값과 AP별 운용 교정값을 함께 보존했다. 일반 <code>rx_fragments</code> 카운터를 IP 단편화 개수로 읽지 않는다.</p>')
    s+='<h2>4. 고정한 수정 모델과 교정·검증 분리</h2>'+model_equations()
    s+=table(['계수','값','의미'],[
        ['hBA',f"{p['BA_busy_s']*1e6:.3f} µs/BA",'AP 응답의 effective busy 기여'],
        ['γ',f"{p['RX_data_scale']:.6f}",'수신 데이터/PHY 시간 proxy 보정'],
        ['hPPDU',f"{p['RX_AMPDU_busy_s']*1e6:.3f} µs/추정 묶음",'묶음당 운용 비용; intrinsic 프리앰블 시간 아님'],
        ['idle fraction',f"{p['idle_busy_fraction']*100:.4f}%",'무부하 기준의 busy 비율'],
        ['k / AX1500','1.05','AX의 native 바이트 포함 관계를 위한 운용 정규화'],
        ['k / SR2','1.207412','SR2 quiet만으로 정함; C2 경쟁 자료로 맞추지 않음'],
        ['Oup / Odown',f"{pk['O_up_s']*1e6:.3f} / {pk['O_down_s']*1e6:.3f} µs",'상·하향을 나눈 운용 비용; retry는 상향에만 적용'],
    ])
    s+=note('교정 자료와 독립 검증 자료 · 왜 후보 모델들을 남겼나','<p>AP-only 100/200/300Mb/s와 idle로 AP 응답 계수를 구했다. 별도의 relay 평균 부하 0.2/0.4/0.6/0.8, 연속/묶음 전송 8조건으로 나머지 계수를 구한 뒤 <code>frozen_aggregation_coverage_profile.json</code>에 고정했다. C₀는 당일 UDP30초×3의 중앙값 <b>333.833Mb/s</b>다. 10월12일의 326.893Mb/s를 덮어쓰지 않았다.</p><p>처음 DDS 확인은 모델 개발 중 진단으로 보존했고, 고정 후 <code>dds_confirmation</code>의 새 6조건을 다시 측정했다. B2는 고정 이후 새 3회, C2는 계수 학습에 쓰지 않았던 3회다. C2 AP별 바이트 정규화만 경쟁이 없는 quiet로 정했다. 시간 순서상 C2는 계수 고정 전에 수집된 별도 자료이며, 계수 고정 뒤 새 수집한 완전 전향 검증이라고 부르지 않는다. C2의 별도 quiet에는 그날 AP 처리량 교정도 사용했다.</p><p>동일 부하에서도 패킷 묶음에 따라 비용이 달라지므로 proposal의 단일 O를 물리적 상수로 해석할 수 없다. 여기서 O와 h는 지정 장비·AP·대역폭·패킷 크기의 effective 계수다. 적용 범위를 바꾸면 다시 교정·검증해야 한다.</p>')
    s+='<p>교정 프로파일: '+raw('frozen_aggregation_coverage_profile.json')+' · '+raw('frozen_radio_profile_v3_packet.json')+'</p>'
    s+='<h2>5. 독립 DDS 자기 부하 확인</h2>'
    rows=[]
    for r in dd:
        q=ddt[r['name']];rows.append([r['name'],q['planned'],q['succeeded'],q['received'],f"{r['beta_unclipped']*100:.3f}%",'통과' if r['self_pass'] else '실패'])
    s+=table(['조건','예정 메시지','발행 성공','고유 수신','β̂oth raw','|β|≤5%'],rows)
    s+=note('자기 부하 시험의 조건과 발행 감소 해석','<p>4→5 Wi-Fi, <code>std_msgs/msg/UInt8MultiArray</code> 1MiB 무작위 바이트에 순번·발행 시각을 기록했다. QoS는 RELIABLE·KEEP_ALL·VOLATILE, Static XML, 발행15초이며 요청 부하는 C₀의0.2/0.5/0.8배다. 교정된 stock runtime의 실제 라이브러리 해시를 송수신 maps와 대조했다. 외부 경쟁 트래픽은 없다.</p><p>Fast의0.8 조건은 예정478개 중418개 발행했다. 받은418개는 모두 성공 발행한 메시지지만 <b>요청 발행률을 달성했다는 뜻은 아니다</b>. 자기 부하 계산은 실제 패킷 계수에 기초한다. DDS의 보관함·호출 대기로 부하가 줄어든 결과를 송신 손실 0 또는 최적 성능과 혼동하지 않는다.</p><p>β는 다른 트래픽이 없을 때 0 근처여야 한다. −0.243%를 0으로 바꾸지 않았고 최대3.141%까지 관측했다. 본 시험의5% 허용 기준은 이 재검증에서 명시한 공학적 기준이며 원문이 정확히5%를 규정한 것은 아니다. 이번 시계 상태로 종단 지연은 승인하지 않았으므로 지연 수치를 비교하지 않는다.</p>')
    s+='<p>'+raw('dds_confirmation/summary.json')+' · '+raw('dds_confirmation/aggregation_analysis.json')+'</p>'
    s+='<h2>6. B2·C2의 독립 예측 오차</h2>'
    for label,rows in [('B2',b2),('C2',c2)]:
        s+=table([label+' 조건','실측 Mb/s','예측 Mb/s','절대 상대 오차','20% 기준'],[[r['name'],f"{r['actual_bps']/1e6:.3f}",f"{r['prediction_bps']/1e6:.3f}",f"{r['error_fraction']*100:.3f}%",'통과' if r['error_fraction']<=.2 else '실패'] for r in rows])
    s+=capacity_validation_note()
    s+=note('B2·C2·quiet·측정 구간의 정의','<p><b>B2</b>: 주 쌍4/5는 AX1500, 경쟁 쌍12/10은 별도 SR2 AP. 두 AP가149번/80MHz를 공유하며 경쟁 UDP를2초 켜고2초 끄는 패턴이다. <b>C2</b>: 네 단말 모두 SR2에서 경쟁 쌍이 약0.9C₀ UDP를 전송한다. 같은 AP 자원을 놓고 경쟁한다. <b>quiet</b>: 해당 토폴로지와 AP를 유지하고 경쟁 UDP만 끈 기준 상태다. 두 AP가 켜져 있어도 B2 경쟁 트래픽이 꺼질 수 있다.</p><p>주 iperf UDP1400B 포화 측정은30초다. 경쟁 source/sink와 통계 측정을 미리 예약하고 무선 부하 중 PC의 TCP 제어를 하지 않았다. 중앙 수신 interval3..27의 약23초 처리량과 대응하는 약24초 source 계수 창을 사용했다. 각 회차 client 성공·30초 지속·경쟁 실행·버퍼 복원을 검사했다. 두 구간의 길이를 같다고 가정한 총 byte 나눗셈은 하지 않는다.</p><p>초기 직접 제어 B2와 짧아진 C2, 시작 시계 오차/준비 실패 회차는 원자료로 보존하고 공식 오차 표에서는 제외했다. PC 시계가 단말보다 약124초 앞서 있어 예약 시각을 host별 오프셋으로 보정했다. 이 정렬은 장시간 radio 평균용이며 1ms 종단 지연 동기화 승인으로 쓰지 않는다. B2/C2에서 β가 양수인 것은 경쟁을 관측한 결과다. raw 파일의 <code>self_pass=false</code>는 경쟁 조건에서 자기 부하 전용 기준을 만족하지 않는다는 뜻이며, 20% 용량 예측 오차 실패와 다르다.</p>')
    s+='<p>'+raw('b2_aggregation_confirmation/summary.json')+' · '+raw('b2_aggregation_confirmation/aggregation_analysis.json')+' · '+raw('c2_scheduled/summary.json')+' · '+raw('c2_scheduled/aggregation_analysis.json')+'</p>'
    s+='<h2>7. 수정 adaptive의 실제 갱신과 결측 보류</h2>'
    s+=fq_explanation()
    s+=table(['DDS','예정/발행/수신','갱신 횟수','갱신 간격 중앙값','피드백 중단 보류','qdisc 복원'],[[r['rmw'],f"{r['planned']}/{r['succeeded']}/{r['received']}",r['updated'],f"{r['median_update_interval_s']*1000:.2f} ms",r['stale_feedback_holds'],'확인' if r['qdisc_restored'] else '실패'] for r in smoke])
    s+=note('normal adaptive·fixed·diagnostic·gate·hold의 뜻','<p><b>Static</b>은 입력값으로 계산한 DDS 정적 XML이다. <b>fixed</b>는 Static에 HTB/fq 고정 상한을 붙인 조건이다. <b>adaptive_diagnostic</b>은10월12일 임시 가정을 사용한 별도 진단 경로이며 정식 검증 근거로 승격하지 않았다.</p><p>이번에는 <code>rospacer govern --mode adaptive</code>의 새 native 교정 입력 경로를 실행했다. 수신5번이 약200ms마다 통계와 RX PHY를 <b>유선50.1→50.2 UDP55910</b>으로 전달한다. DDS 데이터는 XML의 Wi-Fi interface 지정으로 무선4→AP→5에 보낸다. 상한은 최대0.9C₀=300.450Mb/s이고 관측 창은 약3초, 최소2초부터 계산한다.</p><p><b>gate</b>는 교정 및 장비 범위가 검증됐는지 확인하는 관문이다. kernel·module srcversion·reader SHA·AP MAC·149번/80MHz·1MiB 조건을 고정했다. 승인되지 않은 프로파일은 qdisc 설치 전에 거부하는 검사도 추가했다. 기존 입력 경로의 미승인 gate를 임의로 해제하지 않는다.</p><p><b>hold</b>는 입력이 부족할 때 마지막 유효 상한을 유지하고 새 계산을 하지 않는 동작이다. 처음2초의 warm-up, 자체 패킷이 없는 창, 수신 피드백이0.6초 이상 오래된 경우를 로그에 남긴다. 수신 피드백을33초 후 끊고 제어기는43초 유지해 각51회의 결측 보류를 확인했다. 손실된 입력을0으로 만들어 경쟁이 없다고 계산하지 않았다.</p><p>동작 중 상한 범위는 Fast122.935~300.450Mb/s, Cyclone64.478~300.450Mb/s였다. 이 변동은 입력·PHY·교정식·평활의 결과이며 DDS 성능 순위가 아니다. 이번 검사는 손상 없는0.2C₀ 부하의 기능 시운전이다. F 단계의 동적 경쟁 추종·adaptive 대비 fixed 성능 우위·배출 제어 전체를 검증한 시험으로 해석하지 않는다.</p>')
    s+='<p>'+raw('native_adaptive_smoke/summary.json')+' · '+raw('native_adaptive_smoke/qualified_input_profile.json')+' · '+raw('native_adaptive_smoke/fastdds/4/govern.csv','Fast 제어 CSV')+' · '+raw('native_adaptive_smoke/cyclonedds/4/govern.csv','Cyclone 제어 CSV')+'</p>'
    s+='<h2>8. 독립 프레임 참조와 물리적 해석의 한계</h2><p>5번에서 관리 인터페이스와 같은149번/80MHz로 임시 monitor를 만들고18초 캡처했다. UDP100Mb/s·10초의4→5 중계가 포함됐다. 80,754프레임, kernel capture drop0이며 monitor 삭제를 확인했다. 독립 PHY 참조는 AP→5 HE 데이터13,031개에서 MCS11·NSS2·80MHz·GI0.8µs·1201Mb/s, A-MSDU를 확인했다. 흔한 MAC 프레임 길이는10,188B로 여러 UDP 데이터의 묶음이었다.</p><p><b>AP b0:38:6c:7d:f5:74(AX1500)→3c:0a:f3:02:e4:c7(5번)</b>은 하향 사용자 데이터, <b>AP→3c:0a:f3:02:d9:3b(4번)</b>은 원송신자에 대한 BlockAck 방향이다. 후자의 BA12,959개는24Mb/s·해석 duration32µs였다. AP-only에서 교정한 effective BA31.754µs는 이 참조와 약0.77% 차이다. 이는 AP 응답 비용의 한 구성요소를 지지한다.</p><p>HE 데이터의 <code>wlan_radio.duration</code>은 비어 있고 LTF 정보도 완전하지 않았다. AMPDU reference가 각 데이터에 유일하게 붙는 현상을 물리적 PPDU 전체 분리 증명으로 간주하지 않았다. <b>전체 HE airtime 합과 단일 intrinsic O는 확정할 수 없다.</b> native RX duration의0 증분도 실제 수신 airtime0이 아니다. 별도 관측 장비 구매가 꼭 필요한지는 현재 자료만으로 단정할 수 없으며, 먼저 완전한 HE/PPDU 메타데이터를 제공하는 관측 경로가 필요한 상태다.</p><p>'+raw('rx_reference/air.pcap')+' · '+raw('rx_reference/frames_fields.txt')+'</p>'
    s+='<h2>9. 복원·재현·W1 판정</h2><p>4·5번 전원 guard 종료 영수증과 최종 조회에서 Wi-Fi 절전on, CPU powersave, rmem/wmem212992, Wi-Fi root qdisc noqueue, 실험 프로세스 종료, 임시 monitor 없음, AX1500 연결을 확인했다. 임시50.1/50.2 주소만 제거했고 랜 케이블은 유지했다. NetworkManager 저장 프로파일과 원래 연구 DDS 설치는 수정하지 않았다. 기존 서명 survey 수정 모듈과 MOK 신뢰는 유지했다.</p><p>12·10번 경쟁 프로세스도 유한 실행 후 종료하며 각회 sysctl 복원을 확인했다. 최종 rmem/wmem은212992였다. 이번 작업은 드라이버를 추가 수정하거나 일반 sudo 권한을 확대하지 않았다.</p><p>결과와 해시는 '+raw('final_restoration.json','최종 복원 JSON')+' 및 <code>ROSPacer/runs/'+BASE.name+'</code>에 있다. source 기준 커밋: <code>'+commit+'</code>. 실행 시 소스 SHA는 각 summary/provenance에 보존한다. 소스/단위·결측·신원 gate의 자동 검사38개가 통과했다.</p><p><b>판정:</b> 이번에 요청한 polling·포함 관계·aggregation 교정·별도 자기 부하/B2/C2·수정 제어기 기능 검사는 현재 장비 범위에서 끝났다. 원 proposal의 tx≤busy 및 단일 물리 O 가정은 수정해야 한다는 연구 결과다. 따라서 기존 원식을 그대로 둔 W1 전체 승인이나 모든 환경의 adaptive 검증 완료라고 표시하지 않는다. 물리적 O의 전체 독립 비교는 남은 확인 항목이며, 다음 성능 실험은 이 조건부 범위와 제어 입력을 명시해 수행할 수 있다. Zenoh는 사용자 개발 순서에 따라 후속이다.</p>'
    if c2_label=='c2_aggregation_confirmation':
        s=s.replace('C2는 계수 학습에 쓰지 않았던 3회다.','C2도 계수 고정 이후 새로 측정한3회다.')
        s=s.replace('시간 순서상 C2는 계수 고정 전에 수집된 별도 자료이며, 계수 고정 뒤 새 수집한 완전 전향 검증이라고 부르지 않는다.','처음 C2는 계수 고정 전에 수집됐으므로 보조 자료로 남겼고, 최종 판정에는 계수 고정 후 새3회를 사용했다. 기존 quiet에서 정한 바이트 정규화와 용량 비용을 고정하고 새 경쟁 결과를 맞추는 데 사용하지 않았다.')
        s=s.replace('c2_scheduled/summary.json','c2_aggregation_confirmation/summary.json').replace('c2_scheduled/aggregation_analysis.json','c2_aggregation_confirmation/aggregation_analysis.json')
    if smoke_label=='native_adaptive_final':
        s=s.replace('native_adaptive_smoke/',smoke_label+'/')
        ranges=[]
        for r in smoke:
            rows=list(csv.DictReader((BASE/smoke_label/r['rmw']/'4/govern.csv').open()))
            ranges.append(f"{r['rmw']} {min(float(x['cap_packet_Bps']) for x in rows)*8/1e6:.3f}~{max(float(x['cap_packet_Bps']) for x in rows)*8/1e6:.3f}Mb/s")
        s=s.replace('Fast122.935~300.450Mb/s, Cyclone64.478~300.450Mb/s',' · '.join(ranges))
        s=s.replace('각51회의 결측 보류',f"Fast{smoke[0]['stale_feedback_holds']}회·Cyclone{smoke[1]['stale_feedback_holds']}회의 결측 보류")
    s=s.replace('자동 검사38개','자동 검사39개')
    if (out/SENDER_NAME).exists():
        s+='<p id="sender-prototype-reference"><a href="'+SENDER_NAME+'">별도 Sender-only 프로토타입 개발 진단</a>: 무경쟁 DDS 추정 확인, B2 가시성 부족으로 보류. 본 Receiver-assisted 검증과 구분한다.</p>'
    s+='</main></body></html>';(out/NAME).write_text(s,encoding='utf8')
    path=DEST/'W1 보고서.html';original=path.read_text(encoding='utf8');backup=BASE/'W1_report_before_radio_addendum.html'
    if not backup.exists():backup.write_text(original,encoding='utf8')
    else:original=backup.read_text(encoding='utf8')
    original=re.sub(r'<div class="status">.*?</div>', '<div class="status"><b>10월13일 갱신: 수정 무선 입력 모델은 범위 내 통과 · W1 전체 판정은 조건부</b><p>교정에 사용하지 않은 1MiB DDS 자기 부하6조건과 B2·C2 각3회의 오차 기준을 통과했다. 두 DDS의 실제 adaptive 갱신·결측 보류·복원도 확인했다. 기존 tx≤busy 가정과 단일 물리 O는 승인하지 않았으며 장비별 운용 모델로 수정했다. 정확한 HE/PPDU airtime 합의 독립 식별은 남아 있다.</p><p><a href="결과/W1 실험결과/'+NAME+'">10월13일 추가 검증: 조건·수정식·실측값·판정 전체 보기</a></p></div>',original,count=1,flags=re.S)
    original=original.replace('이 보고서의 측정 기준일: 2026년 10월 12일','측정 기준일: 2026년 10월 12일 · 무선 입력 추가 검증: 10월 13일')
    original=re.sub(r'<p class="revision">측정:2026-10-12.*?</p>','<p class="revision">10월12일 수치는 당시 측정값으로 보존 · 최신 무선 입력 판정:2026-10-13 · 서로 다른 날짜의 교정값을 합치지 않음</p>',original,count=1,flags=re.S)
    original=original.replace('<h2 id="section-1">핵심 결과</h2>','<h2 id="radio-20261013">10월13일 무선 입력 재검증</h2>'+table(['검증','결과'],[['실제 DDS 자기 부하6조건','β raw −0.243%~3.141%, 모두±5% 이내'],['B2 독립3회','예측 오차8.698~10.795%, 모두20% 이내'],['C2 별도3회','예측 오차2.239~5.415%, 모두20% 이내'],['수정 adaptive 시운전','Fast/Cyclone각120/120수신; 갱신106/121회; 각51회 피드백 결측 보류']])+'<p>부하 모양에 따른 aggregation과 수신측 PHY·native 통계를 반영했다. 새 상세 보고서의 가정과 검증 범위를 함께 읽어야 한다. <a href="결과/W1 실험결과/'+NAME+'">상세 보고서</a></p><h2 id="section-1">10월12일 핵심 결과</h2>')
    original=original.replace('처리량 C₀는 측정했으나 고정 비용 O는 조건부 추정이며 독립 식별은 미완료다.','C₀ 측정과10월13일 운용 비용 교정·별도 부하 검증을 완료했다. 단일 intrinsic O의 전체 HE airtime 독립 식별은 미완료다.')
    original=original.replace('<td>6. 무선 통계·중계·적응형</td><td>미통과</td><td>149번 통계 채널 귀속은 수정·확인했다. 자기 부하에서 기존 tx≤busy 전제가 성립하지 않아 정식 적응형 모델 승인은 보류한다. 10번 독립 관측과 제한된 적응형 진단은 수행했다.</td>','<td>6. 무선 통계·중계·적응형</td><td>수정 모델 범위 내 통과</td><td>149번 귀속 확인 후 polling·AP응답·aggregation을 교정했다. 별도 DDS 자기 부하6조건과 B2/C2각3회 통과. 두 DDS native 교정 adaptive 갱신·결측 보류 확인. 원식과 모든 AP의 보편 모델 승인은 아님.</td>')
    original=write_section(original,'section-3','<p><b>10월13일 재검증 완료 항목:</b> 읽는 주기·idle·일정 부하를 바꾸어 busy&lt;TX를 재현했고, AP 응답·중계와 aggregation을 반영해 모델을 수정했다. 계수를 고정한 별도 DDS 자기 부하/B2/C2 자료는 명시한 기준을 통과했다. 실제 adaptive 두 DDS 기능 검사도 끝났다.</p><p><b>남은 물리적 확인:</b> 전체 HE/PPDU airtime과 intrinsic O의 독립 식별. AP 응답 BA의32µs 참조는 확보했으나 HE duration/LTF 정보는 부족하다. 기존 원식의 전제를 유지한 채 W1 전체 통과로 처리하지 않는다. <a href="결과/W1 실험결과/'+NAME+'">수정식·검증 자료·적용 범위</a></p>')
    original=original.replace('<h2 id="section-3">미통과 원인과 다음 검증</h2>','<h2 id="section-3">수정 모델의 최신 판정과 남은 물리적 확인</h2>')
    # Historical sections retain measurements, but their scope is explicit.
    for id in ['section-11','section-12','section-13','section-14','section-15']:
        original=re.sub(r'(<h[23] id="'+id+r'">)(.*?)(</h[23]>)',lambda m:m[1]+'10월12일 기록 · '+m[2]+m[3]+'<p class="revision">아래는10월12일 진단이다. 최신 수정 모델 판정은 <a href="#radio-20261013">10월13일 재검증</a>을 따른다.</p>',original,count=1)
    original=original.replace('자기부하0.2..0.8 시험 수행; 기존 식 전제 미통과, 의미 검증 남음','기존 전제는 반증.10월13일 polling/AP-only/relay로 운용 계약 정리; TX 재차감 금지')
    original=original.replace('측정과 진단용 계산을 기록; 정식 오차는 입력 전제 실패로 미확정','10월13일 수정 모델 별도 검증: B2 8.70~10.79%, C2 2.24~5.41%; 모두20% 이내. 원식을 그대로 승인한 결과 아님')
    original=original.replace('일반 adaptive 게이트 거부 유지. 제한된 해석의 diagnostic에서각230회 갱신·보류0·156/156수신 확인. 정식 모델승인과구분','기존 미승인 입력 경로 gate 유지. 교정 profile이 승인된 native 입력 경로에서 Fast/Cyclone갱신106/121회·각120/120수신·피드백 결측 보류 확인. 적용 범위 한정')
    original=write_section(original,'section-19','<p><b>10월13일 복원 완료:</b> 4·5 Wi-Fi절전on, CPU powersave, rmem/wmem212992, root qdisc noqueue, 실험 프로세스 종료, 임시monitor 없음, AX1500 복귀를 확인했다. 임시 유선50.1/50.2 주소를 제거했고 랜 케이블은 유지했다. 12·10 경쟁 프로세스와 소켓 상한도 복원했다. 서명 survey 수정 모듈/MOK와 기존 연구 설치는 유지한다.</p><p><b>앞서 남았던 무선 입력 작업:</b> polling·busy/TX 포함 관계·aggregation 운용 교정·별도 자기 부하/B2/C2·수정 adaptive 기능 검사는 완료했다. 상세 수치와 가정은 <a href="결과/W1 실험결과/'+NAME+'">10월13일 추가 보고서</a>에 있다.</p><p><b>아직 승인하지 않은 부분:</b> 정확한 전체 HE/PPDU airtime과 단일 intrinsic O의 물리적 독립 식별, 다른 AP·driver·payload로의 일반화, adaptive와 fixed의 정식 성능 비교·동적 추종 및 전체 배출 제어. 마지막 두 항목은 후속 성능/구현 단계이며 이 시운전으로 미리 성공 판정하지 않는다. Zenoh는 사용자 순서대로 후속이다.</p><p>10월12일 원자료와 시계·기존 비교군 수치는 그대로 보존했다. 새 원자료는 <code>ROSPacer/runs/'+BASE.name+'</code>. 소스 기준 커밋 <code>'+commit+'</code>, 실제 실행 SHA는 각 provenance/summary에 보존했다.</p><p>이전 보고서는 각 날짜의 기록이다. 최신 판정은 본문과10월13일 추가 보고서를 따른다.</p><ul>'+''.join('<li><a href="결과/W1 실험결과/'+n+'">'+n+'</a></li>' for n in ['W1 구현 전제 검증_261012.html','W1 149채널 B2 추가 검증_261012.html','W1 4·5번 유선 동기화 및 계수기 검증_261012.html'])+'</ul>')
    original=original.replace('10월12일 기록 · 10월12일 기록 · ','10월12일 기록 · ')
    for n in ['W1 구현 전제 검증_261012.html','W1 149채널 B2 추가 검증_261012.html','W1 4·5번 유선 동기화 및 계수기 검증_261012.html']:
        original=original.replace('href="결과/'+n+'"','href="결과/W1 실험결과/'+n+'"')
    original=original.replace('예측 오차2.239~5.415%, 모두20% 이내','예측 오차'+c2_range+', 모두20% 이내')
    original=original.replace('C2 2.24~5.41%; 모두20% 이내','C2 '+c2_range+'; 모두20% 이내')
    if smoke_label=='native_adaptive_final':
        updates=f"{smoke[0]['updated']}/{smoke[1]['updated']}"
        original=original.replace('갱신106/121회',f'갱신{updates}회').replace('갱신106/121회',f'갱신{updates}회')
        original=original.replace('각51회 피드백 결측 보류',f"Fast{smoke[0]['stale_feedback_holds']}회·Cyclone{smoke[1]['stale_feedback_holds']}회 피드백 결측 보류")
    original=original.replace('<h2 id="section-9">W1 전용 역압 실험</h2>', '<h2 id="section-9">W1 전용 역압 실험</h2>'+fq_explanation(),1)
    if (out/SENDER_NAME).exists():
        original=original.replace('<h2 id="radio-20261013">10월13일 무선 입력 재검증</h2>','<h2 id="radio-20261013">10월13일 무선 입력 재검증</h2><p id="sender-prototype-reference"><a href="결과/W1 실험결과/'+SENDER_NAME+'">별도 Sender-only 프로토타입 개발 진단</a>: 무경쟁 DDS 추정 확인, B2 가시성 부족으로 보류. 기존 Receiver-assisted 판정을 대체하지 않는다.</p>',1)
    path.write_text(original,encoding='utf8')
    # Rebase file links when copying the entry report three levels deeper.
    def rebase(m):
        v=m[1]
        if v.startswith(('http:','https:','#','data:','/')):return m[0]
        if v.startswith('결과/W1 실험결과/'):v=v[len('결과/W1 실험결과/'):]
        elif v.startswith('../'):v='../../'+v
        elif v.startswith('결과/'):v='../'+v[len('결과/'):]
        return 'href="'+v+'"'
    nested=re.sub(r'href="([^"]+)"',rebase,original)
    (out/'W1 보고서.html').write_text(nested,encoding='utf8')
    print(json.dumps({'addendum':str(out/NAME),'main':str(path),'nested_copy':str(out/'W1 보고서.html')},ensure_ascii=False))


if __name__=='__main__':main()
