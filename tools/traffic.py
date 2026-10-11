"""Small ROS 2 smoke source/sink; not a replacement for a research benchmark.

Sequence IDs check delivery. Unsynchronised clocks never produce E2E latency.
"""
import argparse
from array import array
import json
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
    a = p.parse_args()
    if a.bytes < 16 or a.hz <= 0 or a.count < 1 or a.seconds <= 0 or a.min_readers < 1:
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
    endpoint = None
    try:
        if a.role == "pub":
            endpoint = node.create_publisher(UInt8MultiArray, a.topic, qos)
            while endpoint.get_subscription_count() < a.min_readers and time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=.1)
            if endpoint.get_subscription_count() < a.min_readers:
                raise RuntimeError("insufficient matched subscribers before deadline")
            msg = UInt8MultiArray()
            msg.data = array('B', bytes(a.bytes))
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
                    raise
                after = time.monotonic_ns()
                record(dict(seq=seq, publish_start_ns=before, publish_succeeded=True,
                                 publish_duration_ms=(after-before)/1e6))
                due += 1/a.hz
                rclpy.spin_once(node, timeout_sec=0)
                time.sleep(max(0, min(due-time.monotonic(), end-time.monotonic())))
            # Keep reliable writer alive to allow outstanding acknowledgements.
            drain = min(end, time.monotonic()+3)
            while time.monotonic() < drain:
                rclpy.spin_once(node, timeout_sec=.05)
        else:
            def receive(msg):
                nonlocal duplicates
                now = time.monotonic_ns()
                if len(msg.data) != a.bytes:
                    record(dict(error="unexpected payload size", bytes=len(msg.data)))
                    return
                seq, publisher_wall = struct.unpack("!QQ", bytes(msg.data[:16]))
                duplicates += int(seq in ids)
                ids.add(seq)
                record(dict(seq=seq, arrival_monotonic_ns=now, publisher_wall_ns=publisher_wall))
            endpoint = node.create_subscription(UInt8MultiArray, a.topic, receive, qos)
            while len(ids) < a.count and time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=.1)
        completed = len(rows) >= a.count if a.role == "pub" else len(ids) >= a.count
        exit_reason = "completed" if completed else "deadline"
    except Exception as exc:
        error, exit_reason = f"{type(exc).__name__}: {exc}", "error"
    except KeyboardInterrupt:
        error, exit_reason = "interrupted", "interrupted"
    finally:
        events.close()
        Path(a.out).write_text(json.dumps(dict(role=a.role, requested=a.count,
            payload_bytes=a.bytes, requested_hz=a.hz, intent=a.intent, topic=a.topic,
            started_monotonic_ns=started, ended_monotonic_ns=time.monotonic_ns(),
            attempted=sum("publish_succeeded" in row for row in rows),
            succeeded=sum(row.get("publish_succeeded", False) for row in rows),
            error=error, exit_reason=exit_reason,
            records=rows, unique_received=len(ids), duplicates=duplicates,
            missing=sorted(set(range(a.count))-ids) if a.role == "sub" else None,
            note="No end-to-end latency: host clocks not synchronised. Includes 16-byte sequence header."),
            indent=2), encoding="utf-8")
        node.destroy_node()
        rclpy.shutdown()
    if error is not None:
        raise RuntimeError(error)


if __name__ == "__main__":
    main()
