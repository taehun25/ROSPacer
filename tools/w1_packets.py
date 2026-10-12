"""Decode classic tcpdump captures: user DATA/DATA_FRAG ports, IPv4 fragments, TCP."""
import json,struct,socket
from pathlib import Path
from deploy import ROOT

def inspect(path):
    data=path.read_bytes()
    if len(data)<24:raise ValueError('missing pcap header')
    magic=data[:4];endian='<' if magic in (b'\xd4\xc3\xb2\xa1',b'\x4d\x3c\xb2\xa1') else '>' if magic in (b'\xa1\xb2\xc3\xd4',b'\xa1\xb2\x3c\x4d') else None
    if endian is None:raise ValueError('unsupported capture format')
    link=struct.unpack(endian+'IHHIIII',data[:24])[-1];pos=24
    result={'captured_packets':0,'IPv4_fragment_packets':0,'max_IP_length':0,'RTPS_packets':0,'user_DATA_FRAG_packets':0,'user_udp_source_ports':{},'tcp_payload_endpoints':{},'udp_user_IP_bytes':0,'linktype':link}
    while pos+16<=len(data):
        sec,usec,n,orig=struct.unpack(endian+'IIII',data[pos:pos+16]);pos+=16;frame=data[pos:pos+n];pos+=n;result['captured_packets']+=1
        off={1:14,113:16,276:20,101:0}.get(link)
        if off is None:raise ValueError('unsupported linktype')
        if link==1 and frame[12:14] in (b'\x81\x00',b'\x88\xa8'):off+=4
        ip=frame[off:]
        if len(ip)<20 or ip[0]>>4!=4:continue
        ihl=(ip[0]&15)*4;length=struct.unpack('!H',ip[2:4])[0];frag=struct.unpack('!H',ip[6:8])[0];result['max_IP_length']=max(result['max_IP_length'],length)
        if frag&0x3fff:result['IPv4_fragment_packets']+=1
        if frag&0x1fff:continue
        src=socket.inet_ntoa(ip[12:16]);dst=socket.inet_ntoa(ip[16:20]);transport=ip[ihl:]
        if len(transport)<8:continue
        sport,dport=struct.unpack('!HH',transport[:4])
        if ip[9]==6 and len(transport)>=20:
            header=(transport[12]>>4)*4;payload_len=max(0,length-ihl-header)
            if payload_len:
                key=f'{src}:{sport}->{dst}:{dport}';result['tcp_payload_endpoints'][key]=result['tcp_payload_endpoints'].get(key,0)+payload_len
            continue
        if ip[9]!=17 or transport[8:12]!=b'RTPS':continue
        result['RTPS_packets']+=1;payload=transport[8:];p=20;user=False
        while p+4<=len(payload):
            sid,flags=payload[p],payload[p+1];size=struct.unpack(('<' if flags&1 else '>')+'H',payload[p+2:p+4])[0];body=payload[p+4:]
            if sid in (0x15,0x16) and len(body)>=12 and body[11] in (0x02,0x03):
                user=True
                if sid==0x16:result['user_DATA_FRAG_packets']+=1
            if size==0:break
            p+=4+size
        if user:
            key=str(sport);result['user_udp_source_ports'][key]=result['user_udp_source_ports'].get(key,0)+1
            result['udp_user_IP_bytes']+=length
    result['qualification']='Sender capture records offered IP packets before over-the-air delivery; user ports decoded only from DATA/DATA_FRAG entity kind; TCP payload includes discovery/control if not separately decoded.'
    return result

def main():
    base=ROOT/'runs/w1_20261012_163000';results={}
    for p in base.glob('*/12/data.pcap'):
        try:results[p.parents[1].name]=inspect(p)
        except Exception as e:results[p.parents[1].name]={'error':str(e)}
    (base/'packet_evidence.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))

if __name__=='__main__':main()
