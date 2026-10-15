"""Sender-local passive 802.11 observation; no receiver statistics input.

PHY payload serialization is a proxy, never full PPDU airtime. Unknown
metadata, incomplete capture and out-of-scope calibration are explicit holds.
"""
from collections import Counter, deque
import csv
import json
import math
from pathlib import Path
import re
import select
import signal
import socket
import statistics
import struct
import subprocess
import threading
import time

# Radiotap field alignment/size from the public radiotap definitions.
LAYOUT={0:(8,8),1:(1,1),2:(1,1),3:(2,4),4:(2,2),5:(1,1),6:(1,1),
        7:(2,2),8:(2,2),9:(2,2),10:(1,1),11:(1,1),12:(1,1),13:(1,1),
        14:(2,2),15:(2,2),16:(1,1),17:(1,1),18:(4,8),19:(1,3),
        20:(4,8),21:(2,12),22:(8,12),23:(2,12),24:(2,12),26:(1,1),27:(2,4)}


def radiotap(packet):
    if len(packet)<8 or packet[0]!=0:raise ValueError('invalid radiotap header')
    length=struct.unpack_from('<H',packet,2)[0]
    if not 8<=length<=len(packet):raise ValueError('truncated radiotap header')
    words=[];offset=4
    while True:
        if offset+4>length:raise ValueError('truncated presence bitmap')
        word=struct.unpack_from('<I',packet,offset)[0];words.append(word);offset+=4
        if not word&0x80000000:break
        if len(words)>8:raise ValueError('oversized presence bitmap')
    fields={};base=0
    for index,word in enumerate(words):
        for bit in range(31):
            if not word&(1<<bit):continue
            if bit==29:continue # no data; next bitmap restarts standard fields
            if bit==30:raise ValueError('unsupported vendor radiotap namespace')
            number=base+bit
            if number not in LAYOUT:raise ValueError('unsupported radiotap namespace/field '+str(number))
            alignment,size=LAYOUT[number];offset=(offset+alignment-1)//alignment*alignment
            if offset+size>length:raise ValueError('truncated radiotap field')
            fields.setdefault(number,packet[offset:offset+size]);offset+=size
        base=0 if word&(1<<29) else base+32
    return length,fields


def he_rate(fields):
    """HE SU only; reject unknown, STBC, DCM, RU and MU rather than guess."""
    if 23 not in fields:return None
    a,b,c,d,e,f=struct.unpack('<6H',fields[23])
    required=0x20|0x40|0x200|0x4000
    if a&3 or a&required!=required or not b&2:return None
    mcs=(c>>8)&15;dcm=bool(c&0x1000);stbc=bool(c&0x8000)
    bw=e&15;gi=(e>>4)&3;nss=f&15
    if dcm or stbc or mcs>11 or bw>3 or gi>2 or not 1<=nss<=8:return None
    bits=(1,2,2,4,4,6,6,6,8,8,10,10)[mcs]
    coding=(.5,.5,.75,.5,.75,2/3,.75,5/6,.75,5/6,.75,5/6)[mcs]
    tones=(234,468,980,1960)[bw];symbol_us=12.8+(.8,1.6,3.2)[gi]
    return tones*bits*coding*nss/(symbol_us*1e-6)/8


def data_rate(fields):
    """Known HE SU or explicit 5GHz OFDM RATE; never infer unknown HE."""
    if 23 in fields:return he_rate(fields)
    if 19 in fields or 21 in fields:return None
    if 2 not in fields or 3 not in fields:return None
    frequency,channel_flags=struct.unpack('<HH',fields[3])
    mbps=fields[2][0]*.5
    if frequency<5000 or not channel_flags&0x40 or mbps not in (6,9,12,18,24,36,48,54):return None
    return mbps*1e6/8


