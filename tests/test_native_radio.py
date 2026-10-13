import copy
import unittest
from unittest.mock import patch
from rospacer.native_radio import estimate,count_delta


class NativeRadioInputTests(unittest.TestCase):
    def setUp(self):
        self.profile=dict(AP='aa:bb:cc:dd:ee:ff',frequency_MHz=5745,width_MHz=80,station_link_header_bytes=14,AMPDU_byte_coverage_scale=1.05,
                          BA_busy_s=.000032,RX_data_scale=1.05,RX_AMPDU_busy_s=.000146,idle_busy_fraction=.01,O_up_s=.00000346,O_down_s=.00000128,alpha=.9,cap_ceiling_skb_Bps=40e6)
        self.old=dict(active_s=0,busy_s=0,tx_s=0,bytes=0,packets=0,retries=0,tx_Bps=100e6,rx_Bps=150e6,boot_id='a',AP=self.profile['AP'],frequency_MHz=5745,width_MHz=80,
                      native={k:0 for k in ['rx_bytes','rx_packets','rx_mpdu_cnt','rx_ampdu_cnt','rx_ampdu_bytes_cnt','rx_ba_cnt']})
        self.sender=copy.deepcopy(self.old);self.sender.update(active_s=3,busy_s=.5,tx_s=1.5,bytes=432600,packets=300);self.sender['native']['rx_ba_cnt']=10
        self.receiver=copy.deepcopy(self.old);self.receiver.update(active_s=3);self.receiver['native'].update(rx_bytes=432600,rx_packets=300,rx_mpdu_cnt=50,rx_ampdu_cnt=10,rx_ampdu_bytes_cnt=430000)

    def test_own_tx_not_subtracted_from_rx_cca(self):
        a=estimate(self.profile,self.old,self.sender,self.old,self.receiver)
        self.sender['tx_s']=2.5
        b=estimate(self.profile,self.old,self.sender,self.old,self.receiver)
        self.assertEqual(a['beta'],b['beta']);self.assertGreater(a['beta'],0)

    def test_negative_residual_retained_and_ceiling_enforced(self):
        self.sender['busy_s']=.02
        result=estimate(self.profile,self.old,self.sender,self.old,self.receiver)
        self.assertLess(result['beta'],0);self.assertLessEqual(result['cap_packet_Bps'],40e6)

    def test_missing_or_stale_input_is_rejected(self):
        self.receiver['active_s']=0
        with self.assertRaisesRegex(ValueError,'stale'):estimate(self.profile,self.old,self.sender,self.old,self.receiver)

    def test_changed_identity_or_channel_is_rejected(self):
        self.receiver['AP']='other'
        with self.assertRaisesRegex(ValueError,'identity'):estimate(self.profile,self.old,self.sender,self.old,self.receiver)
        self.receiver['AP']=self.old['AP'];self.receiver['width_MHz']=40
        with self.assertRaisesRegex(ValueError,'channel'):estimate(self.profile,self.old,self.sender,self.old,self.receiver)

    def test_only_documented_u32_counters_wrap(self):
        self.assertEqual(count_delta({'rx_ba_cnt':2**32-2},{'rx_ba_cnt':3},'rx_ba_cnt'),5)
        with self.assertRaisesRegex(ValueError,'reset'):count_delta({'bytes':100},{'bytes':10},'bytes')

    def test_unvalidated_profile_cannot_install_a_shaper(self):
        from rospacer.native_radio import govern
        cfg={'native_radio_calibration':{'validated':False},'native_reader':'unused','receiver_feedback':{}}
        with patch('rospacer.linux.Shaper') as shaper:
            with self.assertRaisesRegex(ValueError,'validation gate'):govern(cfg,1,'unused.csv')
            shaper.assert_not_called()


if __name__=='__main__':unittest.main()
