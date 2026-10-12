"""Inspect bounded classic-pcap 802.11 headers without decoding payloads.

Presence of radiotap metadata is recorded, not treated as valid airtime.
Capture completeness cannot be inferred from these counts.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct


def analyze(path):
    raw=path.read_bytes()
    formats={b'\xd4\xc3\xb2\xa1':('<',1e6),b'\xa1\xb2\xc3\xd4':('>',1e6),
             b'\x4d\x3c\xb2\xa1':('<',1e9),b'\xa1\xb2\x3c\x4d':('>',1e9)}
    endian,scale=formats[raw[:4]]
    link=struct.unpack_from(endian+'I',raw,20)[0]
    if link!=127:raise ValueError('radiotap classic pcap required')
    counts=Counter();metadata=Counter();directions=Counter();bins={};stamps=[]
    offset=24
    while offset<len(raw):
        if offset+16>len(raw):raise ValueError('truncated record header')
        sec,frac,length,wire=struct.unpack_from(endian+'IIII',raw,offset);offset+=16
        packet=raw[offset:offset+length];offset+=length
        if len(packet)!=length:raise ValueError('truncated packet')
        counts['records']+=1;stamps.append(sec+frac/scale)
        if len(packet)<8:counts['short_radiotap']+=1;continue
        rtlen=struct.unpack_from('<H',packet,2)[0]
        present=struct.unpack_from('<I',packet,4)[0]
        if rtlen<8 or rtlen+2>len(packet):counts['short_wlan']+=1;continue
        fc=struct.unpack_from('<H',packet,rtlen)[0];kind=(fc>>2)&3
        counts[{0:'management',1:'control',2:'data',3:'extension'}[kind]]+=1
        if kind!=2 or rtlen+16>len(packet):continue
        for bit,name in [(2,'legacy_rate'),(19,'HT_MCS'),(20,'AMPDU'),(21,'VHT'),(23,'HE')]:
            if present&(1<<bit):metadata[name]+=1
        mac=lambda b:':'.join(f'{v:02x}' for v in b)
        ra=mac(packet[rtlen+4:rtlen+10]);ta=mac(packet[rtlen+10:rtlen+16])
        direction=ta+' -> '+ra;directions[direction]+=1
        stamp=sec+frac/scale;bucket=int(stamp-stamps[0])
        bins.setdefault(bucket,Counter())[direction]+=1
        if fc&(1<<11):counts['data_retry_flag']+=1
    return {'sha256':hashlib.sha256(raw).hexdigest(),'file_bytes':len(raw),'linktype':link,
            'capture_span_s':stamps[-1]-stamps[0] if stamps else None,'counts':dict(counts),
            'data_radiotap_presence':dict(metadata),'data_directions':dict(directions),
            'data_direction_bins_1s':{str(k):dict(v) for k,v in bins.items()},
            'qualification':'header-only evidence; metadata presence does not prove valid airtime or complete reception'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture');a=p.parse_args()
    path=Path(a.capture);result=analyze(path)
    path.with_suffix('.headers.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='data_direction_bins_1s'},indent=2))
