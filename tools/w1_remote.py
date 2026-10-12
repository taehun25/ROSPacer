"""Stream reviewed Python to only the verified SR2 laptops, preserving raw output."""
import argparse
from pathlib import Path
from deploy import ssh

def main():
    p=argparse.ArgumentParser()
    p.add_argument('host',choices=['12','10'])
    p.add_argument('source',type=Path)
    p.add_argument('--root',action='store_true')
    a=p.parse_args()
    q=ssh(a.host,('sudo -n ' if a.root else '')+'python3 -',a.source.read_bytes())
    print(q.stdout.decode(errors='replace'),end='')
    if q.stderr: print(q.stderr.decode(errors='replace'))
    raise SystemExit(q.returncode)

if __name__=='__main__':main()
