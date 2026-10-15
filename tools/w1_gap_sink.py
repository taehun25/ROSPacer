"""Finite UDP sink for observer-only PHY diagnosis; no control feedback."""
import argparse
import json
from pathlib import Path
import socket
import struct
import time


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1048576);sock.bind(('192.168.0.5',55926));sock.settimeout(.2)
    end=time.monotonic()+18;seen=set();by=0;first=None;last=None;duplicates=0
    try:
        while time.monotonic()<end:
            try:data,addr=sock.recvfrom(2048)
            except socket.timeout:continue
            if addr[0]!='192.168.0.11':continue
            if data==b'GAPEOF':break
            if len(data)!=1400 or data[:8]!=b'GAPPROBE':continue
            stamp=time.time();seq=struct.unpack_from('<Q',data,8)[0]
            if seq in seen:duplicates+=1;continue
            seen.add(seq);by+=len(data);first=first or stamp;last=stamp
    finally:sock.close()
    Path(a.out).write_text(json.dumps({'unique_packets':len(seen),'received_bytes':by,'duplicates':duplicates,'first_wall':first,'last_wall':last,'scope':'offline receiver result only; no feedback sent'}))


if __name__=='__main__':main()
