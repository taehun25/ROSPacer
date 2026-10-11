"""Read-only 12/10 laboratory readiness; no traffic or configuration changes.

Only JSON report files are written, under the user's approved artifact root.
The collector is streamed over SSH and does not require a fresh deployment.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

DEVICES = {"12": "wlo1", "10": "wlp2s0"}
ARTIFACT_ROOT = Path("ros2_ws/src/large_data_1009/ROSPacer")


def command(argv):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=8)
        return dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return dict(exit_code=None, stdout="", stderr=str(exc))


def collect(dev, stamp):
    tools = {name: shutil.which(name) for name in
             ("iw", "tc", "ip", "ss", "nstat", "iperf3", "chronyc", "sudo")}
    report = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  device=dev, tools=tools, changed_configuration=False,
                  started_traffic=False)
    probes = {
        "kernel": ["uname", "-r"],
        "link": ["iw", "dev", dev, "link"],
        "survey": ["iw", "dev", dev, "survey", "dump"],
        "station": ["iw", "dev", dev, "station", "dump"],
        "addresses": ["ip", "-j", "addr", "show", "dev", dev],
        "qdisc": ["tc", "-j", "-s", "qdisc", "show", "dev", dev],
        "packages": ["dpkg-query", "-W", "ros-humble-fastrtps",
                     "ros-humble-rmw-fastrtps-cpp"],
        "sysctl": ["sysctl", "net.core.wmem_max", "net.core.rmem_max"],
        "clock": ["chronyc", "tracking"],
        "processes": ["pgrep", "-af",
                      r"[t]raffic\.py|[r]emote_smoke\.py|[r]ospacer govern|[i]perf3"],
        "sudo": ["sudo", "-n", "true"],
    }
    for name, argv in probes.items():
        report[name] = command(argv)
    if report["sudo"]["exit_code"] == 0:
        report["survey_root"] = command(["sudo", "-n", "iw", "dev", dev, "survey", "dump"])
    report["overlay_present"] = (Path.home()/"ros2_ws/install/setup.bash").exists()
    report["cyclone_runtime_version_verified"] = False
    # Source overlay presence alone cannot establish which library a node loads.
    folder = Path.home()/ARTIFACT_ROOT/"runs"/stamp
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/"preflight.json"
    report["artifact_path"] = str(path)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return report


def assess(reports):
    findings = []
    for host in DEVICES:
        report = reports.get(host, {})
        if "connection_error" in report or not report:
            findings.append(dict(host=host, gate="remote_access", status="blocked",
                                 reason=report.get("connection_error", "no report")))
            continue
        survey = report.get("survey_root", report.get("survey", {}))
        raw = survey.get("stdout", "")
        # Counters must occur in the associated channel's record.
        import re
        blocks = re.split(r"(?=Survey data from)", raw)
        active = next((b for b in blocks if "[in use]" in b), "")
        missing = [name for name in ("channel active time", "channel busy time",
                                    "channel transmit time") if name+":" not in active]
        findings.append(dict(host=host, gate="airtime_fields",
                             status="blocked" if missing else "needs_validation",
                             missing=missing,
                             reason="Presence still requires advancing counters and calibration"))
        findings.append(dict(host=host, gate="noninteractive_sudo",
                             status="available" if report.get("sudo", {}).get("exit_code") == 0
                             else "blocked"))
        if report.get("processes", {}).get("exit_code") == 0:
            findings.append(dict(host=host, gate="experiment_idle", status="blocked",
                                 reason="Existing matching process; inspect before starting traffic"))
        try:
            roots = json.loads(report["qdisc"]["stdout"])
            custom = [q for q in roots if q.get("root") and q.get("kind") != "noqueue"]
            findings.append(dict(host=host, gate="qdisc", status="blocked" if custom else "available",
                                 reason="Existing root must be preserved" if custom else "No custom root seen"))
        except (KeyError, TypeError, ValueError):
            findings.append(dict(host=host, gate="qdisc", status="unknown"))
    package_reports = [reports.get(h, {}).get("packages", {}) for h in DEVICES]
    if all(p.get("exit_code") == 0 for p in package_reports):
        same = package_reports[0]["stdout"] == package_reports[1]["stdout"]
        findings.append(dict(host="12/10", gate="fastdds_versions",
                             status="available" if same else "blocked",
                             reason="Match versions before formal paired comparison"))
    findings.append(dict(host="12/10", gate="formal_experiment", status="needs_validation",
                         reason="C0/RTT, loaded libraries, applied QoS/buffers, clock error and classifier still require verification"))
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", metavar="DEVICE")
    parser.add_argument("--stamp")
    args = parser.parse_args()
    stamp = args.stamp or datetime.now(timezone.utc).strftime("preflight_%Y%m%d_%H%M%S")
    if not stamp.startswith("preflight_") or not all(c.isalnum() or c == "_" for c in stamp):
        parser.error("invalid report directory name")
    if args.collect:
        if args.collect not in DEVICES.values():
            parser.error("unknown laboratory device")
        print(json.dumps(collect(args.collect, stamp), ensure_ascii=False))
        return
    from deploy import ROOT, ssh
    source = Path(__file__).read_bytes()
    reports = {}
    for host, dev in DEVICES.items():
        try:
            p = ssh(host, f"python3 - --collect {dev} --stamp {stamp}", source)
            if p.returncode:
                raise RuntimeError(p.stderr.decode(errors="replace").strip())
            reports[host] = json.loads(p.stdout)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            reports[host] = dict(connection_error=str(exc))
    result = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  hosts=reports, findings=assess(reports), changed_configuration=False)
    folder = ROOT/"runs"/stamp
    folder.mkdir(parents=True, exist_ok=True)
    (folder/"report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(dict(report=str(folder/"report.json"), findings=result["findings"]),
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
