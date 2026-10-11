"""Bounded TCP throughput and ping pilot on the known 12 -> 10 SR2 path.

No tc/sysctl changes. No claim of DDS goodput or a quiet calibrated link.
All raw output is saved on the laptops and mirrored under runs/ locally.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from deploy import ROOT, REMOTE, ssh


def remote(host, script):
    p = ssh(host, "python3 -", script.encode())
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors="replace"))
    return json.loads(p.stdout)


def check_idle():
    for host in ("12", "10"):
        check = remote(host, r"""
import json,subprocess
p=subprocess.run(['pgrep','-af',r'[t]raffic\.py|[r]ospacer govern|[i]perf3'],capture_output=True,text=True)
q=subprocess.run(['tc','-j','qdisc','show','dev', 'wlo1' if """+repr(host)+""" == '12' else 'wlp2s0'],capture_output=True,text=True)
print(json.dumps(dict(process_code=p.returncode,processes=p.stdout,qdisc_code=q.returncode,qdisc=q.stdout)))
""")
        if check["process_code"] != 1:
            raise RuntimeError(f"Host {host} not idle or process check failed: {check['processes']}")
        if check["qdisc_code"] != 0 or any(q.get("root") and q.get("kind") != "noqueue"
                                          for q in json.loads(check["qdisc"])):
            raise RuntimeError(f"Host {host} has an unknown or custom qdisc")


def main():
    check_idle()
    stamp = datetime.now(timezone.utc).strftime("linkpilot_%Y%m%d_%H%M%S")
    prefix = f"import pathlib,json,subprocess,sys\np=pathlib.Path.home()/'{REMOTE}/runs/{stamp}'\np.mkdir(parents=True,exist_ok=True)\n"
    out = ROOT/"runs"/stamp
    out.mkdir(parents=True, exist_ok=True)
    report = dict(run=stamp, protocol="TCP iperf3, 10 s measured + 2 s omit",
                  repeats=3, quiet_link_verified=False, dds_goodput=False,
                  changed_configuration=False, trials=[])
    ping = remote("12", prefix+"""
q=subprocess.run(['ping','-n','-I','192.168.0.3','-c','20','-i','0.2','-W','1','192.168.0.4'],capture_output=True,text=True,timeout=30)
d=dict(exit_code=q.returncode,stdout=q.stdout,stderr=q.stderr)
(p/'ping.json').write_text(json.dumps(d,indent=2))
print(json.dumps(d))
""")
    (out/"ping.json").write_text(json.dumps(ping, indent=2), encoding="utf-8")
    for trial in range(1, 4):
        # A one-shot server with an independent deadline survives SSH interruption safely.
        server = remote("10", prefix+f"""
f=open(p/'server_{trial}.json','w')
q=subprocess.Popen(['timeout','25','iperf3','-s','-1','-B','192.168.0.4','-p','55201','--json'],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(pid=q.pid,deadline_s=25)))
""")
        time.sleep(.5)
        result = remote("12", prefix+f"""
q=subprocess.run(['iperf3','-c','192.168.0.4','-B','192.168.0.3','-p','55201','-t','10','-O','2','--json'],capture_output=True,text=True,timeout=22)
d=dict(exit_code=q.returncode,stdout=q.stdout,stderr=q.stderr)
(p/'client_{trial}.json').write_text(json.dumps(d,indent=2))
print(json.dumps(d))
""")
        (out/f"client_{trial}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        received = None
        if result["exit_code"] == 0:
            data = json.loads(result["stdout"])
            received = data.get("end", {}).get("sum_received", {}).get("bits_per_second")
        report["trials"].append(dict(trial=trial, server=server,
                                     exit_code=result["exit_code"], received_bps=received))
        if result["exit_code"] != 0:
            # Do not start another server while the previous deadline may still be running.
            break
        raw_server = remote("10", prefix+f"print(json.dumps(dict(raw=(p/'server_{trial}.json').read_text())))")
        (out/f"server_{trial}.json").write_text(raw_server["raw"], encoding="utf-8")
    remote("12", prefix+"(p/'summary.json').write_text("+repr(json.dumps(report, indent=2))+")\nprint(json.dumps(dict(saved=True)))")
    (out/"summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
