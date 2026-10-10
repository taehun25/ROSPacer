"""Linux observations and owned, reversible HTB/fq lifecycle."""
import csv
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

from .model import adaptive_rate


def run(argv, check=False):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=5)
    if check and p.returncode:
        raise RuntimeError(f'{" ".join(argv)}: {p.stderr.strip()}')
    return p


def observe(dev):
    survey = run(["iw", "dev", dev, "survey", "dump"])
    station = run(["iw", "dev", dev, "station", "dump"])
    result = {"monotonic_s": time.monotonic(), "survey_raw": survey.stdout,
              "station_raw": station.stdout, "errors": survey.stderr+station.stderr}
    # Only the associated channel; never sum all scanned survey records.
    blocks = re.split(r"(?=Survey data from)", survey.stdout)
    active = next((b for b in blocks if "[in use]" in b), "")
    for label, key in (("channel active time", "active_s"),
                       ("channel busy time", "busy_s"),
                       ("channel transmit time", "tx_s")):
        m = re.search(re.escape(label)+r":\s*(\d+)\s*ms", active)
        if m:
            result[key] = int(m[1])/1000
    for label, key in (("tx bytes", "bytes"), ("tx packets", "packets"),
                       ("tx retries", "retries")):
        m = re.search(re.escape(label)+r":\s*(\d+)", station.stdout)
        if m:
            result[key] = int(m[1])
    for label, key in (("tx bitrate", "tx_Bps"), ("rx bitrate", "rx_Bps")):
        m = re.search(re.escape(label)+r":\s*([0-9.]+) MBit/s", station.stdout)
        if m:
            result[key] = float(m[1])*125000
    result["associated"] = "associated:\tyes" in station.stdout or bool(station.stdout.strip())
    result["adaptive_ready"] = all(k in result for k in
        ("active_s", "busy_s", "tx_s", "bytes", "packets", "retries", "tx_Bps", "rx_Bps"))
    return result


def deltas(old, new):
    if not old["adaptive_ready"] or not new["adaptive_ready"]:
        raise ValueError("required driver counters unavailable")
    d = {"elapsed_s": new["monotonic_s"]-old["monotonic_s"]}
    for key in ("active_s", "busy_s", "tx_s", "bytes", "packets", "retries"):
        d[key] = new[key]-old[key]
        if d[key] < 0:
            raise ValueError("driver counter reset")
    # busy counters run over channel active time, not assumed polling period.
    if d["active_s"] <= 0:
        raise ValueError("stale survey counters")
    d["elapsed_s"] = d["active_s"]
    for key in ("tx_Bps", "rx_Bps"):
        d[key] = new[key]
    return d


