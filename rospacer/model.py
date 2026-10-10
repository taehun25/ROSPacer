"""Byte/s throughout; application goodput and qdisc packet rates are distinct."""
import math
import re


def quantity(value, kind):
    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z/]+)?\s*", str(value))
    if not m:
        raise ValueError(f"invalid quantity: {value}")
    units = {"bytes": {None: 1, "B": 1, "KB": 1000, "MB": 1000000,
                       "KiB": 1024, "MiB": 1048576},
             "rate": {None: 1, "B/s": 1, "MB/s": 1000000, "Mbps": 125000,
                      "Mbit/s": 125000, "Kbps": 125},
             "time": {None: 1, "s": 1, "ms": .001, "us": .000001}}
    if m[2] not in units[kind]:
        raise ValueError(f"unsupported {kind} unit: {m[2]}")
    result = float(m[1]) * units[kind][m[2]]
    if not math.isfinite(result) or result <= 0:
        raise ValueError("quantity must be finite and positive")
    return result


def synthesize(payload, hz, readers, capacity, rtt, tau, alpha=.9,
               unit=1472, header=64, intent="complete", mtu=1500):
    if not (payload > 0 and hz > 0 and readers >= 1 and capacity > 0
            and rtt > 0 and tau > 0 and 0 < alpha < 1
            and 0 <= header < unit <= mtu - 28):
        raise ValueError("invalid operating-point inputs or UDP unit exceeds MTU")
    if intent not in ("complete", "latest"):
        raise ValueError("intent must be complete or latest")
    load = payload * hz * readers
    c = alpha * capacity
    feedback = min(.1, max(.005, .5 / hz))
    lower = payload + capacity * (rtt + feedback)
    upper = tau * (c - load)
    # Fast DDS limits samples, so a continuous feasible interval may still be
    # impossible after discretisation. Do not call that bounded recovery.
    minimum_samples = math.ceil(lower / payload)
    maximum_samples = math.floor(upper / payload)
    feasible = c > load and maximum_samples >= minimum_samples
    samples = maximum_samples if feasible and intent == "complete" else 2
    if intent == "latest":
        samples = 1
    qtx = math.ceil(max(65536, 2 * capacity * .002))
    qrx = math.ceil(max(1048576, 2 * (max(capacity, load) * .02 + unit)))
    # Explicit first-order conversion; packet captures must calibrate the
    # effective RTPS overhead for the actual type, vendor and message size.
    factor = (unit + 28) / (unit - header)
    # Qtx/MTU is the proposal's lower bound, not a safe upper limit. On the
    # current UDP stack it did not prevent a full-sample burst from reaching
    # fq. Reserve a sample plus repair margin pending socket-accounting tests.
    flow_limit = max(math.ceil(qtx/mtu), 2*math.ceil(payload*readers/(unit-header)))
    return dict(payload_bytes=int(payload), publish_hz=hz, readers=readers,
                capacity_Bps=capacity, load_Bps=load, rho=load/capacity,
                alpha=alpha, cap_application_Bps=c, packet_factor=factor,
                cap_packet_Bps=c*factor, unit_bytes=unit, header_bytes=header,
                feedback_s=feedback, rtt_s=rtt, recovery_s=tau,
                cache_lower_bytes=lower, cache_upper_bytes=upper,
                feasible_recovery=feasible and intent == "complete",
                cache_samples=samples, cache_bytes=int(samples*payload),
                socket_tx_bytes=qtx, socket_rx_bytes=qrx,
                fq_flow_limit=flow_limit, fq_limit=max(4096, 4*flow_limit),
                burst_bytes=mtu, mtu=mtu, intent=intent,
                qualifications=[
                    "RTPS header is an explicit provisional input; verify by packet capture.",
                    "Cache limits do not prove publish() backpressure or complete delivery.",
                    "Cyclone WHC watermark is a throttling threshold, not a strict byte cap.",
                    "Recovery bound needs measured C, valid pacing and stable offered load."])


def identify_overhead(capacity, tx_rate, rx_rate, retries, unit, header):
    if not (capacity > 0 and tx_rate > 0 and rx_rate > 0 and retries >= 0
            and 0 <= header < unit):
        raise ValueError("invalid calibration")
    o = .5*((unit-header)/(capacity*(1+retries))
             - (unit+28)/tx_rate - (unit+28)/rx_rate)
    if o < 0 or not math.isfinite(o):
        raise ValueError("C0 and PHY rates inconsistent with two-hop model")
    return o


def adaptive_rate(cfg, delta, relay_in_survey):
    elapsed = delta["elapsed_s"]
    busy, own = delta["busy_s"], delta["tx_s"]
    if elapsed <= 0 or not (0 <= own <= busy <= elapsed*1.1):
        raise ValueError("invalid survey counter deltas")
    up, down = delta["tx_Bps"], delta["rx_Bps"]
    if up <= 0 or down <= 0:
        raise ValueError("missing PHY rate")
    retry = delta["retries"] / max(1, delta["packets"])
    relay = 0.0
    if relay_in_survey:
        # Aggregate traffic relay estimate must be validated on this driver/AP.
        relay = (1+retry)*delta["bytes"]/(cfg["unit_bytes"]-cfg["header_bytes"])*(
            cfg["airtime_overhead_s"]+(cfg["unit_bytes"]+28)/down)
    beta = max(0.0, min(1.0, (busy-own-relay)/elapsed))
    theta = (1+retry)/(cfg["unit_bytes"]-cfg["header_bytes"])*(
        2*cfg["airtime_overhead_s"]+(cfg["unit_bytes"]+28)/up+
        (cfg["unit_bytes"]+28)/down)
    cap = cfg["alpha"]*(1-beta)/theta
    return {"beta": beta, "relay_s": relay, "theta": theta,
            "cap_application_Bps": cap, "cap_packet_Bps": cap*cfg["packet_factor"]}
