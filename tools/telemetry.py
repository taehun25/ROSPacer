"""Bounded read-only queue/socket/driver sampler for W1; JSONL in caller's run dir."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rospacer.linux import run, observe


def udp_counters():
    lines = Path("/proc/net/snmp").read_text().splitlines()
    for header, values in zip(lines, lines[1:]):
        if header.startswith("Udp:") and values.startswith("Udp:"):
            return dict(zip(header.split()[1:], map(int, values.split()[1:])))
    return {}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dev", required=True)
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--interval", type=float, default=.5)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    if not all(math.isfinite(v) and v > 0 for v in (a.seconds, a.interval)):
        p.error("finite positive sampling times required")
    end = time.monotonic()+a.seconds
    with open(a.out, "w", encoding="utf-8") as f:
        while time.monotonic() < end:
            tick = time.monotonic()
            row = dict(monotonic_s=tick, wall_ns=time.time_ns(), udp_global=udp_counters())
            for label, argv in (
                ("qdisc", ["tc", "-j", "-s", "qdisc", "show", "dev", a.dev]),
                ("classes", ["tc", "-j", "-s", "class", "show", "dev", a.dev]),
                ("sockets", ["ss", "-u", "-a", "-m", "-n", "-p"])):
                q = run(argv)
                row[label] = dict(exit_code=q.returncode, stdout=q.stdout, stderr=q.stderr)
            row["wireless"] = observe(a.dev)
            row["collection_duration_s"] = time.monotonic()-tick
            f.write(json.dumps(row)+"\n")
            f.flush()
            time.sleep(max(0,min(a.interval-(time.monotonic()-tick),end-time.monotonic())))


if __name__ == "__main__":
    main()
