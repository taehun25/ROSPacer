"""Reader-facing units and derivation for the 12 October fq comparison."""


def fq_explanation():
    return '''<details class="reader-note" id="fq-limit-explanation"><summary>fq 한도 100·1,490·5,960의 단위, 계산 근거와 해석</summary><div class="note note-body">
<p>아래 값은 <b>10월12일 W1 전용 역압 시험</b>에서 사용한 설정이다. 10월13일에 같은 비교를 다시 측정했다는 뜻은 아니다. <code>flow_limit</code>는 fq의 흐름별 대기 패킷 한도, <code>limit</code>는 fq 전체의 대기 패킷 한도다. 단위는 Linux가 fq 큐에 보관하는 패킷/SKB 수이며, 바이트·ROS 메시지 수·발행률·무선 MPDU/PPDU 수가 아니다.</p>
<div class="scroll"><table><thead><tr><th>설정</th><th>실제 값과 단위</th><th>출처 및 의미</th></tr></thead><tbody>
<tr><td><code>flow_limit</code> 기본값 비교군</td><td>100 패킷/흐름</td><td>Linux fq의 기본 흐름별 한도. 정적 모델로 계산한 최적값이 아니다.</td></tr>
<tr><td><code>flow_limit</code> 설계 비교군</td><td>1,490 패킷/흐름</td><td>설정 생성기가 메시지 크기·reader 수·단편 크기와 수리 여유를 반영한 설계값. 하나의 fq 흐름에 최대 1,490개 패킷이 대기하도록 설정한다.</td></tr>
<tr><td><code>limit</code> 두 비교군 공통</td><td>5,960 패킷/fq 전체</td><td>생성기의 전체 큐 여유 규칙. 흐름별 한도만 비교하기 위해 두 조건 모두 같은 값을 적용했다. Linux fq의 기본 전체 한도는 10,000 패킷이다.</td></tr>
</tbody></table></div>
<p><b>실제 계산:</b> 메시지는 1,048,576 B, reader는 1개, 모델의 단편 단위는 1,472 B, 임시 RTPS 헤더 비용은 64 B, MTU는 1,500 B, 생성된 송신 소켓 버퍼 입력은 163,447 B였다. 단편당 모델상 데이터는 <i>1,472 − 64 = 1,408 B</i>다.</p>
<p style="font-style:italic;overflow-wrap:anywhere">단일 메시지의 근사 패킷 수 = ⌈1,048,576 / 1,408⌉ = 745<br>
소켓 버퍼/MTU 항 = ⌈163,447 / 1,500⌉ = 109<br>
flow_limit = max(109, 2 × 745) = 1,490<br>
limit = max(4,096, 4 × 1,490) = 5,960</p>
<p>생성기 일반식은 <i>flow_limit = max(⌈Qtx / MTU⌉, 2 × ⌈payload × readers / (unit − header)⌉)</i>, <i>limit = max(4,096, 4 × flow_limit)</i>이다. 여기서 <i>Qtx</i>는 생성기의 송신 소켓 버퍼 바이트 입력이다. 2배는 메시지 버스트와 수리를 위한 공학적 여유이고, 4배는 전체 큐 여유 규칙이다. 실제 송신 흐름이 4개라고 측정했다는 뜻은 아니다.</p>
<p><b>정적 최적화와의 관계:</b> 모델 입력을 사용하는 설정 생성기의 출력이지만, proposal 식만으로 유일하게 정해진 수학적 최적값이나 sweep으로 확정한 전역 최적값은 아니다. 실제 DDS의 단편·직렬화·헤더가 다를 수 있으므로 745는 근사치이며, 1,490이 정확히 두 ROS 메시지를 담는다고 보장하지 않는다. 본 역압 시험은 이 설계 한도가 100 패킷보다 버스트 손실을 줄이는지 확인한 시험이다.</p>
<p><code>bp_default100</code>과 <code>bp_design</code>은 같은 Static XML·QoS·소켓 버퍼·DDS 보관함 설정과 같은 HTB 상한을 사용했다. <code>bp_default100</code>도 DDS Default 조건이 아니며, fq의 <code>flow_limit</code>만 100으로 바꾼 비교군이다.</p>
<p>근거: <code>rospacer/model.py</code>의 생성식 및 각 역압 run의 <code>summary.json</code>. 단위와 Linux 기본값: <a href="https://man7.org/linux/man-pages/man8/tc-fq.8.html">tc-fq 매뉴얼</a>.</p>
</div></details>'''
