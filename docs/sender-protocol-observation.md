# Sender-host RTPS observation (2026-10-14)

`rospacer.sender_protocol` is a finite observation prototype. It does not install
HTB, reconstruct wireless airtime, or replace the validated receiver-assisted
path. The original wireless-only sender estimator remains unqualified.

Deployment requirement confirmed by the user on 2026-10-14: no additional
receiver-side ROSPacer/statistics feedback program and no operational dependence
on wired feedback. Changing the feedback transport to Wi-Fi would not remove
the receiver-program dependency. Preserve receiver-assisted evidence as a
reference; qualify this natural-DDS-feedback candidate independently before
claiming functional or performance replacement.

## Input contract

The sender observes its normal managed Wi-Fi interface with an AF_PACKET socket.
Outgoing DATA_FRAG identifies the writer and sequence history; incoming natural
DDS ACKNACK/NACK_FRAG provides protocol-layer reader feedback. No custom receiver
statistics service or additional radio is used. Natural receiver protocol
feedback is still feedback: this changes the proposal's wireless-only passive
input contract rather than proving that contract sufficient.

Scope: one unencrypted RTPS/UDP user writer, one reader/IPv4 peer, 1 MiB
UInt8MultiArray, RELIABLE KEEP_ALL VOLATILE, no GAP. DDS security, IP fragmentation,
multiple writers/readers, capture drops, history overflow or unknown history
cause a hold. This prototype is not a generic RTPS dissector.

Only an observed sequence strictly below the cumulative ACK base is confirmed.
First-fragment observation is required. Zero bitmap bits above the base are not
promoted to positive delivery evidence. GAP invalidates cumulative completion
inference. A protocol confirmation does not establish receiver application
callback execution. Application sequence sets are checked offline for validation;
they never feed the observer online.

## Bounded shadow policy

The observation loop samples about every 200 ms. Its recommendation starts at a
fixed packet-rate ceiling of 305.754201811 Mb/s, with a 10% floor. This ceiling
is an explicitly registered trial bound using 0.9 times an earlier measured
C0=339.726890901 Mb/s; it is not an ACK-derived capacity estimate and is not the
Static generator's application-to-packet conversion.

Pending data older than 0.5 s, or stale ACKs with pending data, recommends a factor
0.8 decrease. Recent valid ACKs permit a bounded factor 1.02 increase. Missing
scope/capture validity holds the previous recommendation. A sole final sample
whose cumulative base equals that sequence and has no missing bitmap/recent
fragment repair is explicitly **unconfirmed**: v3 holds rather than repeatedly
inferring congestion from this ambiguous final ACK boundary. This can also hold
on real single-sample loss without explicit repair feedback. It is a limit of
inference, not proof of no loss or a safety guarantee for a live controller.

ACK lag is sender first-fragment-to-ACK time, including DDS scheduling and queues.
The window byte rate measures ACK confirmation progress, not packet arrival
rate or maximum capacity. beta, theta, AP downlink PHY and aggregation are not
estimated by this module.

## Reproduction and evidence

Local unit checks: `python -m unittest discover -s tests`.
The finite Linux root observer entry point is `python3 -m
rospacer.sender_protocol --help`. It writes a CSV, event JSONL and Ethernet
snaplen-320 PCAP. It never creates a monitor interface or mutates qdiscs.

`tools/w1_protocol_trial.py` runs a finite laboratory shadow trial with pinned
Fast DDS 2.6.11 or CycloneDDS 0.10.5, Static XML, sender4 -> AX AP -> receiver5.
`--mask` suppresses only ACK events in the observer for five seconds; DDS and
network traffic remain intact. It is an input-loss fault test, not an outage
experiment. `--hz 20` is a higher offered DDS load, not B2/C2 competition or a
demonstrated saturation experiment.

`runs/w1_20261014_sender_bounded/protocol_v2.json` and `protocol_v3.json` freeze
separate revisions before new trials. v2 failures remain recorded; v3 tests
do not relabel them as successes. The exact confirmation-set check is distinct
from the predeclared >=95% fraction gate. The latter alone cannot qualify an
automatic pacing controller.

`tools/w1_protocol_analyze.py` maps first DATA_FRAG payloads to application
sequence numbers, then compares confirmations to the final receiver sequence
set offline. `tools/w1_protocol_finish.py` restores only owned campaign state,
audits both machines, and preserves source and raw-evidence hashes.

Further qualification requires independent B2/C2, changing competing load,
prolonged loss/reconnection, live HTB response and fairness/recovery checks under
this changed contract. Even success there would not identify original physical
O or solve wireless-only PHY/aggregation observability.

Protocol references: CycloneDDS 0.10.5 `q_protocol.h` and Fast DDS 2.6.11
`ReaderProxy.cpp`; keep cumulative confirmation conservative rather than
guessing the meaning of a final bitmap boundary.

## 2026-10-14 live B2/C2 follow-up

`rospacer.sender_ack_live` adds explicitly selected finite experimental HTB
actuation. It uses the same ACK policy and an independent expiry guard. It is
not enabled as the production governor. Raw data and criteria are in
`runs/w1_20261014_ack_live`. Competition must start before main traffic and must
have nonzero UDP interval bytes afterward; a failed competitor is excluded.

An initial Cyclone B2 observation failed because a 1346-byte outgoing coalesced
RTPS frame was clipped to 320 bytes before decoding later control messages.
The correction decodes complete MTU frames, stores inbound and control/error
frames fully, and retains only data-only outgoing prefixes in the PCAP. Initial
failures remain preserved. New held-out repeats distinguish capture revisions.

ACK confirmations became exact in final B2/C2 trials, but that alone is not
capacity tracking. B2 often made no actual cap change. One valid Cyclone C2
ACK run published238 versus393 with Fixed; all were received, but publication
reduction remains a material limit. Large gains with zero cap changes or
different actual competing throughput cannot be attributed to ACK control.

## Minimal offline receiver PHY alternative

`rospacer.peer_phy` records/attaches a standard receiver `iw link` PHY reading.
`python -m rospacer apply-peer-phy --help` exposes the calibration-file path.
No receiver-side telemetry daemon or operational wired feedback is needed.
Existing sender model guards are not automatically approved by this correction.

`rospacer.minphy_radio` is a separate scoped operating-budget model. Receiver
PHY is a frozen calibration value. Online inputs are sender survey active/busy/TX
and station bytes/packets/retries/PHY. The MT7921 raw busy contract excludes own
TX; no TX<=busy ordering is assumed. Effective costs are fitted from source-only
idle/self-load calibration and standard receiver iperf interval goodput. They
are neither physical PPDU duration nor independently identified intrinsic O.

The first per-packet relay-cost variant failed a fresh clean validation with
raw residuals approximately-0.06..-0.09. It remains recorded as a failure.
The second variant uses calibrated source TX duration scaled by same-window
byte/retry-weighted uplink PHY versus frozen downlink PHY. Its coefficients
were fitted only on the original calibration data, followed by fresh validation.
Capacity-budget error and the self/other occupancy decomposition are separate
gates: clean residual occupancy around0.10 does not prove other traffic.

`rospacer.minphy_live` is a finite **experimental budget** controller requiring
a hashed profile and a passed clean/B2/C2 capacity-budget receipt. It does not
promote the original occupancy model to validated=true. An explicit experiment
flag, driver/AP/channel scope, no existing qdisc and termination/expiry restore
are required. Existing receiver-assisted implementations and historical logs
are preserved. Formal performance, dynamic competition and generalisation are
separate work.
