import unittest
from rospacer.peer_phy import record,attach,rate
from rospacer.model import adaptive_rate

class OfflinePeerPHY(unittest.TestCase):
    def cal(self):return record('Connected to b0:38:6c:7d:f5:74 (on wlp2s0)\n rx bitrate: 1200.9 MBit/s','channel 149 (5745 MHz), width: 80 MHz','192.168.0.4','192.168.0.5',1)
    def test_units_and_no_scope_promotion(self):
        c=attach({'peers':['192.168.0.5'],'survey_semantics_validated':True},self.cal());self.assertEqual(rate(c),1200.9*125000);self.assertFalse(c['survey_semantics_validated']);self.assertFalse(c['receiver_feedback_required'])
    def test_missing_or_wrong_receiver_rejected(self):
        with self.assertRaises(ValueError):record('Not connected.','', 'a','b',1)
        with self.assertRaises(ValueError):attach({'peers':['x']},self.cal())
        for value in [0,float('nan'),-1]:
            with self.assertRaises(ValueError):attach({'peers':['192.168.0.5']},{**self.cal(),'downlink_PHY_Bps':value})
    def test_model_uses_frozen_peer_not_sender_rx_rate(self):
        cfg=attach({'peers':['192.168.0.5'],'unit_bytes':1472,'header_bytes':64,'airtime_overhead_s':.000003,'alpha':.9,'packet_factor':1.05},self.cal());d={'elapsed_s':1,'busy_s':.2,'tx_s':.1,'tx_Bps':100e6,'rx_Bps':1e6,'retries':0,'packets':100,'bytes':140800}
        a=adaptive_rate(cfg,d,True);b=adaptive_rate(cfg,{**d,'rx_Bps':100e6},True);self.assertEqual(a,b)
        with self.assertRaisesRegex(ValueError,'survey'):adaptive_rate(cfg,{**d,'tx_s':.3},True)