def doctor(dev):
    def read(path):
        try:
            return Path(path).read_text().strip()
        except OSError:
            return None
    report = {"device": dev, "kernel": os.uname().release,
              "os_release": read("/etc/os-release"),
              "product": read("/sys/class/dmi/id/product_name"),
              "driver": str(Path(f"/sys/class/net/{dev}/device/driver").resolve()),
              "mtu": read(f"/sys/class/net/{dev}/mtu"),
              "tools": {t: shutil.which(t) for t in ("iw", "tc", "ip", "iperf3", "ss", "nstat")}}
    commands = {"link": ["iw", "dev", dev, "link"],
                "qdisc": ["tc", "-j", "-s", "qdisc", "show", "dev", dev],
                "addresses": ["ip", "-j", "addr", "show", "dev", dev],
                "packages": ["dpkg-query", "-W", "ros-humble-fastrtps", "ros-humble-rmw-fastrtps-cpp"],
                "sysctl": ["sysctl", "net.core.wmem_max", "net.core.rmem_max"]}
    for key, argv in commands.items():
        if shutil.which(argv[0]):
            p = run(argv)
            report[key] = {"exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    if report["tools"]["iw"]:
        report["wireless"] = observe(dev)
    report["note"] = "No system settings changed. No survey values are substituted."
    return report


class Shaper:
    HANDLE = "7ac0:"
    CLASS = "7ac0:10"

    def __init__(self, cfg):
        self.cfg, self.dev = cfg, cfg["dev"]
        self.owned = False
        self.lock = None

    def tc(self, *args):
        return run(["tc", *map(str, args)], check=True)

    def install(self):
        if os.geteuid() != 0:
            raise RuntimeError("govern requires root (sudo)")
        import fcntl
        self.lock = open(f'/run/rospacer-{self.dev}.lock', "a+")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        roots = json.loads(self.tc("-j", "qdisc", "show", "dev", self.dev).stdout)
        if any(q.get("root") and q["kind"] != "noqueue" for q in roots):
            raise RuntimeError("existing root qdisc must be preserved; only noqueue is supported")
        mtu = int(Path(f'/sys/class/net/{self.dev}/mtu').read_text())
        if mtu != self.cfg["mtu"]:
            raise RuntimeError("device MTU differs from operating-point MTU")
        self.tc("qdisc", "add", "dev", self.dev, "root", "handle", self.HANDLE,
                "htb", "default", "20")
        self.owned = True
        try:
            # A separate bypass class keeps management SSH/TCP unshaped.
            self.tc("class", "add", "dev", self.dev, "parent", self.HANDLE,
                    "classid", "7ac0:20", "htb", "rate", "10gbit", "ceil", "10gbit")
            self.change(self.cfg["cap_packet_Bps"], add=True)
            self.tc("qdisc", "add", "dev", self.dev, "parent", self.CLASS,
                    "handle", "7ac1:", "fq", "limit", self.cfg["fq_limit"],
                    "flow_limit", self.cfg["fq_flow_limit"], "nopacing")
            for i, dst in enumerate([*self.cfg["peers"], "239.255.0.1"]):
                self.tc("filter", "add", "dev", self.dev, "parent", self.HANDLE,
                        "protocol", "ip", "prio", i+1, "u32", "match", "ip", "protocol",
                        "17", "0xff", "match", "ip", "dst", dst+"/32",
                        "flowid", self.CLASS)
        except Exception:
            self.close()
            raise

    def change(self, packet_Bps, add=False):
        rate = max(1000, round(packet_Bps*8))
        self.tc("class", "add" if add else "change", "dev", self.dev,
                "parent", self.HANDLE, "classid", self.CLASS, "htb", "rate",
                f"{rate}bit", "ceil", f"{rate}bit", "burst", self.cfg["burst_bytes"],
                "cburst", self.cfg["burst_bytes"], "quantum", self.cfg["mtu"])

    def stats(self):
        return self.tc("-j", "-s", "qdisc", "show", "dev", self.dev).stdout.strip()

    def close(self):
        if self.owned:
            roots = json.loads(self.tc("-j", "qdisc", "show", "dev", self.dev).stdout)
            if any(q.get("root") and q.get("handle") == self.HANDLE for q in roots):
                self.tc("qdisc", "del", "dev", self.dev, "root", "handle", self.HANDLE)
            self.owned = False
        if self.lock:
            self.lock.close()
            self.lock = None


def govern(cfg, mode, seconds, trace, dry_run=False):
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("finite positive duration required")
    if mode == "adaptive":
        if cfg.get("relay_in_survey") is None or cfg.get("airtime_overhead_s") is None:
            raise ValueError("adaptive requires calibrated O and explicit relay_in_survey")
        initial = observe(cfg["dev"])
        if not initial["adaptive_ready"]:
            raise RuntimeError("adaptive unavailable: driver lacks active/busy/tx survey counters")
    else:
        initial = None
    if dry_run:
        return {"mode": mode, "config": cfg, "changed_system": False}
    shaper = Shaper(cfg)
    cap = cfg["cap_packet_Bps"]
    deadline = time.monotonic()+seconds
    previous_term = signal.getsignal(signal.SIGTERM)
    def stop(signum, frame):
        raise KeyboardInterrupt("termination requested")
    signal.signal(signal.SIGTERM, stop)
    try:
        shaper.install()
        with open(trace, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["monotonic_s", "mode", "status", "cap_packet_Bps",
                                    "beta", "theta", "relay_s", "qdisc_json", "error"])
            writer.writeheader()
            old = initial
            while time.monotonic() < deadline:
                tick = time.monotonic()
                row = dict(monotonic_s=tick, mode=mode, status="fixed", cap_packet_Bps=cap, error="")
                if mode == "adaptive":
                    new = observe(cfg["dev"])
                    try:
                        estimate = adaptive_rate(cfg, deltas(old, new), cfg["relay_in_survey"])
                        # Smooth noise; use measured counter interval above.
                        cap = max(1000, .7*cap+.3*estimate["cap_packet_Bps"])
                        shaper.change(cap)
                        row.update(status="updated", cap_packet_Bps=cap, beta=estimate["beta"],
                                   theta=estimate["theta"], relay_s=estimate["relay_s"])
                    except ValueError as exc:
                        row.update(status="hold", error=str(exc))
                    old = new
                row["qdisc_json"] = shaper.stats()
                writer.writerow(row)
                f.flush()
                time.sleep(max(0, min(.2-(time.monotonic()-tick), deadline-time.monotonic())))
    finally:
        try:
            shaper.close()
        finally:
            signal.signal(signal.SIGTERM, previous_term)
    return {"trace": str(trace), "restored": True, "mode": mode}


def restore(dev):
    """Recover our qdisc after kill -9; never remove another owner's root."""
    import fcntl
    if os.geteuid() != 0:
        raise RuntimeError("restore requires sudo")
    with open(f'/run/rospacer-{dev}.lock', "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        roots = json.loads(run(["tc", "-j", "qdisc", "show", "dev", dev], check=True).stdout)
        if not any(q.get("root") and q.get("handle") == Shaper.HANDLE for q in roots):
            return {"removed": False, "reason": "ROSPacer root not present"}
        run(["tc", "qdisc", "del", "dev", dev, "root", "handle", Shaper.HANDLE], check=True)
    return {"removed": True}