def decode(packet,wire_length=None,allow_bad_fcs=False):
    offset,fields=radiotap(packet)
    if len(packet)<offset+10:raise ValueError('truncated MAC header')
    fc=struct.unpack_from('<H',packet,offset)[0];kind=(fc>>2)&3;subtype=(fc>>4)&15
    flags=fields.get(1,b'\0')[0]
    if flags&0x40 and not allow_bad_fcs:raise ValueError('bad FCS')
    mac=lambda x:':'.join(f'{v:02x}' for v in x)
    result={'kind':kind,'subtype':subtype,'ra':mac(packet[offset+4:offset+10]),'bad_fcs':bool(flags&0x40),
            'retry':bool(fc&0x800),'wire_bytes':(wire_length or len(packet))-offset,
            'duration_us':struct.unpack_from('<H',packet,offset+2)[0],
            'tsft_us':struct.unpack('<Q',fields[0])[0] if 0 in fields else None,
            'legacy_rate_Mbps':fields[2][0]*.5 if 2 in fields else None,
            'frequency_MHz':struct.unpack_from('<H',fields[3])[0] if 3 in fields else None}
    if 5 in fields:result['signal_dbm']=struct.unpack('b',fields[5])[0]
    if 23 in fields:
        he=struct.unpack('<6H',fields[23]);result['he_format']=he[0]&3
        result['beamformed']=bool(he[4]&0x4000) if he[1]&0x10 else None
    # ACK/CTS have only RA. Following bytes may be FCS/padding, never a TA.
    if len(packet)>=offset+16 and not(kind==1 and subtype in (12,13)):result['ta']=mac(packet[offset+10:offset+16])
    if kind!=2:return result
    if len(packet)<offset+24:raise ValueError('truncated data header')
    ds=(fc>>8)&3;header=24+(6 if ds==3 else 0)+(2 if subtype&8 else 0)+(4 if fc&0x8000 and subtype&8 else 0)
    if len(packet)<offset+header:raise ValueError('truncated QoS/WDS header')
    result.update(ds=ds,addr3=mac(packet[offset+16:offset+22]),sequence=struct.unpack_from('<H',packet,offset+22)[0],tid=0,amsdu=False,rate_Bps=data_rate(fields))
    if subtype&8:
        qos=struct.unpack_from('<H',packet,offset+24+(6 if ds==3 else 0))[0]
        result.update(tid=qos&15,amsdu=bool(qos&0x80))
    if 20 in fields:
        ref,ampflags,crc,reserved=struct.unpack('<IHBB',fields[20])
        result.update(ampdu_ref=ref,ampdu_flags=ampflags)
    if fc&0x4000 and len(packet)>=offset+header+8:
        iv=packet[offset+header:offset+header+8]
        result['ccmp_pn']=int.from_bytes(bytes([iv[0],iv[1],iv[4],iv[5],iv[6],iv[7]]),'little')
    # Protected CCMP operating scope: 8-byte header + 8-byte MIC.
    # Retain A-MSDU subheaders/LLC/padding; do not call this UDP payload.
    result['body_bytes']=max(0,result['wire_bytes']-header-(16 if fc&0x4000 else 0)-(4 if flags&0x10 else 0))
    return result


