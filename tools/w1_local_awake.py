"""Temporary Windows sleep inhibition for this finite local lab task."""
import argparse
import ctypes
from pathlib import Path
import time
def main():
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);a=p.parse_args();folder=Path(a.folder)
    set_state=ctypes.windll.kernel32.SetThreadExecutionState
    if not set_state(0x80000001):raise OSError('cannot inhibit unattended sleep')
    (folder/'awake.ready').write_text('ready')
    try:
        end=time.monotonic()+21600
        while time.monotonic()<end and not (folder/'awake.end').exists():time.sleep(2)
    finally:set_state(0x80000000)
if __name__=='__main__':main()
