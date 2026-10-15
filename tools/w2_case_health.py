"""Between-case audit only. Called after all measurement jobs have been cleaned."""
import json, os, subprocess, time
from pathlib import Path

def audit(dev, expected_mac, expected_ssid, session):
    folder = Path(session)
    baseline = json.loads((folder/'baseline.json').read_text())
    def command(argv):
        return subprocess.check_output(argv, text=True, timeout=12).strip()
    # Every subsequent case starts from the guard's saved kernel baseline.
    # Its profile setup then applies the chosen comparison's own values.
    command(['sysctl', '-w'] + [k+'='+str(v) for k,v in baseline['sysctl'].items()])
    qdisc = json.loads(command(['tc','-j','qdisc','show','dev',dev]))
    processes = []
    for item in Path('/proc').iterdir():
        if not item.name.isdigit() or int(item.name) == os.getpid():
            continue
        try:
            args = (item/'cmdline').read_bytes().split(b'\0')
            text = b' '.join(args).decode(errors='replace')
            # Exclude the persistent guard; reject workers, DDS publishers,
            # governors and iperf children that could contaminate the next case.
            if any(x in text for x in ('/tools/w2_worker.py', '/tools/w2_traffic.py')) or ('rospacer' in text and 'sender-govern' in text) or any(Path(x.decode(errors='replace')).name == 'iperf3' for x in args if x):
                stat=(item/'stat').read_text().split()
                if stat[2] != 'Z':processes.append({'pid':int(item.name),'command':text})
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    mac=Path('/sys/class/net',dev,'address').read_text().strip()
    link=command(['iw','dev',dev,'link'])
    guards=[]
    for item in Path('/proc').iterdir():
        if not item.name.isdigit():continue
        try:
            args=(item/'cmdline').read_bytes().split(b'\0')
            if b'guard' in args and str(folder).encode() in args and any(b'w2_host_guard.py' in x for x in args):guards.append(int(item.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):pass
    problems=[]
    if mac != expected_mac:problems.append('host identity mismatch')
    if 'SSID: '+expected_ssid+'\n' not in link+'\n':problems.append('unexpected Wi-Fi association')
    if not qdisc or any(x.get('kind') != 'noqueue' for x in qdisc):problems.append('qdisc not restored to noqueue')
    if processes:problems.append('remaining experiment processes')
    if not guards or (folder/'end').exists() or (folder/'restoration.json').exists():problems.append('session guard inactive or expired')
    actual={k:int(command(['sysctl','-n',k])) for k in baseline['sysctl']}
    if actual != baseline['sysctl']:problems.append('kernel baseline mismatch')
    return {'passed':not problems,'problems':problems,'mac':mac,'link':link,'qdisc':qdisc,'remaining_processes':processes,'guards':guards,'sysctl':actual,'wall':time.time()}
