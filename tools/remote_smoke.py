"""Bounded 12 -> 10 validation on SR2; all remote artifacts in user path.

Receiver uses its default transport because sudo/sysctl is unavailable there.
This is a sender profile/pacing smoke test, not paired Static evaluation.
"""
import json
from pathlib import Path
import shlex
import sys
import time

from deploy import ssh, ROOT, REMOTE


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
    stamp = time.strftime("smoke_%Y%m%d_%H%M%S")
    local = ROOT/"runs"/stamp
    local.mkdir(parents=True, exist_ok=True)
    report = {"run": stamp, "receiver_default_transport": True,
              "capacity_is_development_input": True, "e2e_latency_measured": False}
    for host in ("12", "10"):
        command(host, f'cd ~/{REMOTE} && mkdir -p runs/{stamp}')
    old_rx = command("12", "cat /proc/sys/net/core/rmem_max").strip()
    report["old_rmem_max12"] = int(old_rx)
    try:
        command("12", "sudo -n sysctl -w net.core.rmem_max=1048576")
        for middleware, rmw in (("fastdds", "rmw_fastrtps_cpp"), ("cyclonedds", "rmw_cyclonedds_cpp")):
            base = f'runs/{stamp}/{middleware}'
            command("12", f'cd ~/{REMOTE} && python3 -m rospacer plan --rmw {middleware} '
                    f'--share 20Mbps --rate 1 --dev wlo1 --address 192.168.0.3 --peer 192.168.0.4 '
                    f'--out {base}_profile > {base}_plan.json')
            launch_sub = f'''import subprocess,pathlib,json
p=pathlib.Path.home()/'{REMOTE}'
log=open(p/'{base}_sub.log','w')
shell='source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; export ROS_DOMAIN_ID=71 RMW_IMPLEMENTATION={rmw}; unset CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML; cd '+str(p)+'; exec timeout 18 python3 tools/traffic.py sub --count 3 --hz 1 --seconds 15 --out {base}_sub.json'
proc=subprocess.Popen(['bash','-c',shell],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({{'pid':proc.pid}}))
'''
            subpid = json.loads(python("10", launch_sub))["pid"]
            launch_govern = f'''import subprocess,pathlib,json
p=pathlib.Path.home()/'{REMOTE}'
log=open(p/'{base}_govern.log','w')
proc=subprocess.Popen(['sudo','-n','timeout','14','python3','-m','rospacer','govern','--config','{base}_profile/governor.json','--mode','fixed','--seconds','10','--trace','{base}_govern.csv'],cwd=p,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({{'pid':proc.pid}}))
'''
            govpid = json.loads(python("12", launch_govern))["pid"]
            time.sleep(1)
            start = time.monotonic()
            script = (f'source /opt/ros/humble/setup.bash; source ~/ros2_ws/install/setup.bash; '
                      f'cd ~/{REMOTE}; source {base}_profile/env.bash; export ROS_DOMAIN_ID=71; '
                      f'timeout 12 python3 tools/traffic.py pub --count 3 --hz 1 --seconds 9 '
                      f'--out {base}_pub.json > {base}_pub.log 2>&1')
            p = ssh("12", "bash -lc "+shlex.quote(script))
            report[middleware] = {"publisher_exit": p.returncode, "subscriber_pid": subpid,
                                  "governor_pid": govpid}
            # Bounded waits; remote timeout also bounds cleanup on disconnect.
            time.sleep(max(0, 11-(time.monotonic()-start)))
            for host, suffix in (("12", "pub"), ("10", "sub")):
                raw = command(host, f'cat ~/{REMOTE}/{base}_{suffix}.json')
                (local/f'{middleware}_{suffix}.json').write_text(raw, encoding="utf-8")
                report[middleware][suffix] = json.loads(raw)
            for host, suffix in (("12", "pub"), ("10", "sub"), ("12", "govern")):
                raw = command(host, f'cat ~/{REMOTE}/{base}_{suffix}.log')
                (local/f'{middleware}_{suffix}.log').write_text(raw, encoding="utf-8")
                report[middleware][suffix+"_log"] = raw
            qdisc = command("12", "tc -j qdisc show dev wlo1")
            report[middleware]["qdisc_after"] = json.loads(qdisc)
    finally:
        command("12", f'sudo -n sysctl -w net.core.rmem_max={int(old_rx)}')
        report["rmem_restored12"] = int(command("12", "cat /proc/sys/net/core/rmem_max")) == int(old_rx)
        text = json.dumps(report, indent=2)
        (local/"summary.json").write_text(text, encoding="utf-8")
        for host in ("12", "10"):
            python(host, f"from pathlib import Path; Path.home().joinpath('{REMOTE}/runs/{stamp}/summary.json').write_text("+repr(text)+")")
    print(json.dumps({"run": stamp, "rmem_restored12": report["rmem_restored12"],
        "vendors": {m: {"publisher_exit": report[m]["publisher_exit"],
        "received": report[m].get("sub", {}).get("unique_received"),
        "pub_log": report[m].get("pub_log"), "govern_log": report[m].get("govern_log"),
        "qdisc_after": report[m].get("qdisc_after")} for m in ("fastdds", "cyclonedds") if m in report}}, indent=2))


if __name__ == "__main__":
    main()
