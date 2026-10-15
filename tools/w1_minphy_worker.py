"""Finite sender-only survey/station sampling beside standard UDP iperf."""
import argparse,json,subprocess,time,re
from pathlib import Path
from rospacer.linux import observe

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--seconds',type=float,default=15);p.add_argument('--rate-mbps',type=float,default=600);a=p.parse_args();folder=Path(a.out);folder.mkdir(exist_ok=False);rows=[];errors=[];client=None;started=time.monotonic();end=started+a.seconds
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if a.rate_mbps:
        client=subprocess.Popen(['timeout','-k','2',str(int(a.seconds+8)),'iperf3','-c','192.168.0.5','-B','192.168.0.4','-p','55945','-u','-b',str(int(a.rate_mbps*1e6)),'-l','1400','-w','1048576','-t',str(int(a.seconds)),'-J'],stdout=open(folder/'client.json','w'),stderr=open(folder/'client.stderr','w'))
    while time.monotonic()<end:
        tick=time.monotonic()
        try:
            r=observe('wlp2s0');r['boot_id']=boot;ap=re.search(r'^Station ([0-9a-f:]{17})',r['station_raw'],re.M)
            if not ap:raise ValueError('source AP unavailable')
            r['AP']=ap[1];rows.append(r)
        except Exception as e:errors.append(str(e))
        time.sleep(max(0,.2-(time.monotonic()-tick)))
    rc=client.wait(timeout=10) if client else None
    result={'rows':rows,'errors':errors,'client_rc':rc,'rate_mbps':a.rate_mbps,'start_monotonic':started,'end_monotonic':time.monotonic(),'receiver_stats_feedback':False}
    (folder/'source.json').write_text(json.dumps(result,indent=2));print(json.dumps({'sample_count':len(rows),'errors':len(errors),'client_rc':rc}))
if __name__=='__main__':main()
