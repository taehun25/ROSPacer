"""Finite B2 source: saturated UDP for two seconds, then two seconds off.

Runs on the additional AP's source laptop. No kernel/network settings change.
The SSH controller may leave this AP; all children have independent time bounds.
"""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import subprocess
import time


def command(argv, timeout=5):
    q = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return {"rc": q.returncode, "stdout": q.stdout, "stderr": q.stderr}


def link(dev):
    return command(["iw", "dev", dev, "link"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--peer", required=True)
    p.add_argument("--bind", required=True)
    p.add_argument("--dev", default="wlp2s0")
    p.add_argument("--port", type=int, default=55449)
    p.add_argument("--seconds", type=float, default=240)
    p.add_argument("--delay", type=float, default=10)
    p.add_argument("--out", required=True)
    p.add_argument("--source-commit", required=True)
    a = p.parse_args()
    for value in [a.peer, a.bind]:
        if ipaddress.ip_address(value).version != 4:
            p.error("IPv4 required")
    if not 4 <= a.seconds <= 300 or not 0 <= a.delay <= 30:
        p.error("finite duration 4..300 seconds and delay 0..30 required")
    folder = Path(a.out)
    folder.mkdir(parents=True, exist_ok=True)
    initial = link(a.dev)
    if "SSID: iptime5GAX1500\n" not in initial["stdout"] or "freq: 5745" not in initial["stdout"]:
        raise RuntimeError("B2 source must be on AX1500 at channel149")
    metadata = {"args": vars(a), "initial_link": initial,
                "info": command(["iw", "dev", a.dev, "info"]),
                "power": command(["iw", "dev", a.dev, "get", "power_save"]),
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "wall_ns": time.time_ns(), "monotonic_s": time.monotonic()}
    (folder/"metadata.json").write_text(json.dumps(metadata, indent=2))
    time.sleep(a.delay)
    start = time.monotonic()
    deadline = start + a.seconds
    results = []
    with (folder/"events.jsonl").open("w") as events:
        while time.monotonic() + 2 < deadline and not (folder/"stop").exists():
            state = link(a.dev)
            if "SSID: iptime5GAX1500\n" not in state["stdout"]:
                raise RuntimeError("source AP changed during B2")
            tick = time.monotonic()
            row = {"burst": len(results), "start_monotonic_s": tick,
                   "start_wall_ns": time.time_ns(), "link": state}
            argv = ["iperf3", "-c", a.peer, "-B", a.bind, "-p", str(a.port),
                    "-u", "-b", "0", "-l", "1400", "-t", "2", "-i", ".2",
                    "-J", "--get-server-output"]
            try:
                result = command(argv, timeout=min(7, deadline-time.monotonic()))
                (folder/f"burst_{len(results):03d}.json").write_text(json.dumps(result, indent=2))
                data = json.loads(result["stdout"]) if result["stdout"] else {}
                row.update(rc=result["rc"], error=data.get("error"), client_end=data.get("end"))
            except (subprocess.TimeoutExpired, ValueError) as e:
                row.update(rc=None, error=str(e))
            row.update(end_monotonic_s=time.monotonic(), end_wall_ns=time.time_ns())
            row["elapsed_s"] = row["end_monotonic_s"] - tick
            row["period_overrun_s"] = max(0, time.monotonic()-(tick+4))
            results.append(row)
            events.write(json.dumps(row)+"\n")
            events.flush()
            # Keep successive starts four seconds apart. Sleeping two seconds
            # after process exit also counted the handshake as extra off time.
            # Actual payload on/off still requires the receiver interval logs.
            time.sleep(max(0, min(tick+4-time.monotonic(), deadline-time.monotonic())))
    summary = {"start_monotonic_s": start, "end_monotonic_s": time.monotonic(),
               "bursts": results, "final_link": link(a.dev),
               "scope": "iperf requested2s payload at4second start periods; inspect intervals/overruns for actual duty cycle; no valid airtime estimate"}
    (folder/"summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"bursts": len(results), "successful_bursts": sum(r.get("rc") == 0 and not r.get("error") for r in results)}), flush=True)


if __name__ == "__main__":
    main()
