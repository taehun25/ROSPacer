"""Pair smoke logs without equating backpressured publication with offered load."""
import math
import statistics


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered)-1)*fraction
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(pos-lo)


def analyze_pair(publisher, subscriber, clock_evidence=None):
    if publisher.get("role") != "pub" or subscriber.get("role") != "sub":
        raise ValueError("publisher and subscriber roles required")
    requested = publisher["requested"]
    if type(requested) is not int or requested <= 0:
        raise ValueError("positive requested count required")
    attempts = [row for row in publisher.get("records", []) if type(row.get("seq")) is int]
    successes = [row for row in attempts if row.get("publish_succeeded", True)]
    attempted_ids = {row["seq"] for row in attempts}
    success_ids = {row["seq"] for row in successes}
    arrivals = [row for row in subscriber.get("records", [])
                if type(row.get("seq")) is int and "arrival_monotonic_ns" in row]
    received_ids = {row["seq"] for row in arrivals}
    valid_ids = received_ids & set(range(requested))
    durations = [row["publish_duration_ms"] for row in attempts
                 if "publish_duration_ms" in row]
    first_arrivals = {}
    for row in arrivals:
        first_arrivals.setdefault(row["seq"], row["arrival_monotonic_ns"])
    times = sorted(t for seq, t in first_arrivals.items() if 0 <= seq < requested)
    intervals = [(b-a)/1e6 for a, b in zip(times, times[1:])]
    payload = publisher.get("payload_bytes")
    goodput = None
    if payload is not None and len(times) > 1 and times[-1] > times[0]:
        goodput = (len(times)-1)*payload*1e9/(times[-1]-times[0])
    starts = sorted(row["publish_start_ns"] for row in successes if "publish_start_ns" in row)
    actual_hz = None
    if len(starts) > 1 and starts[-1] > starts[0]:
        actual_hz = (len(starts)-1)*1e9/(starts[-1]-starts[0])
    latency=None
    clock_validated=False
    if clock_evidence and clock_evidence.get('validated') is True:
        bound=clock_evidence.get('relative_error_bound_ms')
        if not isinstance(bound,(int,float)) or not math.isfinite(bound) or not 0<=bound<=1:
            raise ValueError('qualified relative clock bound required')
        stamped={}
        for row in arrivals:
            if 0<=row['seq']<requested and 'arrival_wall_ns' in row and 'publisher_wall_ns' in row:
                stamped.setdefault(row['seq'],(row['arrival_wall_ns']-row['publisher_wall_ns'])/1e6)
        values=list(stamped.values())
        if len(stamped)==len(valid_ids) and values and min(values)>=-bound:
            latency=dict(p50=percentile(values,.5),p95=percentile(values,.95),p99=percentile(values,.99),
                         minimum=min(values),maximum=max(values),samples=len(values),clock_error_bound_ms=bound,
                         definition='payload timestamp before publish to receiver callback; includes serialization/queueing')
            clock_validated=True
    return dict(requested=requested, attempted=len(attempts), publish_succeeded=len(successes),
        publish_failed=len(attempts)-len(successes), unique_received=len(valid_ids),
        delivery_requested=len(valid_ids)/requested,
        delivery_successful_publish=len(valid_ids & success_ids)/len(success_ids) if success_ids else None,
        received_without_success=sorted(valid_ids-success_ids),
        received_without_attempt=sorted(valid_ids-attempted_ids),
        received_out_of_range=sorted(received_ids-valid_ids),
        duplicate_arrivals=len(arrivals)-len(received_ids), missing_requested=sorted(set(range(requested))-valid_ids),
        requested_hz=publisher.get("requested_hz"), actual_publish_hz=actual_hz,
        publish_duration_ms=dict(mean=statistics.mean(durations) if durations else None,
                                 p50=percentile(durations,.5),
                                 p95=percentile(durations,.95), p99=percentile(durations,.99),
                                 maximum=max(durations) if durations else None),
        arrival_interval_ms=dict(mean=statistics.mean(intervals) if intervals else None,
                                  stdev=statistics.pstdev(intervals) if intervals else None,
                                  p95=percentile(intervals,.95), p99=percentile(intervals,.99)),
        arrival_interval_goodput_Bps=goodput, end_to_end_latency_ms=latency,
        successful_publish_per_target_second=len(successes)/publisher['measurement_target_s'] if publisher.get('measurement_target_s') else None,
        clock_validated=clock_validated,
        publisher_exit_reason=publisher.get("exit_reason", "legacy_log_unspecified"),
        subscriber_exit_reason=subscriber.get("exit_reason", "legacy_log_unspecified"),
        notes=["Successful-publish delivery alone can hide offered-load reduction.",
               "Arrival goodput uses (unique arrivals-1)*payload / first-to-last arrival span.",
               "Interval variability includes loss/backpressure; it is not isolated network jitter.",
               "No E2E latency is computed without verified clock synchronisation.",
               "Payload includes the 16-byte sequence header; CDR/RTPS/IP overhead excluded."])
