"""W2 source/sink, derived from the retained W1 source; explicit warmup and raw timing.

Sequence IDs check delivery. Unsynchronised clocks never produce E2E latency.
"""
import argparse
from array import array
import hashlib
import json
import math
import os
import random
from pathlib import Path
import struct
import time

import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from std_msgs.msg import UInt8MultiArray


def main():
    p = argparse.ArgumentParser()
    p.add_argument("role", choices=("pub", "sub"))
    p.add_argument("--bytes", type=int, default=1048576)
    p.add_argument("--hz", type=float, default=10)
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--out", required=True)
    p.add_argument("--intent", choices=("complete", "latest"), default="complete")
    p.add_argument("--topic", default="/rospacer_smoke")
    p.add_argument("--min-readers", type=int, default=1)
    p.add_argument("--discovery-seconds", type=float, default=10)
    p.add_argument("--drain-seconds", type=float, default=3)
    p.add_argument("--continue-on-publish-error", action="store_true")
    p.add_argument("--pattern", choices=("random", "zeros"), default="random")
    p.add_argument("--start-wall",type=float,default=0)
    p.add_argument("--warmup-seconds",type=float,default=0)
    p.add_argument("--ready-path")
    p.add_argument("--start-marker")
    a = p.parse_args()
    if a.bytes < 16 or a.count < 1 or a.min_readers < 1 or not all(math.isfinite(v) and v > 0 for v in (a.hz,a.seconds,a.discovery_seconds)) or not math.isfinite(a.drain_seconds) or a.drain_seconds < 0:
        p.error("invalid traffic parameters")
    rclpy.init()
    try:
        node = rclpy.create_node("rospacer_smoke_"+a.role)
    except Exception as exc:
        Path(a.out).write_text(json.dumps(dict(role=a.role, requested=a.count,
                                             payload_bytes=a.bytes, exit_reason="node_creation_error", error=str(exc),
                                             unique_received=0)), encoding="utf-8")
        rclpy.shutdown()
        raise
    qos = QoSProfile(history=HistoryPolicy.KEEP_ALL if a.intent == "complete" else HistoryPolicy.KEEP_LAST,
                     depth=1, reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.VOLATILE)
    rows, ids, duplicates = [], set(), 0
    started = time.monotonic_ns()
    error, exit_reason = None, "running"
    events = open(Path(a.out).with_suffix(".events.jsonl"), "w", encoding="utf-8")
    def record(row):
        rows.append(row)
        events.write(json.dumps(row)+"\n")
        events.flush()
    end = time.monotonic()+a.seconds
    measurement_started_ns = None
    measurement_ended_ns = None
    publisher_errors = []
    def save_metadata():
        libs = sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines()
            if line.split()[-1].startswith('/') and any(k in line for k in
            ('libfastrtps', 'libfastcdr', 'librmw_fastrtps', 'libddsc', 'librmw_cyclonedds'))})
        metadata = dict(pid=os.getpid(), rmw=os.environ.get('RMW_IMPLEMENTATION'),
            qos=str(endpoint.qos_profile), libraries={lib:hashlib.sha256(Path(lib).read_bytes()).hexdigest() for lib in libs},
            environment={k:os.environ.get(k) for k in ('CYCLONEDDS_URI','FASTRTPS_DEFAULT_PROFILES_FILE','RMW_FASTRTPS_USE_QOS_FROM_XML','ROS_DOMAIN_ID','LD_LIBRARY_PATH')})
        Path(a.out).with_suffix('.metadata.json').write_text(json.dumps(metadata,indent=2))
    endpoint = None
    try:
        if a.role == "pub":
            endpoint = node.create_publisher(UInt8MultiArray, a.topic, qos)
            save_metadata()
            discovery_end = time.monotonic()+a.discovery_seconds
            while endpoint.get_subscription_count() < a.min_readers and time.monotonic() < discovery_end:
                rclpy.spin_once(node, timeout_sec=.1)
            if endpoint.get_subscription_count() < a.min_readers:
                raise RuntimeError("insufficient matched subscribers before deadline")
            msg = UInt8MultiArray()
            msg.data = array('B', random.Random(0).randbytes(a.bytes) if a.pattern == 'random' else bytes(a.bytes))
            if a.start_wall:
                while time.time()<a.start_wall:time.sleep(max(0,min(.1,a.start_wall-time.time())))
            warm_end=time.monotonic()+a.warmup_seconds
            warm_due=time.monotonic();warm_started_wall=time.time();warm_calls=0;warm_max_ms=0
            while time.monotonic()<warm_end:
                msg.data[:16]=array('B',struct.pack("!QQ",2**64-1,time.time_ns()))
                warm_before=time.monotonic()
                try:endpoint.publish(msg)
                except Exception as exc:publisher_errors.append('warmup: '+str(exc))
                warm_calls+=1;warm_max_ms=max(warm_max_ms,(time.monotonic()-warm_before)*1000)
                warm_due+=1/a.hz
                rclpy.spin_once(node,timeout_sec=0)
                time.sleep(max(0,min(warm_due-time.monotonic(),warm_end-time.monotonic())))
            measurement_nominal=a.start_wall+a.warmup_seconds;ready_wall=time.time()
            if a.ready_path:
                ready_file=Path(a.ready_path);pending=ready_file.with_name(ready_file.name+'.pending')
                pending.write_text(json.dumps({'ready':True,'wall_ns':time.time_ns(),'warmup_max_publish_ms':warm_max_ms,'warmup_publish_calls':warm_calls}));pending.replace(ready_file)
            if a.start_marker:
                marker=Path(a.start_marker);deadline=measurement_nominal+45
                while not marker.exists() and time.time()<deadline:rclpy.spin_once(node,timeout_sec=.02)
                if not marker.exists():raise RuntimeError('measurement barrier marker missing')
                measurement_nominal=json.loads(marker.read_text())['start_wall']
                while time.time()<measurement_nominal:rclpy.spin_once(node,timeout_sec=max(0,min(.01,measurement_nominal-time.time())))
            Path(a.out).with_suffix('.start.json').write_text(json.dumps({'wall_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),'nominal_wall':measurement_nominal,'warmup_started_wall':warm_started_wall,'warmup_publish_calls':warm_calls,'warmup_max_publish_ms':warm_max_ms,'barrier_wait_s':time.time()-ready_wall,'barrier_enabled':bool(a.start_marker)}))
            end = time.monotonic()+a.seconds
            measurement_started_ns = time.monotonic_ns()
            due = time.monotonic()
            for seq in range(a.count):
                if time.monotonic() >= end:
                    break
                msg.data[:16] = array('B', struct.pack("!QQ", seq, time.time_ns()))
                before = time.monotonic_ns()
                try:
                    endpoint.publish(msg)
                except Exception as exc:
                    record(dict(seq=seq, publish_start_ns=before, publish_succeeded=False,
                                publish_duration_ms=(time.monotonic_ns()-before)/1e6,
                                error=f"{type(exc).__name__}: {exc}"))
                    publisher_errors.append(f"{type(exc).__name__}: {exc}")
                    if not a.continue_on_publish_error:
                        raise
                else:
                    after = time.monotonic_ns()
                    record(dict(seq=seq, publish_start_ns=before, publish_succeeded=True,
                                     publish_duration_ms=(after-before)/1e6))
                due += 1/a.hz
                rclpy.spin_once(node, timeout_sec=0)
                time.sleep(max(0, min(due-time.monotonic(), end-time.monotonic())))
            # Keep reliable writer alive to allow outstanding acknowledgements.
            measurement_ended_ns = time.monotonic_ns()
            drain = time.monotonic()+a.drain_seconds
            while time.monotonic() < drain:
                rclpy.spin_once(node, timeout_sec=.05)
        else:
            def receive(msg):
                nonlocal duplicates
                now = time.monotonic_ns()
                wall = time.time_ns()
                if len(msg.data) != a.bytes:
                    record(dict(error="unexpected payload size", bytes=len(msg.data)))
                    return
                seq, publisher_wall = struct.unpack("!QQ", bytes(msg.data[:16]))
                if seq>=a.count:return
                duplicates += int(seq in ids)
                ids.add(seq)
                record(dict(seq=seq, arrival_monotonic_ns=now, arrival_wall_ns=wall, publisher_wall_ns=publisher_wall))
            endpoint = node.create_subscription(UInt8MultiArray, a.topic, receive, qos)
            save_metadata()
            if a.start_marker:
                marker=Path(a.start_marker);deadline=a.start_wall+a.warmup_seconds+45
                while not marker.exists() and time.time()<deadline:rclpy.spin_once(node,timeout_sec=.02)
                if not marker.exists():raise RuntimeError('subscriber measurement barrier marker missing')
                go=json.loads(marker.read_text())['start_wall']
                end=time.monotonic()+max(0,go+a.seconds+a.drain_seconds+8-time.time())
            elif a.start_wall:end=time.monotonic()+max(0,a.start_wall+a.warmup_seconds+a.seconds+a.drain_seconds+8-time.time())
            while time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=.1)
        completed = len(rows) >= a.count if a.role == "pub" else len(ids) >= a.count
        exit_reason = "completed_with_publish_errors" if completed and publisher_errors else "completed" if completed else "deadline_with_publish_errors" if publisher_errors else "deadline"
    except Exception as exc:
        error, exit_reason = f"{type(exc).__name__}: {exc}", "error"
    except KeyboardInterrupt:
        error, exit_reason = "interrupted", "interrupted"
    finally:
        events.close()
        Path(a.out).write_text(json.dumps(dict(role=a.role, requested=a.count,
            payload_bytes=a.bytes, requested_hz=a.hz, intent=a.intent, topic=a.topic,
            started_monotonic_ns=started, ended_monotonic_ns=time.monotonic_ns(),
            measurement_started_ns=measurement_started_ns, measurement_ended_ns=measurement_ended_ns,
            measurement_target_s=a.seconds, publisher_errors=publisher_errors, pattern=a.pattern,
            attempted=sum("publish_succeeded" in row for row in rows),
            succeeded=sum(row.get("publish_succeeded", False) for row in rows),
            error=error, exit_reason=exit_reason,
            records=rows, unique_received=len(ids), duplicates=duplicates,
            missing=sorted(set(range(a.count))-ids) if a.role == "sub" else None,
            note="Raw wall timestamps retained; E2E latency requires independent clock qualification. Includes 16-byte sequence header."),
            indent=2), encoding="utf-8")
        node.destroy_node()
        rclpy.shutdown()
    if error is not None:
        raise RuntimeError(error)


if __name__ == "__main__":
    main()
