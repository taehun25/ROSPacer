"""Bounded 12 -> 10 validation on SR2; all remote artifacts in user path.

Receiver transport remains default unless --paired-static is requested.
--receiver-buffer raises only the receiver kernel cap for a bounded diagnostic.
Neither short mode establishes comparative performance or an optimum.
"""
import json
import argparse
import csv
import io
import math
from pathlib import Path
import shlex
import sys
import time

from deploy import ssh, ROOT, REMOTE
from link_probe import check_idle
sys.path.insert(0, str(ROOT))
from rospacer.model import quantity
from rospacer.metrics import analyze_pair
from rospacer.linux import parse_class_stats


def command(host, script):
    p = ssh(host, "bash -lc "+shlex.quote(script))
    if p.returncode:
        raise RuntimeError(f"host{host}: {p.stderr.decode()} {p.stdout.decode()}")
    return p.stdout.decode()


def python(host, script):
    p = ssh(host, "python3 -", script.encode())
    if p.returncode:
        raise RuntimeError(f"host{host}: {p.stderr.decode()} {p.stdout.decode()}")
    return p.stdout.decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--hz", type=float, default=1)
    parser.add_argument("--payload", default="1MiB")
    parser.add_argument("--share", default="20Mbps", help="explicit development cap input; not measured C0")
    parser.add_argument("--middleware", action="append", choices=("fastdds", "cyclonedds"))
    parser.add_argument("--paired-static", action="store_true", help="also apply the generated receiver XML; needs receiver rmem_max")
    parser.add_argument("--receiver-buffer", action="store_true", help="temporarily raise receiver rmem_max to 1 MiB, then restore")
    a = parser.parse_args()
    payload = int(quantity(a.payload, "bytes"))
    capacity = quantity(a.share, "rate")
    if a.count < 1 or not math.isfinite(a.hz) or a.hz <= 0 or payload < 16:
        parser.error("positive count/Hz and payload >=16 required")
    seconds = math.ceil(max(10, a.count/a.hz+5, 2*a.count*payload/(.9*capacity)+5))
    if seconds > 45:
        parser.error("smoke deadline exceeds 45s; use fewer samples or a separate long-run runner")
    govern_seconds = seconds+3
    sub_seconds = govern_seconds+5
    check_idle()
    stamp = time.strftime("smoke_%Y%m%d_%H%M%S")
    local = ROOT/"runs"/stamp
    local.mkdir(parents=True, exist_ok=True)
    report = {"run": stamp, "receiver_default_transport": True,
              "capacity_is_development_input": True, "e2e_latency_measured": False,
              "count": a.count, "hz": a.hz, "payload_bytes": payload,
              "share_input": a.share, "pub_deadline_s": seconds,
              "classifier": "rtps_ipv4_no_options"}
    report["receiver_default_transport"] = not a.paired_static
    selected = a.middleware or ["fastdds", "cyclonedds"]
    for host in ("12", "10"):
        command(host, f'cd ~/{REMOTE} && mkdir -p runs/{stamp}')
    old_rx = command("12", "cat /proc/sys/net/core/rmem_max").strip()
    report["old_rmem_max12"] = int(old_rx)
    manage_receiver = a.receiver_buffer or a.paired_static
    old_rx10 = int(command("10", "cat /proc/sys/net/core/rmem_max"))
    report["old_rmem_max10"] = old_rx10
    report["receiver_kernel_cap_managed"] = manage_receiver
    # The receiver's limited sudo policy permits these two exact values.
    # Refuse any other original value rather than losing the ability to restore it.
    if manage_receiver and old_rx10 not in (212992, 1048576):
        raise RuntimeError("receiver rmem_max is outside the installed restore policy")
    receiver_changed = False
    try:
        command("12", "sudo -n sysctl -w net.core.rmem_max=1048576")
        if manage_receiver:
            command("10", "sudo -n /usr/sbin/sysctl -w net.core.rmem_max=1048576")
            receiver_changed = True
        for middleware, rmw in (("fastdds", "rmw_fastrtps_cpp"), ("cyclonedds", "rmw_cyclonedds_cpp")):
            if middleware not in selected:
                continue
            base = f'runs/{stamp}/{middleware}'
            command("12", f'cd ~/{REMOTE} && python3 -m rospacer plan --rmw {middleware} '
                    f'--share {capacity} --rate {a.hz} --payload {payload} --dev wlo1 --address 192.168.0.3 --peer 192.168.0.4 '
                    f'--out {base}_profile > {base}_plan.json')
            if a.paired_static:
                receiver_limit = int(command("10", "cat /proc/sys/net/core/rmem_max"))
                plan = json.loads(command("12", f'cat ~/{REMOTE}/{base}_profile/governor.json'))
                if receiver_limit < plan["socket_rx_bytes"]:
                    raise RuntimeError("receiver rmem_max insufficient for paired static; no receiver launched")
                command("10", f'cd ~/{REMOTE} && python3 -m rospacer plan --rmw {middleware} '
                        f'--share {capacity} --rate {a.hz} --payload {payload} --dev wlp2s0 --address 192.168.0.4 --peer 192.168.0.3 '
                        f'--out {base}_profile > {base}_plan.json')
            receiver_setup = f'source {base}_profile/env.bash;' if a.paired_static else 'unset CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML;'
            launch_sub = f'''import subprocess,pathlib,json
p=pathlib.Path.home()/'{REMOTE}'
log=open(p/'{base}_sub.log','w')
shell='source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; export ROS_DOMAIN_ID=71 RMW_IMPLEMENTATION={rmw}; cd '+str(p)+'; {receiver_setup} exec timeout -k 3 {sub_seconds+4} python3 tools/traffic.py sub --count {a.count} --bytes {payload} --hz {a.hz} --seconds {sub_seconds} --out {base}_sub.json'
proc=subprocess.Popen(['bash','-c',shell],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({{'pid':proc.pid}}))
'''
            subpid = json.loads(python("10", launch_sub))["pid"]
            launch_govern = f'''import subprocess,pathlib,json
p=pathlib.Path.home()/'{REMOTE}'
log=open(p/'{base}_govern.log','w')
proc=subprocess.Popen(['sudo','-n','timeout','-k','3','{govern_seconds+4}','python3','-m','rospacer','govern','--config','{base}_profile/governor.json','--mode','fixed','--seconds','{govern_seconds}','--trace','{base}_govern.csv'],cwd=p,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({{'pid':proc.pid}}))
'''
            govpid = json.loads(python("12", launch_govern))["pid"]
            for host, dev in (("12", "wlo1"), ("10", "wlp2s0")):
                launch_sample = f'''import subprocess,pathlib,json
p=pathlib.Path.home()/'{REMOTE}'
log=open(p/'{base}_telemetry.log','w')
cmd=['timeout','-k','3','{govern_seconds+4}','python3','tools/telemetry.py','--dev','{dev}','--seconds','{govern_seconds}','--out','{base}_telemetry.jsonl']
if '{host}'=='12': cmd=['sudo','-n']+cmd
proc=subprocess.Popen(cmd,cwd=p,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(pid=proc.pid)))
'''
                python(host, launch_sample)
            time.sleep(1)
            start = time.monotonic()
            script = (f'source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; '
                      f'cd ~/{REMOTE}; source {base}_profile/env.bash; export ROS_DOMAIN_ID=71; '
                      f'timeout -k 3 {seconds+4} python3 tools/traffic.py pub --count {a.count} --bytes {payload} --hz {a.hz} --seconds {seconds} '
                      f'--out {base}_pub.json > {base}_pub.log 2>&1')
            p = ssh("12", "bash -lc "+shlex.quote(script))
            report[middleware] = {"publisher_exit": p.returncode, "subscriber_pid": subpid,
                                  "governor_pid": govpid}
            # Bounded waits; remote timeout also bounds cleanup on disconnect.
            time.sleep(max(0, govern_seconds+1-(time.monotonic()-start)))
            for host, suffix in (("12", "pub"), ("10", "sub")):
                raw = command(host, f'cat ~/{REMOTE}/{base}_{suffix}.json')
                (local/f'{middleware}_{suffix}.json').write_text(raw, encoding="utf-8")
                report[middleware][suffix] = json.loads(raw)
            report[middleware]["metrics"] = analyze_pair(report[middleware]["pub"],report[middleware]["sub"])
            raw = command("12", f'cat ~/{REMOTE}/{base}_govern.csv')
            (local/f'{middleware}_govern.csv').write_text(raw,encoding="utf-8")
            trace = list(csv.DictReader(io.StringIO(raw)))
            report[middleware]["max_class_bytes"] = {}
            for row in trace:
                for item in parse_class_stats(row["class_json"]):
                    key = item.get("handle", item.get("classid", "unknown"))
                    before = report[middleware]["max_class_bytes"].get(key,0)
                    report[middleware]["max_class_bytes"][key] = max(before,item.get("bytes",0))
            for host in ("12", "10"):
                raw = command(host, f'cat ~/{REMOTE}/{base}_telemetry.jsonl')
                (local/f'{middleware}_telemetry{host}.jsonl').write_text(raw,encoding="utf-8")
            for host, suffix in (("12", "pub"), ("10", "sub"), ("12", "govern")):
                raw = command(host, f'cat ~/{REMOTE}/{base}_{suffix}.log')
                (local/f'{middleware}_{suffix}.log').write_text(raw, encoding="utf-8")
                report[middleware][suffix+"_log"] = raw
            qdisc = command("12", "tc -j qdisc show dev wlo1")
            report[middleware]["qdisc_after"] = json.loads(qdisc)
    finally:
        # Both hosts must be restored even when one SSH restoration fails.
        restoration_errors = []
        for host, original in (("12", int(old_rx)), ("10", old_rx10)):
            if host == "10" and not receiver_changed:
                continue
            try:
                command(host, f'sudo -n /usr/sbin/sysctl -w net.core.rmem_max={original}')
            except Exception as error:
                restoration_errors.append(f"host{host}: {error}")
        report["rmem_restored12"] = int(command("12", "cat /proc/sys/net/core/rmem_max")) == int(old_rx)
        report["rmem_restored10"] = int(command("10", "cat /proc/sys/net/core/rmem_max")) == old_rx10
        report["restoration_errors"] = restoration_errors
        text = json.dumps(report, indent=2)
        (local/"summary.json").write_text(text, encoding="utf-8")
        for host in ("12", "10"):
            python(host, f"from pathlib import Path; Path.home().joinpath('{REMOTE}/runs/{stamp}/summary.json').write_text("+repr(text)+")")
        if restoration_errors:
            raise RuntimeError("; ".join(restoration_errors))
    print(json.dumps({"run": stamp, "rmem_restored12": report["rmem_restored12"],
        "rmem_restored10": report["rmem_restored10"],
        "vendors": {m: {"publisher_exit": report[m]["publisher_exit"],
        "received": report[m].get("sub", {}).get("unique_received"),
        "pub_log": report[m].get("pub_log"), "govern_log": report[m].get("govern_log"),
        "qdisc_after": report[m].get("qdisc_after")} for m in ("fastdds", "cyclonedds") if m in report}}, indent=2))


if __name__ == "__main__":
    main()
