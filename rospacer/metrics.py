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
    hz=publisher.get('requested_hz')
    deviations=[abs(dt-1000/hz) for dt in intervals] if isinstance(hz,(int,float)) and math.isfinite(hz) and hz>0 else []
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
        arrival_jitter_ms=dict(p50=percentile(deviations,.5),p95=percentile(deviations,.95),p99=percentile(deviations,.99),
                              definition='abs(consecutive unique arrival interval - requested publish period); includes loss/backpressure'),
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


def recovery_metric(subscriber,outage,clock_evidence):
    """Proposal recovery: trailing1s p95 falls below2x pre-outage p95."""
    result={'recovery_s':None,'definition':'first full post-restore1s arrival window with p95 latency <=2x pre-outage p95; minimum3samples',
            'clock_validated':bool(clock_evidence and clock_evidence.get('validated'))}
    if not result['clock_validated']:
        result['reason']='clock evidence not qualified';return result
    start,end=outage['outage_started_monotonic_ns'],outage['outage_ended_monotonic_ns']
    seen=set();rows=[]
    for r in subscriber.get('records',[]):
        if r.get('seq') in seen or not all(k in r for k in ['seq','arrival_monotonic_ns','arrival_wall_ns','publisher_wall_ns']):continue
        seen.add(r['seq']);rows.append((r['arrival_monotonic_ns'],(r['arrival_wall_ns']-r['publisher_wall_ns'])/1e6))
    rows.sort()
    baseline=[d for t,d in rows if start-4e9<=t<start]
    if len(baseline)<3:result['reason']='insufficient pre-outage samples';return result
    result['baseline_p95_ms']=percentile(baseline,.95);result['threshold_ms']=2*result['baseline_p95_ms']
    after=[(t,d) for t,d in rows if t>=end]
    result['first_arrival_after_restore_s']=(after[0][0]-end)/1e9 if after else None
    result['windows']=[]
    for t,d in after:
        if t<end+1e9:continue
        window=[v for u,v in after if t-1e9<=u<=t]
        if len(window)<3:continue
        p95=percentile(window,.95);result['windows'].append({'after_restore_s':(t-end)/1e9,'p95_ms':p95,'samples':len(window)})
        if result['recovery_s'] is None and p95<=result['threshold_ms']:result['recovery_s']=(t-end)/1e9
    if result['recovery_s'] is None:result['reason']='threshold not reached within observed windows (censored)'
    return result