def control_summary(frames,ap,receiver,frequency=5745):
    """CRC-valid receiver-directed RTS/CTS/BA candidates, not PPDU airtime.

    CTS has no transmitter address. Attribute it only when both the local
    timestamp delta and NAV decrement agree with the preceding AP->peer RTS.
    This is a diagnostic gate; neither NAV nor the driver timestamp is an
    approved physical airtime input. No receiver measurement is used.
    """
    counts=Counter();pending=None;nav=[];closed=[];mismatch=[]
    for stamp,packet,wire in frames:
        try:r=packet if isinstance(packet,dict) else decode(packet,wire)
        except ValueError:continue
        if r.get('parse_error') or r.get('bad_fcs') or r.get('frequency_MHz')!=frequency or r.get('kind')!=1:continue
        subtype=r['subtype'];ts=r.get('tsft_us')
        if subtype==11:
            if pending:counts['unclosed_rts_candidates']+=1
            pending=None
            if r.get('ta')==ap and r['ra']==receiver:
                counts['peer_rts_good']+=1
                duration=r.get('duration_us',0)
                if ts is None or not 0<duration<=4096:
                    counts['unsupported_rts_timing']+=1;continue
                pending={'ts':ts,'duration':duration,'cts':False};nav.append(duration)
        elif subtype==12 and r['ra']==ap:
            counts['ap_addressed_cts_good']+=1
            if not pending or ts is None or pending['cts']:continue
            # MT7921 exposes a 32-bit timestamp through the u64 TSFT field.
            delta=(ts-pending['ts'])%(1<<32)
            decrement=pending['duration']-r.get('duration_us',0)
            if 20<=delta<=200 and decrement>0 and abs(delta-decrement)<=4:
                pending['cts']=True;counts['peer_rts_cts_candidates']+=1
            else:counts['cts_timing_mismatch']+=1
        elif subtype==9 and r.get('ta')==receiver and r['ra']==ap:
            counts['peer_ba_good']+=1
            if not pending or not pending['cts'] or ts is None:continue
            delta=(ts-pending['ts'])%(1<<32)
            if 0<delta<=min(4096,pending['duration']+300):
                counts['peer_rts_cts_ba_candidates']+=1
                closed.append(delta);mismatch.append(delta-pending['duration'])
                pending=None
            else:counts['ba_outside_candidate_window']+=1
    if pending:counts['unclosed_rts_candidates']+=1
    return {'counts':dict(counts),'rts_nav_us_median':statistics.median(nav) if nav else None,
            'rts_to_ba_timestamp_us_median':statistics.median(closed) if closed else None,
            'rts_to_ba_minus_nav_us_median':statistics.median(mismatch) if mismatch else None,
            'qualification':'CRC-valid control exchange candidates only; CTS lacks TA; NAV/timestamp not qualified airtime; receiver exclusivity still required'}


def crc_summary(frames,ap,receiver,frequency=5745):
    """Failed-CRC headers are tentative diagnostic labels, never data input."""
    counts=Counter()
    for stamp,packet,wire in frames:
        try:r=packet if isinstance(packet,dict) else decode(packet,wire,allow_bad_fcs=True)
        except ValueError:counts['parse_errors']+=1;continue
        if r.get('parse_error'):counts['parse_errors']+=1;continue
        if r.get('frequency_MHz')!=frequency:continue
        if r.get('bad_fcs'):counts['bad_fcs_all']+=1
        if r.get('kind')==2 and r.get('subtype') in (0,8) and r.get('ta')==ap and r['ra']==receiver:
            suffix='bad' if r.get('bad_fcs') else 'good'
            counts['peer_'+suffix+'_frames']+=1
            counts['peer_'+suffix+'_candidate_body_bytes']+=r.get('body_bytes',0)
    return {'counts':dict(counts),'qualification':'bad-FCS addresses/lengths are tentative; excluded from all estimator serialization/coverage inputs'}


def fcs_counter(dev):
    phy=(Path('/sys/class/net')/dev/'phy80211').resolve().name
    try:return int((Path('/sys/kernel/debug/ieee80211')/phy/'statistics/dot11FCSErrorCount').read_text().strip())
    except (OSError,ValueError):return None


def pcap_frames(path):
    with Path(path).open('rb') as f:
        head=f.read(24)
        formats={b'\xd4\xc3\xb2\xa1':('<',1e6),b'\xa1\xb2\xc3\xd4':('>',1e6),b'\x4d\x3c\xb2\xa1':('<',1e9),b'\xa1\xb2\x3c\x4d':('>',1e9)}
        if len(head)!=24 or head[:4] not in formats:raise ValueError('classic pcap required')
        endian,scale=formats[head[:4]]
        if struct.unpack_from(endian+'I',head,20)[0]!=127:raise ValueError('radiotap link type required')
        while True:
            record=f.read(16)
            if not record:break
            if len(record)!=16:raise ValueError('truncated pcap record')
            sec,frac,size,wire=struct.unpack(endian+'4I',record)
            if size>65536:raise ValueError('oversized capture record')
            packet=f.read(size)
            if len(packet)!=size:raise ValueError('truncated pcap packet')
            yield sec+frac/scale,packet,wire


