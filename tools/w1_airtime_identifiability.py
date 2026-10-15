"""Audit actual radiotap information rather than inventing missing HE timing."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys
from deploy import ROOT
sys.path.insert(0,str(ROOT))
from rospacer.sender_radio import decode,radiotap,pcap_frames

def main():
    paths=[ROOT/'runs/w1_20261013_sender_gap'/n/'4/air.pcap' for n in ['clean_fcs_retry','b2_fcs_1','control_clean','control_b2']]
    paths+=[ROOT/'runs/w1_20261013_w1_closeout/sender_b2_post_ssh'/h/'air.pcap' for h in ['4','5']]
    rows=[]
    for path in paths:
        counts=Counter();ltfs=Counter();refs=Counter()
        for stamp,packet,wire in pcap_frames(path):
            try:r=decode(packet,wire);offset,f=radiotap(packet)
            except ValueError:continue
            if not(r['kind']==2 and r['subtype'] in (0,8) and r.get('ta')=='b0:38:6c:7d:f5:74' and r['ra']=='3c:0a:f3:02:e4:c7'):continue
            counts['crc_valid_peer_data']+=1
            if 23 in f:
                a,b,c,d,e,g=struct.unpack('<6H',f[23]);counts['HE_metadata']+=1
                counts['GI_known']+=bool(b&0x2)
                counts['LTF_symbol_count_known']+=bool(b&0x4)
                counts['pre_FEC_padding_known']+=bool(b&0x8)
                counts['PE_disambiguity_known']+=bool(b&0x20)
                counts['Doppler_known']+=bool(a&0x8000)
                ltfs[str((e>>6)&3)]+=1
            if 20 in f:
                ref,flags,crc,reserved=struct.unpack('<IHBB',f[20]);refs[ref]+=1
                counts['AMPDU_last_known']+=bool(flags&0x4)
        rows.append({'pcap':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'counts':dict(counts),'raw_LTF_size_encoding':dict(ltfs),'AMPDU_reference_count':len(refs),'references_shared_by_multiple_observed_MPDUs':sum(n>1 for n in refs.values())})
    result={'captures':rows,'physical_airtime_identified':False,'intrinsic_O_identified':False,
            'reason':'HE-LTF symbol count and pre-FEC padding are not marked known; LTF size has raw encoding1 but does not supply the missing symbol count. PPDU boundaries and complete capture are not qualified. PHY serialization and fitted operational costs do not independently identify physical airtime.',
            'O_identifiability':'A single C0 fit identifies one weighted up/down effective service cost; splitting Oup/Odown or removing aggregation/ACK/retry effects requires independent observations or added assumptions.',
            'W1_relation':'Proposal e-calib requires fitting O to C0 and comparing HE preamble/ACK costs, not proof of universal full-PPDU physical airtime. The fitted operational cost exists; independent physical comparison remains qualified as unavailable.',
            'definition_source':'installed Linux ieee80211_radiotap.h, fields HE data2 and data5; see current_restoration_audit.json'}
    out=ROOT/'runs/w1_20261013_w1_closeout/airtime_identifiability.json';out.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({'rows':rows,'physical_airtime_identified':False}))

if __name__=='__main__':main()
