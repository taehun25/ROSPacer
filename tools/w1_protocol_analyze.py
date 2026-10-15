"""Offline application-sequence cross-check; never feeds receiver data online."""
import csv,hashlib,json,struct,statistics
from pathlib import Path
from deploy import ROOT
BASE=ROOT/'runs/w1_20261014_sender_bounded'
def app_sequences(path):
    values={};mismatch=[]
    with path.open('rb') as f:
        head=f.read(24);assert head[:4]==b'\x4d\x3c\xb2\xa1' and struct.unpack_from('<I',head,20)[0]==1
        while True:
            rec=f.read(16)
            if not rec:break
            sec,ns,n,wire=struct.unpack('<4I',rec);frame=f.read(n)
            if len(frame)<62 or frame[12:14]!=b'\x08\x00' or frame[23]!=17:continue
            if frame[26:30]!=bytes([192,168,0,4]) or frame[30:34]!=bytes([192,168,0,5]):continue
            p=frame[42:];pos=20
            if p[:4]!=b'RTPS':continue
            while pos+4<=len(p):
                kind,flags=p[pos:pos+2];e='<' if flags&1 else '>';length=struct.unpack_from(e+'H',p,pos+2)[0];b=p[pos+4:min(pos+4+length,len(p))]
                if kind==0x16 and len(b)>=56 and b[11] in (2,3):
                    hi,lo=struct.unpack_from(e+'iI',b,12);sn=(hi<<32)+lo;frag=struct.unpack_from(e+'I',b,20)[0];size=struct.unpack_from(e+'I',b,28)[0]
                    if frag==1 and size==1048592:
                        start=4+struct.unpack_from(e+'H',b,2)[0]
                        if flags&2:
                            while start+4<=len(b):
                                pid,sz=struct.unpack_from(e+'HH',b,start);start+=4
                                if pid==1:break
                                start+=(sz+3)//4*4
                        cdr=b[start:]
                        if len(cdr)>=24 and cdr[:2] in (b'\0\1',b'\0\0'):
                            ce='<' if cdr[:2]==b'\0\1' else '>'
                            dims,offset,count=struct.unpack_from(ce+'III',cdr,4)
                            if dims==0 and offset==0 and count==1048576:
                                seq=struct.unpack_from('!Q',cdr,16)[0]
                                if sn in values and values[sn]!=seq:mismatch.append(sn)
                                values[sn]=seq
                if not length:break
                pos+=4+length
    return values,mismatch
def main():
    protocols={version:json.loads((BASE/('protocol_'+version+'.json')).read_text()) for version in ['v2','v3']};results=[]
    for tag in ['fast_clean']+protocols['v2']['trials']+protocols['v3']['trials']:
        version='v1' if tag=='fast_clean' else ('v3' if tag in protocols['v3']['trials'] else 'v2')
        protocol=protocols.get(version,protocols['v2'])
        folder=BASE/tag
        if not (folder/'summary.json').exists():continue
        r=json.loads((folder/'summary.json').read_text());o=json.loads((folder/'4/protocol/summary.json').read_text());mapping,mismatch=app_sequences(folder/'4/protocol/ethernet.pcap')
        pub=json.loads((folder/'4/pub.json').read_text());sub=json.loads((folder/'5/sub.json').read_text());received={x['seq'] for x in sub['records']}
        confirmed={mapping[sn] for sn in o['confirmed_sequence_numbers'] if sn in mapping};missing_map=[sn for sn in o['observed_sequence_numbers'] if sn not in mapping]
        rows=list(csv.DictReader((folder/'4/protocol/trace.csv').open()));steady=[x for x in rows if pub['measurement_started_ns']/1e9+3<=float(x['monotonic_s'])<=pub['measurement_ended_ns']/1e9-1]
        caps=[float(x['recommended_packet_Bps'])*8/1e6 for x in rows];backoff=[x for x in rows if x['status']=='backoff'];masked_backoff=[x for x in backoff if 12<=float(x['elapsed_s'])<=18]
        tail=[x for x in rows if float(x['monotonic_s'])>=pub['measurement_ended_ns']/1e9+1]
        r.update(version=version,application_mapping_count=len(mapping),mapping_missing=missing_map,mapping_inconsistent=mismatch,false_confirmation_sequences=sorted(confirmed-received),receiver_unconfirmed_sequences=sorted(received-confirmed),
                 confirmed_application_sequences=sorted(confirmed),confirmed_receiver_fraction=len(confirmed&received)/len(received) if received else 0,
                 steady_rows=len(steady),steady_nonhold_fraction=sum(x['status']!='hold' for x in steady)/len(steady) if steady else 0,
                 cap_Mbps_range=[min(caps),max(caps)],backoff_updates=len(backoff),masked_backoff_updates=len(masked_backoff),
                 tail_backoff_updates=sum(x['status']=='backoff' for x in tail),tail_ambiguity_hold_updates=sum(x['status']=='hold' and 'last sample' in x['reason'] for x in tail),
                 input_check_pass=not missing_map and not mismatch and confirmed==received and r['capture_drops']==0 and r['scope_error'] is None and r['observed']==r['published'],
                 registered_fraction_gate_pass=not missing_map and not mismatch and not (confirmed-received) and len(confirmed&received)>=.95*len(received) and r['capture_drops']==0 and r['scope_error'] is None and r['observed']>=.95*r['published'],
                 mask_response_pass=(not r['masked_ack_events']) or bool(masked_backoff),
                 source_frozen_match=None if version=='v1' else json.loads((folder/'manifest.json').read_text())['source_sha256']==protocol['validation_source_sha256'],
                 wireless_model_validated=False,automatic_pacing_validated=False)
        results.append(r)
    record={'results':results,'exact_confirmation_match_in_all_trials':all(r['input_check_pass'] for r in results if r['tag']!='fast_clean'),
            'registered_fraction_gate_pass_in_completed_trials':all(r['registered_fraction_gate_pass'] for r in results if r['tag']!='fast_clean'),
            'completed_validation_trials':len([r for r in results if r['tag']!='fast_clean']),'planned_validation_trials':sum(len(p['trials']) for p in protocols.values()),
            'original_wireless_only_sender_model_qualified':False,'production_automatic_pacing_qualified':False,
            'scope':'ACK confirmation at Reader protocol layer vs final application sequence set offline; no custom receiver telemetry, no HTB, no capacity/beta/airtime claim'}
    (BASE/'results.json').write_text(json.dumps(record,indent=2));print(json.dumps([{k:r[k] for k in ['tag','published','received','observed','confirmed','input_check_pass','mapping_missing','backoff_updates','cap_Mbps_range']} for r in results]),flush=True)
if __name__=='__main__':main()