def summarize(frames,ap,source,receiver,frequency=5745,exclusive_receiver=False):
    counts=Counter();errors=Counter();rates=Counter();refs=Counter();sequences={}
    serial=0.;wire=0;unique_body=0;body=0;retry=0;amsdu=0;unknown_body=0;ambiguous_body=0
    for stamp,packet,wire_length in frames:
        try:
            if isinstance(packet,dict):
                if 'parse_error' in packet:raise ValueError(packet['parse_error'])
                r=packet
            else:r=decode(packet,wire_length)
            if r.get('bad_fcs'):raise ValueError('bad FCS')
        except ValueError as e:errors[str(e)]+=1;continue
        if r['frequency_MHz']!=frequency:errors['off-channel or missing frequency']+=1;continue
        if r.get('ta')==ap and r['ra']==source and r['kind']==1 and r['subtype']==9:counts['own_ba']+=1
        if r.get('ta')==receiver and r['ra']==ap and r['kind']==1 and r['subtype']==9:counts['peer_ba']+=1
        if r['kind']!=2 or r['subtype'] not in (0,8):continue # exclude null-data
        counts[r.get('ta','?')+' -> '+r['ra']]+=1
        # Addr3 is original source in From-DS frames: isolate our relayed MAC
        # traffic even when encrypted. Other hosts sending to the same reader
        # are not silently classified as our data.
        if not(r.get('ta')==ap and r['ra']==receiver and r['ds']==2):continue
        ambiguous=r['amsdu'] # encrypted inner A-MSDU sources are not visible
        if ambiguous:ambiguous_body+=r['body_bytes']
        if r['addr3']!=source and not(ambiguous and exclusive_receiver):
            counts['unattributed_peer_mpdu']+=1;continue
        counts['own_relay_mpdu']+=1;wire+=r['wire_bytes'];body+=r['body_bytes'];amsdu+=r['amsdu'];retry+=r['retry']
        key=(r['tid'],r['sequence'])
        duplicate=r['retry'] and key in sequences and stamp-sequences[key]<1
        if not duplicate:unique_body+=r['body_bytes']
        sequences[key]=stamp
        if 'ampdu_ref' in r:refs[r['ampdu_ref']]+=1
        if r['rate_Bps'] is None:unknown_body+=r['body_bytes']
        else:serial+=r['wire_bytes']/r['rate_Bps'];rates[str(round(r['rate_Bps']*8/1e6,3))]+=1
    known_wire=wire # all-known case only; unknown-rate windows cannot estimate.
    return {'counts':dict(counts),'errors':dict(errors),'relay_wire_bytes':wire,'relay_body_bytes':body,'relay_unique_body_bytes':unique_body,
            'relay_serialization_s':serial,'relay_rate_Bps':known_wire/serial if serial and not unknown_body else None,
            'unknown_rate_body_bytes':unknown_body,'ambiguous_amsdu_body_bytes':ambiguous_body,'exclusive_receiver_assumed':exclusive_receiver,'rates_Mbps':dict(rates),'relay_retries':retry,'amsdu_frames':amsdu,
            'ampdu_refs':len(refs),'shared_ampdu_refs':sum(v>1 for v in refs.values()),
            'qualification':'visible MAC/PHY proxies only; unique references do not prove one PPDU per MPDU'}


def window_uplink(samples,station_header_bytes=34):
    """Byte/retry weighted harmonic PHY proxy over the same counter window.

    Station rates are sampled values, not per-PPDU transmit timestamps.
    No receiver observations or invented duration fields are used.
    """
    from .native_radio import count_delta
    weight=serial=0.
    for old,new in zip(samples,samples[1:]):
        n=count_delta(old,new,'packets');by=count_delta(old,new,'bytes')
        retries=count_delta(old,new,'retries')
        if n<=0:
            if by:raise ValueError('uplink bytes without packets')
            continue
        ip=by-station_header_bytes*n
        rate=new['tx_Bps']
        if ip<=0 or not math.isfinite(rate) or rate<=0:raise ValueError('invalid window uplink geometry/rate')
        current=ip*(1+retries/n);weight+=current;serial+=current/rate
    if min(weight,serial)<=0:raise ValueError('no own packets for window uplink PHY')
    return weight/serial


