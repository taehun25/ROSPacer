"""Finite SSH TCP relay to the verified 4th laptop; diagnostic MSS only."""
import argparse
import os
import select
import socket
import time

def main():
    p=argparse.ArgumentParser();p.add_argument('--mss',type=int,choices=[256,512,1024,1448],required=True);a=p.parse_args()
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP,socket.TCP_MAXSEG,a.mss)
    s.bind(('192.168.0.5',0));s.settimeout(4);s.connect(('192.168.0.4',22));s.settimeout(4)
    deadline=time.monotonic()+35
    try:
        while time.monotonic()<deadline:
            ready,_,_=select.select([0,s],[],[],1)
            if 0 in ready:
                data=os.read(0,32768)
                if not data:break
                s.sendall(data)
            if s in ready:
                data=s.recv(32768)
                if not data:break
                while data:
                    sent=os.write(1,data);data=data[sent:]
    finally:s.close()

if __name__=='__main__':main()
