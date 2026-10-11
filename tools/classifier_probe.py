"""Bounded negative classifier check: non-RTPS UDP to the DDS peer must bypass.

SR2 12/10 helper, not a performance benchmark. Leaves sysctl unchanged.
"""
import csv
import io
import json
import time

from deploy import ROOT, REMOTE
from link_probe import check_idle
from remote_smoke import command, python
from rospacer.linux import parse_class_stats


def main():
    check_idle()
    stamp = time.strftime("classifier_%Y%m%d_%H%M%S")
    local = ROOT / "runs" / stamp
    local.mkdir(parents=True)
    base = f"runs/{stamp}"
    for host in ("12", "10"):
        command(host, f"cd ~/{REMOTE} && mkdir -p {base}")
    command("12", f"cd ~/{REMOTE} && python3 -m rospacer plan --rmw cyclonedds "
            f"--share 4Mbps --rate 1 --payload 128KiB --dev wlo1 "
            f"--address 192.168.0.3 --peer 192.168.0.4 --out {base}/profile "
            f"> {base}/plan.json")
    report = dict(run=stamp, protocol="non-RTPS iperf3 UDP", offered_bps=20000000,
                  duration_s=6, udp_payload_bytes=1472, changed_sysctl=False)
    governor_started = None
    try:
        report["server"] = json.loads(python("10", f"""
import subprocess,pathlib,json
p=pathlib.Path.home()/'{REMOTE}/{base}'
f=open(p/'server.json','w')
q=subprocess.Popen(['timeout','25','iperf3','-s','-1','-B','192.168.0.4','-p','55202','--json'],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(pid=q.pid,deadline_s=25)))
"""))
        report["governor"] = json.loads(python("12", f"""
import subprocess,pathlib,json
p=pathlib.Path.home()/'{REMOTE}'
f=open(p/'{base}/govern.log','w')
q=subprocess.Popen(['sudo','-n','timeout','-k','3','26','python3','-m','rospacer','govern','--config','{base}/profile/governor.json','--mode','fixed','--seconds','22','--trace','{base}/govern.csv'],cwd=p,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(pid=q.pid,deadline_s=26)))
"""))
        governor_started = time.monotonic()
        time.sleep(1)
        roots = json.loads(command("12", "tc -j qdisc show dev wlo1"))
        if not any(q.get("root") and q.get("handle") == "7ac0:" for q in roots):
            raise RuntimeError("governor did not install its root qdisc")
        report["client"] = json.loads(python("12", f"""
import subprocess,pathlib,json
p=pathlib.Path.home()/'{REMOTE}/{base}'
q=subprocess.run(['iperf3','-c','192.168.0.4','-B','192.168.0.3','-p','55202','-u','-b','20M','-l','1472','-t','6','--json'],capture_output=True,text=True,timeout=15)
d=dict(exit_code=q.returncode,stdout=q.stdout,stderr=q.stderr)
(p/'client.json').write_text(json.dumps(d,indent=2))
print(json.dumps(d))
"""))
        if report["client"]["exit_code"]:
            raise RuntimeError("iperf client failed; inspect raw result")
        time.sleep(max(0, 23 - (time.monotonic() - governor_started)))
        for host, filename in (("12", "govern.csv"), ("12", "govern.log"),
                               ("12", "client.json"), ("12", "plan.json"),
                               ("10", "server.json")):
            raw = command(host, f"cat ~/{REMOTE}/{base}/{filename}")
            (local / filename).write_text(raw, encoding="utf-8")
        maxima = {}
        for row in csv.DictReader(io.StringIO((local / "govern.csv").read_text())):
            for item in parse_class_stats(row["class_json"]):
                handle = item.get("handle", item.get("classid", "unknown"))
                maxima[handle] = max(maxima.get(handle, 0), item.get("bytes", 0))
        report["max_class_bytes"] = maxima
        report["non_rtps_bypassed"] = (
            maxima.get("7ac0:10") == 0 and maxima.get("7ac0:20", 0) > 1048576)
        client_end = json.loads(report["client"]["stdout"]).get("end", {})
        report["client_udp_summary"] = client_end.get("sum")
        server_end = json.loads((local / "server.json").read_text()).get("end", {})
        receiver = server_end.get("sum_received", server_end.get("sum"))
        report["receiver_udp_summary_raw"] = receiver
        valid_receiver = receiver and receiver.get("sender") is False and receiver.get("bytes", 0) > 0
        report["receiver_udp_goodput_bps"] = receiver.get("bits_per_second") if valid_receiver else None
        if not valid_receiver:
            report["receiver_summary_note"] = "No receiver goodput inferred; inspect server interval counters and raw end summary."
        cfg = json.loads(command("12", f"cat ~/{REMOTE}/{base}/profile/governor.json"))
        report["rtps_cap_packet_Bps"] = cfg["cap_packet_Bps"]
    finally:
        # Wait for the independently bounded governor before inspecting cleanup.
        if governor_started is not None:
            time.sleep(max(0, 27 - (time.monotonic() - governor_started)))
        roots = json.loads(command("12", "tc -j qdisc show dev wlo1"))
        if any(q.get("root") and q.get("handle") == "7ac0:" for q in roots):
            command("12", f"cd ~/{REMOTE} && sudo -n python3 -m rospacer restore --dev wlo1")
            roots = json.loads(command("12", "tc -j qdisc show dev wlo1"))
        report["qdisc_after"] = roots
        text = json.dumps(report, indent=2)
        (local / "summary.json").write_text(text, encoding="utf-8")
        for host in ("12", "10"):
            python(host, f"from pathlib import Path; Path.home().joinpath('{REMOTE}/{base}/summary.json').write_text(" + repr(text) + ")")
    print(json.dumps({k: v for k, v in report.items() if k != "client"}, indent=2))


if __name__ == "__main__":
    main()
