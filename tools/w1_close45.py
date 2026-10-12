"""End the owned W1 power session and remove temporary wired clock setup."""
import json
import time
from deploy import ROOT,REMOTE,ssh
from w1_b2 import Control,OTHER,SR2


def main():
    base=ROOT/'runs/w1_20261012_radio45';out=base/'close45';out.mkdir(exist_ok=False)
    c=Control('192.168.0.4','192.168.0.5','Wi-Fi 2',out);result={}
    homes={'4':'/home/csilab','5':'/home/csi'}
    try:
        c.connect(OTHER)
        for h,home in homes.items():
            folder=home+'/'+REMOTE+'/runs/w1_20261012_radio45/session_independent10'
            q=c.extra(h,'sudo -n python3 '+home+'/'+REMOTE+'/tools/w1_session.py end --folder '+folder+' --dev wlp2s0')
            if q.returncode:raise RuntimeError(q.stderr.decode())
            result[h]={'session_restoration':json.loads(q.stdout)}
        time.sleep(3)
        for h,command in [('4','sudo -n chronyc -n delete 192.168.50.1'),('5','sudo -n chronyc -n deny 192.168.50.2'),
                          ('4','sudo -n nmcli device disconnect enp1s0'),
                          ('5','sudo -n python3 /home/csi/'+REMOTE+'/tools/w1_clock_link.py end --folder /home/csi/'+REMOTE+'/runs/w1_20261012_radio45/clock_link/5')]:
            q=c.extra(h,command);result[h].setdefault('temporary_setup_cleanup',[]).append({'command':command,'rc':q.returncode,'stdout':q.stdout.decode(),'stderr':q.stderr.decode()})
            if q.returncode:raise RuntimeError('cleanup failed: '+command+' '+q.stderr.decode())
        code="""import json,subprocess,time
from pathlib import Path
commands={'link':['iw','dev','wlp2s0','link'],'qdisc':['tc','-j','qdisc','show','dev','wlp2s0'],
 'power':['iw','dev','wlp2s0','get','power_save'],'sysctl':['sysctl','net.core.rmem_max','net.core.wmem_max'],
 'ethernet':['ip','-j','addr','show','dev','enp1s0'],'interfaces':['iw','dev'],
 'processes':['pgrep','-af',r'[t]raffic.py|[r]ospacer govern|[i]perf3|[w]1_session.py|[w]1_monitor_guard.py|[w]1_outage.py|[w]1_wifi_shaper|[w]1_adaptive_probe.py|[t]elemetry.py|[w]1_wired_guard.py'],
 'rules':['sudo','-n','iptables-save'],'clock_sources':['chronyc','-n','sources']}
r={'wall_ns':time.time_ns(),'cpu_governors':{str(p):p.read_text().strip() for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_governor')}}
for name,argv in commands.items():
 q=subprocess.run(argv,capture_output=True,text=True,timeout=8);r[name]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
print(json.dumps(r))
"""
        for h in homes:
            raw=c.python(h,code);r=result[h];r.update(raw=raw,ssid_AX='SSID: '+OTHER+'\n' in raw['link']['stdout'],
                qdisc_noqueue=all(x['kind']=='noqueue' for x in json.loads(raw['qdisc']['stdout'])),
                experiment_processes_ended=raw['processes']['rc']==1,
                temporary_firewall_rules_absent='W1' not in raw['rules']['stdout'] and 'w1' not in raw['rules']['stdout'],
                power_session='independent10 session ended and baseline restored',wire_management='temporary address/source removed; stored profiles preserved')
            if not all([r['ssid_AX'],r['qdisc_noqueue'],r['experiment_processes_ended'],r['session_restoration']['restored'],r['temporary_firewall_rules_absent']]):raise RuntimeError('final audit failed: '+h)
        c.connect(SR2)
        q=ssh('10',"iw dev wlp2s0 info; test ! -e /sys/class/net/w1mon")
        result['10_monitor']={'rc':q.returncode,'managed_info':q.stdout.decode(),'stderr':q.stderr.decode()}
        if q.returncode:raise RuntimeError('observer monitor cleanup not confirmed')
        (base/'final_receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({h:{k:v for k,v in r.items() if k not in ['raw','session_restoration','temporary_setup_cleanup']} for h,r in result.items()},indent=2))
    finally:
        (out/'cleanup_receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        c.connect(SR2)


if __name__=='__main__':main()
