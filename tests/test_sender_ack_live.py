import unittest
from rospacer.sender_ack_live import validate,Actuator

class FakeShaper:
    def __init__(self):self.rates=[]
    def change(self,v):self.rates.append(v)
    def class_stats(self):return '[]'
    def stats(self):return '[]'

class LiveBounds(unittest.TestCase):
    def cfg(self):return dict(experimental_ack_trial=True,payload_bytes=1048576,peers=['192.168.0.5'],dev='wlp2s0',ack_ceiling_packet_Bps=100,cap_packet_Bps=100)
    def test_explicit_scope_and_no_custom_receiver(self):
        c=self.cfg();self.assertEqual(validate(c,'192.168.0.4','192.168.0.5',60),100)
        for change in [dict(experimental_ack_trial=False),dict(receiver_feedback={}),dict(cap_packet_Bps=101),dict(peers=['x','y'])]:
            with self.assertRaises(ValueError):validate({**c,**change},'192.168.0.4','192.168.0.5',60)
    def test_invalid_recommendation_cannot_mutate(self):
        s=FakeShaper();a=Actuator(s,'ack',100)
        for value in [0,9,101,float('nan')]:
            with self.assertRaises(ValueError):a(value,'backoff','test')
        self.assertFalse(s.rates)
    def test_fixed_never_follows_ack_decrease(self):
        s=FakeShaper();a=Actuator(s,'fixed',100);r=a(80,'backoff','test');self.assertEqual(r['applied_packet_Bps'],100);self.assertFalse(s.rates)
    def test_hold_retains_last_applied_rate(self):
        s=FakeShaper();a=Actuator(s,'ack',100);a(80,'backoff','test');a(100,'hold','invalid input');self.assertEqual(s.rates,[80]);a(81.6,'recover','test');self.assertEqual(s.rates,[80,81.6])
