import unittest
from rospacer.minphy_radio import estimate
class MinimalPHYModel(unittest.TestCase):
    def data(self):
        a=dict(boot_id='x',AP='a',active_s=0,busy_s=0,tx_s=0,packets=0,bytes=0,retries=0);b={**a,'active_s':3,'busy_s':.12,'tx_s':.3,'packets':1000,'bytes':1442000,'tx_Bps':100e6};p=dict(AP='a',busy_semantics='excludes_self_tx',peer_rx_phy_Bps=150e6,idle_busy_fraction=.01,relay_effective_overhead_s=2e-6,service_effective_overhead_s=5e-6,alpha=.9,ceiling_packet_Bps=40e6);return p,a,b
    def test_counter_inclusion_is_explicit(self):
        p,a,b=self.data();r=estimate(p,a,b);self.assertGreater(r['raw_packet_Bps'],0);self.assertLessEqual(r['cap_packet_Bps'],p['ceiling_packet_Bps'])
        with self.assertRaises(ValueError):estimate({**p,'busy_semantics':'unknown'},a,b)
    def test_missing_geometry_reset_and_AP_never_invented(self):
        p,a,b=self.data()
        for changes in [{'AP':'wrong'},{'bytes':-1},{'tx_Bps':0},{'busy_s':4}]:
            with self.assertRaises(ValueError):estimate(p,a,{**b,**changes})
