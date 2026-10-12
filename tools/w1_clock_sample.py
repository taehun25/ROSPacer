"""Read-only chrony sampler. Always numeric output; no clock steps."""
import argparse
import json
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=float,default=30)
    p.add_argument('--out',required=True)
    a = p.parse_args()
    if not 0 < a.seconds <= 300:
        p.error('bounded 0..300 seconds required')
    end = time.monotonic()+a.seconds
    with Path(a.out).open('w') as f:
        while time.monotonic()<end:
            tick=time.monotonic()
            row={'monotonic_s':tick,'wall_ns':time.time_ns()}
            for k,cmd in [('tracking',['chronyc','-n','tracking']),('sources',['chronyc','-n','sources']),('ntpdata',['chronyc','-n','ntpdata'])]:
                q=subprocess.run(cmd,capture_output=True,text=True,timeout=3)
                row[k]={'rc':q.returncode,'stdout':q.stdout,'stderr':q.stderr}
            f.write(json.dumps(row)+'\n');f.flush()
            time.sleep(max(0,min(.5-(time.monotonic()-tick),end-time.monotonic())))


if __name__=='__main__':
    main()
