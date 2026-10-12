"""B2 calibration across two overlapping APs, with finite offline interference.

The additional pair must already be connected to AX1500. The controller visits
that AP only to prepare/collect; all main-link measurements run from SR2.
"""
import argparse
import io
import ipaddress
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import time

from deploy import KEY, ROOT, REMOTE, ssh
from w1_calibrate import fetch, launch, remote

SR2 = "iptime5GAX1500SR2"
OTHER = "iptime5GAX1500"


class Control:
    def __init__(self, ip4, ip5, interface, out):
        self.ip4, self.ip5, self.interface, self.out = ip4, ip5, interface, out
        self.bind = None
        self.visits = []

    def connect(self, ssid):
        q = subprocess.run(["netsh", "wlan", "connect", "name="+ssid,
                            "ssid="+ssid, "interface="+self.interface], capture_output=True)
        if q.returncode:
            raise RuntimeError(q.stdout.decode(errors="replace"))
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            state = subprocess.check_output(["netsh", "wlan", "show", "interfaces"]).decode(errors="replace")
            # Match a complete SSID value; AX1500 is also a prefix of SR2.
            matching = [line.split(":", 1)[1].strip() for line in state.splitlines()
                        if line.strip().startswith("SSID ")]
            if ssid in matching:
                ps = "Get-NetIPAddress -InterfaceAlias '"+self.interface.replace("'", "''")+"' -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress | ConvertTo-Json -Compress"
                raw = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps])
                addresses = json.loads(raw)
                if isinstance(addresses, str):
                    addresses = [addresses]
                valid = [s for s in addresses if s.startswith("192.168.0.")]
                if len(valid) == 1:
                    self.bind = valid[0]
                    os.environ["ROSPACER_SSH_BIND"] = self.bind
                    self.visits.append({"ssid": ssid, "bind": self.bind, "pc_monotonic_s": time.monotonic(), "state": state})
                    (self.out/"pc_ap_visits.json").write_text(json.dumps(self.visits, indent=2))
                    return
            time.sleep(1)
        raise RuntimeError("controller AP association/DHCP timeout")

    def extra(self, host, command, data=None):
        if host == "4":
            command = shlex.join(["ssh", "-o", "HostKeyAlias=192.168.0.4", "-o", "StrictHostKeyChecking=yes",
                                  "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "csilab@"+self.ip4, command])
        return subprocess.run(["ssh", "-b", self.bind, "-i", KEY,
                               "-o", "HostKeyAlias=192.168.0.5", "-o", "StrictHostKeyChecking=yes",
                               "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "csi@"+self.ip5, command],
                              input=data, capture_output=True, timeout=50)

    def python(self, host, source):
        q = self.extra(host, "python3 -", source.encode())
        if q.returncode:
            raise RuntimeError(q.stderr.decode(errors="replace"))
        return json.loads(q.stdout)

    def anchor(self, host):
        start = time.monotonic()
        r = self.python(host, "import json,time;print(json.dumps({'monotonic_s':time.monotonic(),'wall_ns':time.time_ns()}))")
        end = time.monotonic()
        r.update(pc_midpoint_s=(start+end)/2, roundtrip_s=end-start,
                 purpose="coarse campaign overlap only; not qualified E2E clocks")
        return r


def pair_check():
    reports = {}
    for h, dev in [("12", "wlo1"), ("10", "wlp2s0")]:
        source = "import subprocess,json\nr={}\nfor k,a in " + repr({"link": ["iw", "dev", dev, "link"], "info": ["iw", "dev", dev, "info"],
                 "qdisc": ["tc", "-j", "qdisc", "show", "dev", dev]}) + ".items():\n q=subprocess.run(a,capture_output=True,text=True,timeout=5);r[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}\nprint(json.dumps(r))"
        r = remote(h, source)
        if "SSID: "+SR2+"\n" not in r["link"]["stdout"] or "channel 149 " not in r["info"]["stdout"] or "width: 80 MHz" not in r["info"]["stdout"]:
            raise RuntimeError("main pair must stay on SR2 channel149/80MHz")
        if any(x.get("root") and x["kind"] != "noqueue" for x in json.loads(r["qdisc"]["stdout"])):
            raise RuntimeError("unexpected main-pair shaper")
        reports[h] = r
    return reports


def trial(run, name, out):
    print("START "+name, flush=True)
    before = pair_check()
    homes = {"12": "/home/csi2", "10": "/home/csi"}
    bases = {h: homes[h]+"/"+REMOTE+"/runs/"+run+"/b2" for h in homes}
    for h in homes:
        remote(h, "from pathlib import Path;Path("+repr(bases[h])+").mkdir(parents=True,exist_ok=True);print('{}')")
        args = ["timeout", "-k", "2", "43", "python3", "tools/telemetry.py", "--dev", "wlo1" if h == "12" else "wlp2s0",
                "--seconds", "38", "--interval", ".5", "--out", bases[h]+"/"+name+"_telemetry.jsonl"]
        launch(h, (["sudo", "-n"] if h == "12" else [])+args, homes[h]+"/"+REMOTE, bases[h]+"/"+name+"_telemetry.log")
    launch("10", ["timeout", "-k", "2", "39", "iperf3", "-s", "-1", "-B", "192.168.0.4", "-p", "55448", "-J"], homes["10"]+"/"+REMOTE, bases["10"]+"/"+name+"_server.json")
    time.sleep(.5)
    pc_start = time.monotonic()
    client = remote("12", "import subprocess,json,time\na=time.monotonic();q=subprocess.run(['iperf3','-c','192.168.0.4','-B','192.168.0.3','-p','55448','-u','-b','0','-l','1400','-t','30','-J'],capture_output=True,text=True,timeout=36);print(json.dumps({'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr,'start_mono':a,'end_mono':time.monotonic()}))")
    pc_end = time.monotonic()
    (out/(name+"_12_client.json")).write_text(json.dumps(client, indent=2))
    time.sleep(9)
    for h in homes:
        for suffix in ["telemetry.jsonl", "telemetry.log"]:
            (out/(name+"_"+h+"_"+suffix)).write_text(fetch(h, bases[h]+"/"+name+"_"+suffix), encoding="utf-8")
    server = fetch("10", bases["10"]+"/"+name+"_server.json")
    (out/(name+"_10_server.json")).write_text(server)
    srv = json.loads(server)
    streams = [row for interval in srv.get("intervals", []) for row in interval.get("streams", [])]
    seconds = sum(r["seconds"] for r in streams)
    result = {"trial": name, "pc_call_start_s": pc_start, "pc_call_end_s": pc_end, "pair_before": before,
              "receiver_bps": 8*sum(r["bytes"] for r in streams)/seconds if seconds else None,
              "receiver_interval_seconds": seconds, "client_rc": client["rc"], "receiver_error": srv.get("error"),
              "adaptive_estimate": None, "estimate_error": None,
              "scope": "throughput calibration only; active/busy/tx counters and qualified E2E clocks unavailable"}
    print(json.dumps({"DONE": name, "receiver_Mbps": result["receiver_bps"]/1e6 if result["receiver_bps"] else None}), flush=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--ip4", required=True)
    p.add_argument("--ip5", required=True)
    p.add_argument("--interface", default="Wi-Fi 2")
    a = p.parse_args()
    for s in [a.ip4, a.ip5]:
        if ipaddress.ip_address(s).version != 4:
            p.error("IPv4 required")
    if Path(a.run).name != a.run:
        p.error("run must be a single folder name")
    out = ROOT/"runs"/a.run/"b2"
    out.mkdir(parents=True, exist_ok=False)
    c = Control(a.ip4, a.ip5, a.interface, out)
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    results = []
    worker_path = "/home/csi/"+REMOTE+"/tools/w1_b2_worker.py"
    remote_out = "/home/csi/"+REMOTE+"/runs/"+a.run+"/b2_contender"
    server_out = "/home/csilab/"+REMOTE+"/runs/"+a.run+"/b2_server"
    try:
        c.connect(OTHER)
        inventories = {}
        for host in ["4", "5"]:
            r = c.python(host, "import subprocess,json\nr={}\nfor k,a in {'link':['iw','dev','wlp2s0','link'],'info':['iw','dev','wlp2s0','info'],'processes':['pgrep','-af',r'[r]un_sweep|[r]un_campaign|[i]perf3|[t]raffic.py'],'qdisc':['tc','-j','qdisc','show'],'power':['iw','dev','wlp2s0','get','power_save']}.items():\n q=subprocess.run(a,capture_output=True,text=True,timeout=5);r[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}\nprint(json.dumps(r))")
            if "SSID: "+OTHER+"\n" not in r["link"]["stdout"] or "channel 149 " not in r["info"]["stdout"] or r["processes"]["rc"] != 1:
                raise RuntimeError("additional pair must be idle on AX1500 channel149")
            inventories[host] = r
        (out/"additional_pair.json").write_text(json.dumps(inventories, indent=2))
        # The migration guard may have created this artifact parent as root.
        # Limit ownership repair to the dedicated run directory on each host.
        for host, account in [("4", "csilab"), ("5", "csi")]:
            folder = "/home/"+account+"/"+REMOTE+"/runs/"+a.run
            q = c.extra(host, shlex.join(["sudo", "-n", "chown", account+":"+account, folder]))
            if q.returncode:
                raise RuntimeError(q.stderr.decode())
        q = c.extra("5", "python3 -c "+shlex.quote("import sys;from pathlib import Path;p=Path("+repr(worker_path)+");p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(sys.stdin.buffer.read())"), (ROOT/"tools/w1_b2_worker.py").read_bytes())
        if q.returncode:
            raise RuntimeError(q.stderr.decode())
        c.connect(SR2)
        results.append(trial(a.run, "clean_otherAP_idle", out))
        (out/"progress.json").write_text(json.dumps(results, indent=2))
        c.connect(OTHER)
        anchor_before = c.anchor("5")
        server = c.python("4", "import subprocess,json;from pathlib import Path\np=Path("+repr(server_out)+");p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen("+repr(["timeout", "-k", "2", "220", "iperf3", "-s", "-B", a.ip4, "-p", "55449", "-J"])+",stdout=open(p/'server.jsonl','w'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True);print(json.dumps({'pid':q.pid}))")
        args = ["timeout", "-k", "2", "205", "python3", worker_path, "--peer", a.ip4, "--bind", a.ip5,
                "--seconds", "180", "--delay", "10", "--out", remote_out, "--source-commit", source_commit]
        worker = c.python("5", "import subprocess,json;from pathlib import Path\np=Path("+repr(remote_out)+");p.mkdir(parents=True,exist_ok=True);q=subprocess.Popen("+repr(args)+",stdout=open(p/'worker.log','w'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True);print(json.dumps({'pid':q.pid}))")
        (out/"launch.json").write_text(json.dumps({"server": server, "worker": worker, "clock_anchor_before": anchor_before, "source_commit": source_commit}, indent=2))
        c.connect(SR2)
        # Ensure the delayed worker has started before the first measurement.
        time.sleep(11)
        for name in ["B2_1", "B2_2", "B2_3"]:
            results.append(trial(a.run, name, out))
            (out/"progress.json").write_text(json.dumps(results, indent=2))
        c.connect(OTHER)
        c.python("5", "from pathlib import Path;Path("+repr(remote_out+"/stop")+").write_text('stop');print('{}')")
        c.python("5", "import time,json;from pathlib import Path\np=Path("+repr(remote_out+"/summary.json")+");end=time.monotonic()+20\nwhile not p.exists() and time.monotonic()<end:time.sleep(.5)\nassert p.exists(),'worker did not complete after stop';print('{}')")
        anchor_after = c.anchor("5")
        cleanup = c.python("4", "import os,signal,json,time;from pathlib import Path\npid="+str(server['pid'])+";p=Path('/proc')/str(pid)/'cmdline'\nr={'pid':pid,'already_exited':not p.exists()}\nif p.exists():\n cmd=p.read_bytes();assert b'iperf3' in cmd and b'55449' in cmd,cmd;assert os.getpgid(pid)==pid;os.killpg(pid,signal.SIGTERM);r['signalled']=True\nprint(json.dumps(r))")
        (out/"server_cleanup.json").write_text(json.dumps(cleanup, indent=2))
        for host, source, label in [("5", remote_out, "contender"), ("4", server_out, "server")]:
            script = "import sys,tarfile;from pathlib import Path\np=Path("+repr(source)+");a=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz');a.add(p,arcname="+repr(label)+");a.close()"
            q = c.extra(host, "python3 -c "+shlex.quote(script))
            if q.returncode:
                raise RuntimeError(q.stderr.decode())
            with tarfile.open(fileobj=io.BytesIO(q.stdout), mode="r:gz") as archive:
                archive.extractall(out, filter="data")
        contender = json.loads((out/"contender/summary.json").read_text())
        successful = [r for r in contender["bursts"] if r.get("rc") == 0 and not r.get("error")]
        if not successful:
            raise RuntimeError("no successful interference bursts; do not label B2 valid")
        offset = anchor_before["pc_midpoint_s"] - anchor_before["monotonic_s"]
        end_offset = anchor_after["pc_midpoint_s"] - anchor_after["monotonic_s"]
        for r in results:
            r["successful_contender_bursts_overlapping_call"] = sum(b["start_monotonic_s"]+offset < r["pc_call_end_s"] and b["end_monotonic_s"]+offset > r["pc_call_start_s"] for b in successful)
            r["campaign_clock_mapping_uncertainty_s"] = max(anchor_before["roundtrip_s"], anchor_after["roundtrip_s"])/2 + abs(offset-end_offset)
        (out/"summary.json").write_text(json.dumps({"trials": results, "contender": contender, "clock_anchor_before": anchor_before, "clock_anchor_after": anchor_after, "source_commit": source_commit, "model_error_validated": False}, indent=2))
        print(json.dumps({"trials": [{k: r[k] for k in ["trial", "receiver_bps", "successful_contender_bursts_overlapping_call"]} for r in results]}), flush=True)
    finally:
        # Restores controller connectivity even when a measurement fails. Remote
        # interference/server are independently bounded to205/220 seconds.
        c.connect(SR2)


if __name__ == "__main__":
    main()
