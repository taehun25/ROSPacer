import struct,unittest
from rospacer.sender_protocol import rtps_events,DeliveryState,recommend

PREFIX=bytes(range(12));READER_PREFIX=bytes(range(12,24));WRITER=b'\0\0\x10\x03';READER=b'\0\0\x10\x04'
def sub(kind,body,endian='<'):
    return bytes([kind,1 if endian=='<' else 0])+struct.pack(endian+'H',len(body))+body
def header(prefix):return b'RTPS\x02\x03\x01\x10'+prefix
def data(sn=1):
    b=struct.pack('<HH',0,28)+READER+WRITER+struct.pack('<iIIHHI',0,sn,1,1,1388,1048588)
    return header(PREFIX)+sub(0x16,b)
def ack(base=2,bits=0,mask=(),count=1,endian='<',destination=PREFIX):
    b=READER+WRITER+struct.pack(endian+'iII',0,base,bits)+struct.pack(endian+str(len(mask))+'I',*mask)+struct.pack(endian+'I',count)
    return header(READER_PREFIX)+sub(0x0e,destination,endian)+sub(0x06,b,endian)
class ProtocolEvidence(unittest.TestCase):
    def state(self):
        s=DeliveryState('a','b',1048576);s.consume('a','b',rtps_events(data())[0],1);return s
    def test_full_guid_and_both_endian_ack(self):
        for endian in ['<','>']:
            s=self.state();s.consume('b','a',rtps_events(ack(endian=endian))[-1],1.1)
            self.assertEqual(list(s.acks),[1]);self.assertAlmostEqual(s.snapshot(1.2)['recent_ack_lag_s_max'],.1)
    def test_missing_bitmap_not_delivery_ack(self):
        s=self.state();e=rtps_events(ack(base=1,bits=2,mask=(0x80000000,)))[-1];self.assertEqual(e['missing'],[1]);s.consume('b','a',e,1.1);self.assertFalse(s.acks)
    def test_wrong_writer_prefix_never_confirms(self):
        s=self.state();s.consume('b','a',rtps_events(ack(destination=b'x'*12))[-1],1.1);self.assertFalse(s.acks)
    def test_truncated_bitmap_and_excess_bits_rejected(self):
        for packet in [ack(bits=33,mask=(0,)),ack(bits=257,mask=(0,)*9)]:
            with self.assertRaises(ValueError):rtps_events(packet)
    def test_first_fragment_must_be_observed(self):
        s=self.state();s.samples[1]['first_fragment_seen']=False;s.consume('b','a',rtps_events(ack())[-1],1.1);self.assertFalse(s.acks)
    def test_gap_invalidates_cumulative_completion(self):
        s=self.state();gap=header(PREFIX)+sub(0x0e,READER_PREFIX)+sub(0x08,READER+WRITER+struct.pack('<iIiII',0,1,0,2,0))
        s.consume('a','b',rtps_events(gap)[-1],1.05);s.consume('b','a',rtps_events(ack())[-1],1.1);self.assertFalse(s.acks);self.assertIn('GAP',s.scope_error)
    def test_preemptive_ack_and_duplicate_cannot_invent_progress(self):
        s=self.state();s.consume('b','a',rtps_events(ack(base=0))[-1],1.1);self.assertIsNone(s.last_ack)
        e=rtps_events(ack(count=2))[-1];s.consume('b','a',e,1.2);s.consume('b','a',e,2);self.assertEqual(len(s.acks),1);self.assertEqual(s.last_ack,1.2)
    def test_ack_beyond_local_capture_holds(self):
        s=self.state();s.consume('b','a',rtps_events(ack(base=9))[-1],1.1);self.assertFalse(s.acks);self.assertIsNotNone(s.scope_error)
    def test_stale_feedback_backs_off_and_respects_floor(self):
        s=self.state();s.consume('a','b',rtps_events(data(sn=2))[0],1.05)
        e=rtps_events(ack(base=1))[-1];s.consume('b','a',e,1.1)
        cap,status,why=recommend(s.snapshot(2),100,100,10);self.assertEqual(cap,80);self.assertEqual(status,'backoff')
        cap,status,why=recommend(s.snapshot(2),10,100,10);self.assertEqual(cap,10)
    def test_security_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError,'security'):rtps_events(header(PREFIX)+sub(0x31,b'\0'*8))
    def test_gap_without_info_dst_still_invalidates(self):
        s=self.state();packet=header(PREFIX)+sub(0x08,READER+WRITER+struct.pack('<iIiII',0,1,0,2,0))
        s.consume('a','b',rtps_events(packet)[-1],1.1);self.assertIn('GAP',s.scope_error)
    def test_invalidated_timestamp_zero_length_does_not_hide_data(self):
        packet=header(PREFIX)+b'\x09\x03\0\0'+data()[20:]
        self.assertEqual(rtps_events(packet)[0]['kind'],'data')
    def test_unconfirmed_last_sample_is_not_inferred_as_congestion(self):
        s=self.state();s.consume('b','a',rtps_events(ack(base=1))[-1],1.1)
        state=s.snapshot(2);self.assertTrue(state['unconfirmed_tail'])
        cap,status,why=recommend(state,100,100,10);self.assertEqual((cap,status),(100,'hold'));self.assertFalse(s.acks)
    def test_tail_with_recent_fragment_repair_still_backs_off(self):
        s=self.state();s.consume('b','a',rtps_events(ack(base=1))[-1],1.1);s.last_nack=1.9
        cap,status,why=recommend(s.snapshot(2),100,100,10);self.assertEqual((cap,status),(80,'backoff'))
    def test_coalesced_outgoing_data_control_needs_full_capture(self):
        gap=READER+WRITER+struct.pack('<iIiII',0,1,0,2,0)
        packet=header(PREFIX)+sub(0x16,data()[24:]+bytes(243))+sub(0x08,gap)
        with self.assertRaisesRegex(ValueError,'truncated control header'):rtps_events(packet[:320],len(packet))
        self.assertEqual([e['kind'] for e in rtps_events(packet)],['data','gap'])
