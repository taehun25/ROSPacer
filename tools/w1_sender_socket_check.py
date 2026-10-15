"""Finite raw-socket observability check; records MAC metadata only."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rospacer.sender_radio import SenderMonitor,summarize


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    profile=dict(AP='b0:38:6c:7d:f5:74',source_MAC='3c:0a:f3:02:d9:3b',receiver_MAC='3c:0a:f3:02:e4:c7',frequency_MHz=5745,exclusive_receiver=True)
    bins=[];samples=[];begin=time.monotonic()
    with SenderMonitor('wlp2s0') as m:
        m.configure_filter(profile)
        while time.monotonic()-begin<19:
            time.sleep(.5);now=time.monotonic()
            with m.lock:frames=list(m.frames)
            bins.append(summarize([r for r in frames if now-.5<=r[0]<=now],profile['AP'],profile['source_MAC'],profile['receiver_MAC'],exclusive_receiver=True))
            if len(samples)<100:
                samples.extend([r[1] for r in frames if r[1].get('kind')==2 and r[1].get('ra')==profile['receiver_MAC']][:100-len(samples)])
    Path(a.out).write_text(json.dumps({'bins':bins,'samples':samples,'monitor_removed':not Path('/sys/class/net/rpmon').exists()},indent=2))


if __name__=='__main__':main()