def estimate(profile,old,new,visible):
    """Calibrated operating estimate using only sender-local inputs."""
    from .native_radio import check_scope,count_delta
    for key in ['BA_busy_s','relay_serialization_scale','relay_exchange_busy_s','idle_busy_fraction','O_up_s','O_down_s','alpha','cap_ceiling_skb_Bps']:
        if not math.isfinite(profile[key]) or profile[key]<0:raise ValueError('invalid sender calibration coefficient')
    if not 0<profile['alpha']<=1 or profile['cap_ceiling_skb_Bps']<=0:raise ValueError('invalid sender control bounds')
    if old['boot_id']!=new['boot_id'] or old['AP']!=new['AP']:raise ValueError('sender identity changed')
    check_scope(profile,old);check_scope(profile,new)
    dt=count_delta(old,new,'active_s');busy=count_delta(old,new,'busy_s');own=count_delta(old,new,'tx_s')
    if dt<=0 or not 0<=busy<=dt*1.1 or not 0<=own<=dt*1.1:raise ValueError('invalid sender survey window')
    n=count_delta(old,new,'packets');by=count_delta(old,new,'bytes')
    if n<=0:raise ValueError('no own packets')
    if visible.get('capture_drops',0):raise ValueError('sender monitor capture dropped packets')
    if visible['unknown_rate_body_bytes']:raise ValueError('unknown downlink PHY metadata')
    if visible['ambiguous_amsdu_body_bytes'] and not profile.get('exclusive_receiver'):raise ValueError('encrypted A-MSDU source attribution unavailable')
    if visible['counts'].get('unattributed_peer_mpdu',0)>profile.get('foreign_peer_frames_max',8):raise ValueError('other sender observed at receiver MAC')
    down=visible['relay_rate_Bps'];up=new.get('window_tx_Bps',new['tx_Bps']);frame=by/n;ip=frame-profile.get('station_link_header_bytes',14)
    if down is None or min(down,up)<=0:raise ValueError('missing sender-observed downlink PHY')
    if 'uplink_Mbps_range' in profile and not profile['uplink_Mbps_range'][0]<=up*8/1e6<=profile['uplink_Mbps_range'][1]:raise ValueError('uplink PHY outside sender calibration')
    if not 28<=ip<=1500:raise ValueError('unsupported packet geometry')
    coverage=visible['relay_unique_body_bytes']/by
    conservation=profile.get('relay_estimator')=='source-station-byte-conservation-v1'
    if conservation:
        if visible['counts'].get('own_relay_mpdu',0)<profile['PHY_sample_min_frames']:raise ValueError('insufficient CRC-valid downlink PHY samples')
        if not profile['PHY_sample_body_coverage'][0]<=coverage<=profile['PHY_sample_body_coverage'][1]:raise ValueError('PHY sampling visibility outside conservation profile')
        if visible['counts'].get('peer_ba',0)<profile['peer_BA_min_count']:raise ValueError('insufficient passive downlink control samples')
    else:
        low,high=profile['body_coverage_range']
        if not low<=coverage<=high:raise ValueError('sender relay visibility outside calibrated range')
    phy=down*8/1e6
    if not profile['downlink_Mbps_range'][0]<=phy<=profile['downlink_Mbps_range'][1]:raise ValueError('downlink PHY outside sender calibration')
    ba=visible['counts'].get('own_ba',0)
    peer_ba=visible['counts'].get('peer_ba',0)
    if peer_ba<=0:raise ValueError('missing passive downlink BlockAck exchanges')
    serialization=by/down if conservation else visible['relay_serialization_s']
    relay=profile['BA_busy_s']*ba+profile['relay_serialization_scale']*serialization+profile['relay_exchange_busy_s']*peer_ba
    # This MT7921 operating contract excludes own TX from raw busy.
    beta=(busy-profile['idle_busy_fraction']*dt-relay)/dt
    if not -.05<=beta<=1:raise ValueError('sender occupancy residual outside accepted range: '+str(beta))
    retries=count_delta(old,new,'retries')/n
    theta=((1+retries)*(profile['O_up_s']+ip/up)+profile['O_down_s']+ip/down)/frame
    rate=profile['alpha']*(1-beta)/theta
    if not math.isfinite(rate) or rate<=0:raise ValueError('invalid sender capacity estimate')
    return {'beta':beta,'relay_s':relay,'theta':theta,'cap_packet_Bps':min(profile['cap_ceiling_skb_Bps'],rate),
            'downlink_Mbps':phy,'uplink_Mbps':up*8/1e6,'body_coverage':coverage,'amsdu_frames':visible['amsdu_frames'],
            'relay_mpdu':visible['counts'].get('own_relay_mpdu',0),'ambiguous_amsdu_body_bytes':visible['ambiguous_amsdu_body_bytes']}


