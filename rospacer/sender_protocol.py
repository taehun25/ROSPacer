"""Sender-host RTPS delivery observations, not a wireless airtime estimator.

Scope: one unencrypted RTPS/UDP writer, one peer, KEEP_ALL, large DATA_FRAG.
No custom receiver measurements. Natural ACKNACK is protocol feedback, not
proof of application callback execution or a maximum-capacity measurement.
"""
from collections import Counter,deque
import argparse,csv,json,math,select,socket,struct,time

def sequence(body,offset,endian,allow_zero=False):
    high,low=struct.unpack_from(endian+'iI',body,offset)
    value=(high<<32)+low
    if value<0 or (value==0 and not allow_zero):raise ValueError('invalid RTPS sequence number')
    return value

def rtps_events(payload,full_length=None):
    """Read only headers; DATA_FRAG bodies may intentionally be snaplen-truncated."""
    if len(payload)<20 or payload[:4]!=b'RTPS' or payload[4]!=2:return []
    full_length=len(payload) if full_length is None else full_length
    origin=payload[8:20].hex();destination=None;pos=20;events=[]
    while pos+4<=len(payload):
        kind,flags=payload[pos],payload[pos+1];endian='<' if flags&1 else '>'
        length=struct.unpack_from(endian+'H',payload,pos+2)[0]
        end=pos+4+length if length else (pos+4 if kind==0x09 and flags&2 else full_length)
        if end>full_length or end<pos+4:raise ValueError('invalid RTPS submessage extent')
        b=payload[pos+4:min(end,len(payload))]
        if kind in (0x30,0x31,0x32,0x33,0x34):raise ValueError('DDS security unsupported')
        if kind==0x0e:
            if len(b)<12:raise ValueError('truncated INFO_DST')
            destination=b[:12].hex()
        elif kind==0x0c:
            if len(b)<20:raise ValueError('truncated INFO_SRC')
            origin=b[8:20].hex()
        elif kind==0x16:
            if len(b)<32:raise ValueError('truncated DATA_FRAG header')
            sn=sequence(b,12,endian);start,count,fragment,size=struct.unpack_from(endian+'IHHI',b,20)
            if not start or not count or not fragment or not size:raise ValueError('invalid DATA_FRAG geometry')
            events.append({'kind':'data','writer':origin+':'+b[8:12].hex(),'writer_entity':b[8:12].hex(),'sequence':sn,'fragment_start':start,'fragment_count':count,'sample_size':size})
        elif kind in (0x06,0x12,0x08):
            required=20 if kind!=0x08 else 28
            if len(b)<required:raise ValueError('truncated control header')
            if kind!=0x08 and (not destination or destination=='0'*24):
                events.append({'kind':'unattributed_control','submessage':kind});pos=end;continue
            writer=(origin if kind==0x08 else destination)+':'+b[4:8].hex();reader=origin+':'+b[:4].hex()
            if kind==0x06:
                base=sequence(b,8,endian,allow_zero=True);bits=struct.unpack_from(endian+'I',b,16)[0]
                if bits>256:raise ValueError('oversized ACKNACK bitmap')
                words=(bits+31)//32;needed=20+words*4+4
                if len(b)<needed:raise ValueError('truncated ACKNACK bitmap/count')
                mask=struct.unpack_from(endian+str(words)+'I',b,20) if words else ()
                missing=[base+i for i in range(bits) if mask[i//32]&(1<<(31-i%32))]
                count=struct.unpack_from(endian+'I',b,20+words*4)[0]
                events.append({'kind':'ack','writer':writer,'reader':reader,'base':base,'missing':missing,'count':count})
            elif kind==0x12:
                sn=sequence(b,8,endian)
                if len(b)<28:raise ValueError('truncated NACK_FRAG set/count')
                bits=struct.unpack_from(endian+'I',b,20)[0]
                if bits>256 or len(b)<28+4*((bits+31)//32):raise ValueError('invalid NACK_FRAG bitmap')
                events.append({'kind':'nack_frag','writer':writer,'reader':reader,'sequence':sn})
            else:events.append({'kind':'gap','writer':writer})
        if end<=pos:raise ValueError('RTPS parser did not advance')
        pos=end
    return events

def ethernet_events(frame,wire_length=None):
    if len(frame)<42 or frame[12:14]!=b'\x08\x00':return None
    ip=frame[14:];ihl=(ip[0]&15)*4
    if ip[0]>>4!=4 or ihl!=20 or ip[9]!=17:return None
    total,fragment=struct.unpack_from('!HH',ip,2)[0],struct.unpack_from('!H',ip,6)[0]
    if fragment&0x3fff:raise ValueError('IP fragmentation unsupported')
    if len(ip)<28 or total<28:raise ValueError('truncated UDP header')
    length=struct.unpack_from('!H',ip,24)[0]
    if length<8 or length>total-20:raise ValueError('invalid UDP extent')
    return socket.inet_ntoa(ip[12:16]),socket.inet_ntoa(ip[16:20]),rtps_events(ip[28:28+length-8],length-8)

class DeliveryState:
    def __init__(self,source,peer,payload):
        self.source,self.peer,self.payload=source,peer,payload
        self.writer=None;self.reader=None;self.samples={};self.acks={};self.ack_count=None;self.ack_base=0;self.last_ack=None
        self.completed=deque();self.counts=Counter();self.errors=Counter();self.scope_error=None
        self.last_unique=None;self.last_nack=None;self.latest_ack_missing=[]
    def consume(self,src,dst,event,stamp):
        kind=event['kind']
        if kind=='gap' and src==self.source and dst==self.peer and event.get('writer')==self.writer:
            self.scope_error='GAP makes cumulative ACK delivery inference ambiguous';return
        if kind=='data' and src==self.source and dst==self.peer:
            if event['writer_entity'][-2:] not in ('02','03') or not self.payload<=event['sample_size']<=self.payload+4096:return
            if self.writer and event['writer']!=self.writer:self.scope_error='multiple large-data writers';return
            self.writer=event['writer'];sn=event['sequence'];self.counts['data_frag']+=1
            if sn in self.samples:
                if self.samples[sn]['sample_size']!=event['sample_size']:self.scope_error='sample size changed for same sequence'
                if event['fragment_start']==1:self.samples[sn]['first_fragment_seen']=True
                self.counts['repeated_sample_fragments']+=1
            else:
                self.samples[sn]={'first_seen':stamp,'first_fragment_seen':event['fragment_start']==1,'sample_size':event['sample_size']}
                self.counts['unique_samples']+=1
                self.last_unique=stamp
            if len(self.samples)>4096:self.scope_error='finite observation history exceeded'
        elif src==self.peer and dst==self.source and self.writer and event.get('writer')==self.writer:
            if kind=='gap':self.scope_error='GAP makes cumulative ACK delivery inference ambiguous';return
            if kind not in ('ack','nack_frag'):return
            if self.reader and self.reader!=event['reader']:self.scope_error='reader identity changed';return
            self.reader=event['reader'];self.counts[kind]+=1
            if kind=='nack_frag':self.last_nack=stamp;return
            if event['base']==0:self.counts['preemptive_ack']+=1;return
            if self.ack_count is not None:
                delta=(event['count']-self.ack_count)%(1<<32)
                if delta==0:self.counts['duplicate_ack']+=1;return
                if delta>=1<<31:self.counts['old_ack']+=1;return
            if event['base']<self.ack_base:self.scope_error='ACK base regressed';return
            if event['base']>max(self.samples)+1:self.scope_error='ACK refers beyond observed writer history';return
            self.ack_count=event['count'];self.ack_base=event['base'];self.last_ack=stamp;self.counts['requested_missing_samples']+=len(event['missing'])
            self.latest_ack_missing=event['missing']
            if self.scope_error:return
            for sn,sample in self.samples.items():
                if sn<event['base'] and sn not in self.acks and sample['first_fragment_seen']:
                    self.acks[sn]=stamp;self.completed.append((stamp,sn,stamp-sample['first_seen']))
    def snapshot(self,stamp,window=3):
        pending=[r for sn,r in self.samples.items() if sn not in self.acks]
        pending_ids=[sn for sn in self.samples if sn not in self.acks]
        recent=[r for r in self.completed if stamp-window<=r[0]<=stamp]
        return {'writer':self.writer,'reader':self.reader,'observed_samples':len(self.samples),'confirmed_samples':len(self.acks),'pending_samples':len(pending),
                'oldest_pending_s':max([stamp-r['first_seen'] for r in pending]+[0]),'ack_age_s':stamp-self.last_ack if self.last_ack is not None else None,
                'confirmed_payload_Bps_window':len(recent)*self.payload/window,'recent_ack_lag_s_max':max([r[2] for r in recent]+[0]),'scope_error':self.scope_error,
                'unconfirmed_tail':len(pending_ids)==1 and pending_ids[0]==max(self.samples) and self.ack_base==pending_ids[0] and not self.latest_ack_missing,
                'new_sample_age_s':stamp-self.last_unique if self.last_unique is not None else None,
                'nack_fragment_age_s':stamp-self.last_nack if self.last_nack is not None else None,
                'counts':dict(self.counts),'errors':dict(self.errors)}

def recommend(state,cap,ceiling,floor,delay=.5):
    """Limited congestion response, not beta/theta or maximum-capacity prediction."""
    if not 0<floor<=cap<=ceiling:raise ValueError('invalid protocol cap bounds')
    if state['scope_error']:return cap,'hold',state['scope_error']
    if not state['writer'] or not state['reader']:return cap,'hold','writer/reader observation warming up'
    if state.get('unconfirmed_tail') and state.get('new_sample_age_s',0)>delay and (state.get('nack_fragment_age_s') is None or state['nack_fragment_age_s']>delay):
        return cap,'hold','last sample lacks cumulative positive ACK; no loss or rate inference'
    if state['pending_samples'] and state['oldest_pending_s']>delay:
        return max(floor,cap*.8),'backoff','unconfirmed data exceeds delay budget'
    if state['pending_samples'] and (state['ack_age_s'] is None or state['ack_age_s']>delay):
        return max(floor,cap*.8),'backoff','natural ACK feedback missing/stale'
    if state['ack_age_s'] is not None and state['ack_age_s']<=delay:
        return min(ceiling,cap*1.02),'recover','fresh ACK progress; bounded increase'
    return cap,'idle','no fresh ACK progress; no increase'

def observe(dev,source,peer,payload,seconds,output,ceiling,skip_start=None,skip_seconds=0,actuator=None):
    from pathlib import Path
    if not 0<seconds<=120 or payload!=1048576:raise ValueError('finite 1MiB trial required')
    folder=Path(output);folder.mkdir(exist_ok=False,parents=True);s=DeliveryState(source,peer,payload)
    cap=ceiling;floor=ceiling*.1;started=time.monotonic();end=started+seconds;drops=0;skip=0
    sock=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));sock.bind((dev,0));sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4*1024*1024)
    buffer=bytearray(2048);next_tick=started;queue=[]
    columns=['monotonic_s','elapsed_s','status','reason','recommended_packet_Bps','observed_samples','confirmed_samples','pending_samples','oldest_pending_s','ack_age_s','confirmed_payload_Bps_window','recent_ack_lag_s_max','unconfirmed_tail','new_sample_age_s','nack_fragment_age_s','scope_error','capture_drops','masked_ack_events','applied_packet_Bps','htb_changes','class_json','qdisc_json']
    try:
        with (folder/'trace.csv').open('w',newline='') as out,(folder/'events.jsonl').open('w') as events,(folder/'ethernet.pcap').open('xb') as capture:
            w=csv.DictWriter(out,fieldnames=columns);w.writeheader();capture.write(struct.pack('<IHHIIII',0xa1b23c4d,2,4,0,0,2048,1))
            while time.monotonic()<end:
                if select.select([sock],[],[],max(0,min(.02,next_tick-time.monotonic())))[0]:
                    wire,anc,flags,address=sock.recvmsg_into([buffer],0,socket.MSG_TRUNC);stamp=time.monotonic();frame=bytes(buffer[:min(wire,len(buffer))])
                    # Retain only this IPv4 pair, not unrelated workstation traffic.
                    if len(frame)>=42 and frame[12:14]==b'\x08\x00' and frame[23]==17 and frame[26:30] in (socket.inet_aton(source),socket.inet_aton(peer)) and frame[30:34] in (socket.inet_aton(source),socket.inet_aton(peer)):
                        # Decode full MTU frames, including coalesced outgoing
                        # DATA_FRAG + control packets. Archive controls in full.
                        saved=frame if frame[26:30]==socket.inet_aton(peer) else frame[:320]
                        try:
                            if wire>len(buffer):raise ValueError('captured RTPS frame exceeds full-frame budget')
                            parsed=ethernet_events(frame,wire)
                            if parsed:
                                src,dst,decoded=parsed
                                if any(e['kind']!='data' for e in decoded):saved=frame
                                for e in decoded:
                                    mask=e['kind']=='ack' and skip_start is not None and skip_start<=stamp-started<skip_start+skip_seconds
                                    if mask:skip+=1
                                    else:s.consume(src,dst,e,stamp)
                                    if e['kind']!='data' or e['fragment_start']==1:events.write(json.dumps({'monotonic_s':stamp,'src':src,'dst':dst,'event':e,'masked':mask})+'\n')
                        except ValueError as e:
                            saved=frame;s.errors[str(e)]+=1;s.scope_error='unsupported/truncated captured RTPS input'
                        sec,ns=divmod(time.time_ns(),1000000000);capture.write(struct.pack('<4I',sec,ns,len(saved),wire)+saved)
                tick=time.monotonic()
                if tick>=next_tick:
                    stats=sock.getsockopt(263,6,12);current=struct.unpack_from('I',stats,4)[0];drops+=current
                    state=s.snapshot(tick)
                    if drops:state['scope_error']='packet capture drop; delivery history incomplete'
                    cap,status,reason=recommend(state,cap,ceiling,floor)
                    row={k:state[k] for k in columns if k in state};row.update(monotonic_s=tick,elapsed_s=tick-started,status=status,reason=reason,recommended_packet_Bps=cap,capture_drops=drops,masked_ack_events=skip)
                    if actuator is not None:row.update(actuator(cap,status,reason))
                    w.writerow(row);out.flush();events.flush();next_tick=tick+.2
    finally:sock.close()
    result={**s.snapshot(time.monotonic()),'confirmed_sequence_numbers':sorted(s.acks),'observed_sequence_numbers':sorted(s.samples),'capture_drops':drops,'masked_ack_events':skip,
            'HTB_applied':actuator is not None,'receiver_statistics_feedback':False,'natural_reader_protocol_feedback':True,'wireless_airtime_estimator':False,
            'scope':'single unencrypted RTPS/UDP writer+reader; no GAP; ACK does not prove application callback completion; window rate is ACK confirmation progress, not arrival rate or capacity'}
    (folder/'summary.json').write_text(json.dumps(result,indent=2));return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--dev',required=True);p.add_argument('--source',required=True);p.add_argument('--peer',required=True);p.add_argument('--out',required=True);p.add_argument('--seconds',type=float,default=45);p.add_argument('--cap-mbps',type=float,default=300);p.add_argument('--mask-start',type=float);p.add_argument('--mask-seconds',type=float,default=0);a=p.parse_args()
    print(json.dumps(observe(a.dev,a.source,a.peer,1048576,a.seconds,a.out,a.cap_mbps*1e6/8,a.mask_start,a.mask_seconds)),flush=True)
if __name__=='__main__':main()