class SenderMonitor:
    """Same-radio monitor companion with bounded history and drop accounting."""
    def __init__(self,dev,name='rpmon',capture_path=None):
        self.dev=dev;self.name=name;self.created=False;self.sock=None;self.thread=None
        self.done=threading.Event();self.lock=threading.Lock();self.frames=deque();self.error=None;self.drop_events=deque();self.power_previous=None
        self.capture_path=capture_path;self.capture=None

    def command(self,*args):
        q=subprocess.run(args,capture_output=True,text=True,timeout=6)
        if q.returncode:raise ValueError(q.stderr.strip())
        return q.stdout

    def configure_filter(self,profile):
        """Kernel BPF: drop our own TX copies before the socket queue."""
        import ctypes
        expression='wlan addr1 '+profile['receiver_MAC']+' or wlan addr1 '+profile['source_MAC']+' or wlan addr2 '+profile['receiver_MAC']
        expression+=' or (wlan type ctl and (wlan addr1 '+profile['AP']+' or wlan addr2 '+profile['AP']+'))'
        # BPF return value trims the kernel skb before recvmsg sees it. Keep
        # full accepted length here; MSG_TRUNC copies only our 192-byte header
        # buffer while returning the original frame length for byte accounting.
        output=self.command('tcpdump','-ddd','-s','65535','-i',self.name,expression).splitlines()
        class Instruction(ctypes.Structure):_fields_=[('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint32)]
        class Program(ctypes.Structure):_fields_=[('length',ctypes.c_ushort),('filter',ctypes.POINTER(Instruction))]
        count=int(output[0]);instructions=(Instruction*count)(*(Instruction(*map(int,row.split())) for row in output[1:]))
        if count!=len(output)-1:raise ValueError('invalid compiled monitor BPF')
        program=Program(count,instructions);libc=ctypes.CDLL(None,use_errno=True)
        if libc.setsockopt(self.sock.fileno(),socket.SOL_SOCKET,26,ctypes.byref(program),ctypes.sizeof(program))!=0:
            raise OSError(ctypes.get_errno(),'cannot attach sender monitor BPF')

    def __enter__(self):
        if Path('/sys/class/net',self.name).exists():raise ValueError('preserve existing sender monitor')
        try:
            power=re.search(r'Power save:\s*(on|off)',self.command('iw','dev',self.dev,'get','power_save'))
            if not power:raise ValueError('cannot preserve sender power-save state')
            self.power_previous=power[1]
            if self.power_previous=='on':self.command('iw','dev',self.dev,'set','power_save','off')
            self.command('iw','dev',self.dev,'interface','add',self.name,'type','monitor','flags','control','otherbss','fcsfail');self.created=True
            self.command('ip','link','set','dev',self.name,'up')
            if self.capture_path:
                self.capture=open(self.capture_path,'xb')
                self.capture.write(struct.pack('<IHHIIII',0xa1b23c4d,2,4,0,0,192,127))
            self.sock=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4*1024*1024)
            self.sock.bind((self.name,0));self.sock.setblocking(False)
            self.thread=threading.Thread(target=self.read,daemon=True);self.thread.start();return self
        except BaseException:
            self.close();raise

    def read(self):
        buffer=bytearray(192)
        try:
            while not self.done.is_set():
                if not select.select([self.sock],[],[],.1)[0]:continue
                size,anc,flags,addr=self.sock.recvmsg_into([buffer],0,socket.MSG_TRUNC)
                stamp=time.monotonic()
                if self.capture:
                    sec,frac=divmod(time.time_ns(),1000000000);length=min(size,len(buffer))
                    self.capture.write(struct.pack('<4I',sec,frac,length,size)+buffer[:length])
                try:parsed=decode(bytes(buffer[:min(size,len(buffer))]),size,allow_bad_fcs=True)
                except ValueError as e:parsed={'parse_error':str(e)}
                entry=(stamp,parsed,size)
                with self.lock:
                    self.frames.append(entry)
                    while self.frames and self.frames[0][0]<stamp-5:self.frames.popleft()
                    if len(self.frames)>150000:
                        self.frames.popleft();self.drop_events.append((stamp,1))
        except (OSError,ValueError) as e:
            if not self.done.is_set():self.error=str(e)

    def window(self,start,end,profile):
        if self.error:raise ValueError('sender monitor failed: '+self.error)
        with self.lock:frames=[r for r in self.frames if start<=r[0]<=end]
        stats=self.sock.getsockopt(263,6,12) # SOL_PACKET, PACKET_STATISTICS
        if len(stats)<8:raise ValueError('missing packet capture drop statistics')
        dropped=struct.unpack_from('I',stats,4)[0]
        with self.lock:
            if dropped:self.drop_events.append((end,dropped))
            # Account conservatively for drops reported since the preceding
            # collection, and recover after an entirely clean window.
            while self.drop_events and self.drop_events[0][0]<start-.5:self.drop_events.popleft()
            window_drops=sum(count for stamp,count in self.drop_events)
        result=summarize(frames,profile['AP'],profile['source_MAC'],profile['receiver_MAC'],profile['frequency_MHz'],profile['exclusive_receiver'])
        result['capture_drops']=window_drops
        result['control_diagnostic']=control_summary(frames,profile['AP'],profile['receiver_MAC'],profile['frequency_MHz'])
        result['crc_diagnostic']=crc_summary(frames,profile['AP'],profile['receiver_MAC'],profile['frequency_MHz'])
        return result

    def close(self):
        self.done.set()
        if self.thread:self.thread.join(timeout=2)
        if self.sock:self.sock.close();self.sock=None
        try:
            if self.created:
                self.command('iw','dev',self.name,'del');self.created=False
        finally:
            try:
                if self.power_previous=='on':
                    self.command('iw','dev',self.dev,'set','power_save','on');self.power_previous=None
            finally:
                if self.capture:
                    capture,self.capture=self.capture,None;capture.close()

    def __exit__(self,*args):self.close()


def govern(cfg,seconds,trace,dry_run=False,shadow=False):
    from .native_radio import snapshot,check_scope
    from .linux import Shaper
    import hashlib
    import os
    if 'sender_radio_calibration' not in cfg:raise ValueError('sender-only calibration profile required')
    if not isinstance(cfg.get('cap_packet_Bps'),(int,float)) or not math.isfinite(cfg['cap_packet_Bps']) or cfg['cap_packet_Bps']<=0:raise ValueError('positive finite sender initial cap required')
    profile=cfg['sender_radio_calibration'];reader=cfg['native_reader']
    if not shadow and profile.get('validated') is not True:raise ValueError('sender-only calibration has not passed held-out validation')
    if not math.isfinite(seconds) or not 0<seconds<=120:raise ValueError('sender prototype duration must be <=120s')
    if os.uname().release!=profile['kernel_release']:raise ValueError('kernel outside sender scope')
    for name,digest in profile['module_srcversions'].items():
        if Path('/sys/module',name,'srcversion').read_text().strip()!=digest:raise ValueError('driver outside sender scope')
    if hashlib.sha256(Path(reader).read_bytes()).hexdigest()!=profile['reader_sha256']:raise ValueError('sender native reader changed')
    if profile['payload_bytes']!=cfg['payload_bytes']:raise ValueError('payload outside sender scope')
    if Path('/sys/class/net',cfg['dev'],'address').read_text().strip()!=profile['source_MAC']:raise ValueError('wrong source MAC')
    check_scope(profile,snapshot(cfg['dev'],reader))
    if dry_run:return {'mode':'adaptive-sender','changed_system':False,'input_contract':'sender-local-passive-monitor','shadow':shadow}
    columns=['monotonic_s','mode','status','cap_packet_Bps','beta','theta','relay_s','downlink_Mbps','uplink_Mbps','body_coverage','amsdu_frames','relay_mpdu','ambiguous_amsdu_body_bytes','mean_station_bytes','capture_drops','relay_wire_bytes','relay_body_bytes','visible_errors','control_diagnostic','crc_diagnostic','source_fcs_error_delta','source_fcs_counter_status','error']
    samples=None
    cap=cfg['cap_packet_Bps'];history=deque();shaper=None;deadline=time.monotonic()+seconds
    previous=signal.getsignal(signal.SIGTERM)
    def stop(*args):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop)
    try:
        if shadow and cfg.get('sender_snapshot_file'):samples=open(cfg['sender_snapshot_file'],'x')
        with SenderMonitor(cfg['dev'],capture_path=cfg.get('sender_capture_file') if shadow else None) as monitor:
            monitor.configure_filter(profile)
            if not shadow:
                shaper=Shaper(cfg);shaper.install()
            with open(trace,'w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
                while time.monotonic()<deadline:
                    tick=time.monotonic();row={'monotonic_s':tick,'mode':'sender-shadow' if shadow else 'adaptive-sender','status':'hold','cap_packet_Bps':cap,'error':''}
                    try:
                        sample=snapshot(cfg['dev'],reader);sample['fcs_errors']=fcs_counter(cfg['dev']);stamp=time.monotonic();history.append((stamp,sample))
                        if samples:samples.write(json.dumps({'monotonic_s':stamp,'sample':sample})+'\n');samples.flush()
                        while len(history)>2 and history[1][0]<stamp-3:history.popleft()
                        if len(history)<2 or stamp-history[0][0]<2:raise ValueError('sender observation warming up')
                        if stamp-tick>.6:raise ValueError('sender counter collection stale')
                        visible=monitor.window(history[0][0],stamp,profile)
                        row['control_diagnostic']=json.dumps(visible['control_diagnostic'])
                        row['crc_diagnostic']=json.dumps(visible['crc_diagnostic'])
                        first_fcs=history[0][1]['fcs_errors'];last_fcs=sample['fcs_errors']
                        if first_fcs is None or last_fcs is None:row['source_fcs_counter_status']='missing'
                        elif last_fcs<first_fcs:row['source_fcs_counter_status']='reset'
                        else:row.update(source_fcs_error_delta=last_fcs-first_fcs,source_fcs_counter_status='available (radio-wide cached counter)')
                        n=sample['packets']-history[0][1]['packets']
                        row.update(capture_drops=visible['capture_drops'],body_coverage=visible['relay_unique_body_bytes']/max(1,sample['bytes']-history[0][1]['bytes']),mean_station_bytes=(sample['bytes']-history[0][1]['bytes'])/n if n>0 else '',relay_mpdu=visible['counts'].get('own_relay_mpdu',0),relay_wire_bytes=visible['relay_wire_bytes'],relay_body_bytes=visible['relay_body_bytes'],visible_errors=json.dumps(visible['errors']))
                        if profile.get('uplink_sampling')=='window-byte-retry-harmonic':sample['window_tx_Bps']=window_uplink([x for _,x in history],profile['station_link_header_bytes'])
                        result=estimate(profile,history[0][1],sample,visible)
                        cap=min(profile['cap_ceiling_skb_Bps'],max(1000,.7*cap+.3*result['cap_packet_Bps']))
                        if shaper:shaper.change(cap)
                        row.update(result,status='estimated' if shadow else 'updated',cap_packet_Bps=cap)
                    except (ValueError,KeyError,OSError,json.JSONDecodeError) as e:row['error']=str(e)
                    writer.writerow(row);f.flush();time.sleep(max(0,min(.2-(time.monotonic()-tick),deadline-time.monotonic())))
    finally:
        try:
            if shaper:shaper.close()
        finally:
            try:
                if samples:samples.close()
            finally:signal.signal(signal.SIGTERM,previous)
    return {'mode':'adaptive-sender','shadow':shadow,'restored':True,'input_contract':'sender-local-passive-monitor','trace':str(trace)}
