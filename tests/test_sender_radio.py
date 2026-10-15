import copy
import struct
import unittest
from unittest.mock import patch
from rospacer.sender_radio import radiotap,he_rate,decode,summarize,estimate,govern,SenderMonitor,control_summary,crc_summary,fcs_counter,window_uplink,data_rate


def frame(addr3='aa:bb:cc:dd:ee:ff',amsdu=False,mcs_known=True,retry=False):
    # FLAGS, CHANNEL, AMPDU, HE with explicit alignment and known masks.
    present=(1<<1)|(1<<3)|(1<<20)|(1<<23)
    rt=struct.pack('<BBHI',0,0,32,present)+b'\0\0'+struct.pack('<HH',5745,0x140)+b'\0\0'+struct.pack('<IHBB',7,0,0,0)
    rt+=struct.pack('<6H',0x4260 if mcs_known else 0x4240,2,11<<8,0,2,2)
    # Correct length includes flags/channel padding, ampdu and HE: 36 bytes.
    rt=rt[:2]+struct.pack('<H',len(rt))+rt[4:]
    mac=lambda x:bytes.fromhex(x.replace(':',''))
    fc=0x4288|(0x800 if retry else 0)
    wlan=struct.pack('<HH',fc,0)+mac('11:22:33:44:55:66')+mac('66:55:44:33:22:11')+mac(addr3)+struct.pack('<HH',16,0x80 if amsdu else 0)
    return rt+wlan+b'\0'*64,len(rt)+1522


class SenderRadioTests(unittest.TestCase):
    def setUp(self):
        self.profile=dict(AP='66:55:44:33:22:11',frequency_MHz=5745,width_MHz=80,exclusive_receiver=True,
            body_coverage_range=[.8,1.1],downlink_Mbps_range=[1195,1205],BA_busy_s=.000063,
            relay_serialization_scale=1.,relay_exchange_busy_s=.000175,idle_busy_fraction=.005,
            O_up_s=.0000055,O_down_s=.0000055,alpha=.9,cap_ceiling_skb_Bps=40e6)
        self.old=dict(boot_id='a',AP=self.profile['AP'],frequency_MHz=5745,width_MHz=80,active_s=0,busy_s=0,tx_s=0,bytes=0,packets=0,retries=0)
        self.new={**self.old,'active_s':3,'busy_s':.5,'tx_s':1.5,'bytes':10000000,'packets':6900,'retries':50,'tx_Bps':150e6}
        self.visible=dict(counts={'own_ba':1000,'peer_ba':1000,'own_relay_mpdu':1100},relay_rate_Bps=150122549.0196,
            relay_serialization_s=.07,relay_unique_body_bytes=9500000,unknown_rate_body_bytes=0,ambiguous_amsdu_body_bytes=9500000,amsdu_frames=1100,capture_drops=0)

    def test_he_rate_is_not_ap_control_frame_rate(self):
        p,n=frame();_,f=radiotap(p)
        self.assertAlmostEqual(he_rate(f)*8/1e6,1200.980392,places=5)
        q,n=frame(mcs_known=False);_,f=radiotap(q)
        self.assertIsNone(he_rate(f))

    def test_explicit_ofdm_arp_rate_is_known_without_guessing_he(self):
        fields={2:b'\x0c',3:struct.pack('<HH',5745,0x140)}
        self.assertEqual(data_rate(fields),750000)
        _,unknown=radiotap(frame(mcs_known=False)[0])
        self.assertIsNone(data_rate({**unknown,2:b'\x0c'}))
        self.assertIsNone(data_rate({**fields,2:b'\x05'}))

    def test_encrypted_amsdu_needs_explicit_receiver_exclusivity(self):
        p,n=frame(addr3='66:55:44:33:22:11',amsdu=True)
        options=dict(ap=self.profile['AP'],source='aa:bb:cc:dd:ee:ff',receiver='11:22:33:44:55:66')
        strict=summarize([(1,p,n)],**options)
        self.assertEqual(strict['relay_wire_bytes'],0)
        self.assertGreater(strict['ambiguous_amsdu_body_bytes'],0)
        scoped=summarize([(1,p,n)],**options,exclusive_receiver=True)
        self.assertEqual(scoped['counts']['own_relay_mpdu'],1)
        self.assertEqual(scoped['relay_wire_bytes'],1522)

    def test_retries_preserve_airtime_but_not_duplicate_delivery_bytes(self):
        p,n=frame();q,_=frame(retry=True)
        a=summarize([(1,p,n),(1.01,q,n)],self.profile['AP'],'aa:bb:cc:dd:ee:ff','11:22:33:44:55:66')
        self.assertEqual(a['relay_wire_bytes'],3044)
        self.assertEqual(a['relay_body_bytes'],2*a['relay_unique_body_bytes'])
        self.assertEqual(a['shared_ampdu_refs'],1)
        self.assertNotIn('ppdu_count',a)

    def test_bad_fcs_and_truncated_headers_are_rejected(self):
        p,n=frame();p=bytearray(p);p[8]=0x40
        with self.assertRaisesRegex(ValueError,'bad FCS'):decode(p,n)
        with self.assertRaisesRegex(ValueError,'truncated'):decode(bytes(p[:12]),n)

    def test_crc_diagnostic_never_promotes_failed_frame_to_estimator(self):
        p,n=frame();p=bytearray(p);p[8]=0x40
        parsed=decode(p,n,allow_bad_fcs=True)
        strict=summarize([(1,parsed,n)],self.profile['AP'],'aa:bb:cc:dd:ee:ff','11:22:33:44:55:66')
        self.assertEqual(strict['relay_wire_bytes'],0)
        self.assertEqual(strict['errors']['bad FCS'],1)
        diag=crc_summary([(1,parsed,n)],self.profile['AP'],'11:22:33:44:55:66')
        self.assertEqual(diag['counts']['peer_bad_frames'],1)

    def test_control_exchange_requires_crc_valid_cts_time_and_nav_match(self):
        ap=self.profile['AP'];peer='11:22:33:44:55:66'
        def ctl(sub,ts,duration,ta=None,ra=ap,bad=False):
            return {'kind':1,'subtype':sub,'tsft_us':ts,'duration_us':duration,'ta':ta,'ra':ra,'frequency_MHz':5745,'bad_fcs':bad}
        # Wrap the actual driver's 32-bit receive timer.
        start=(1<<32)-30
        rts=ctl(11,start,369,ap,peer);cts=ctl(12,30,309);ba=ctl(9,540,0,peer)
        rows=[(1,rts,20),(1.00006,cts,14),(1.00057,ba,56)]
        result=control_summary(rows,ap,peer)
        self.assertEqual(result['counts']['peer_rts_cts_ba_candidates'],1)
        self.assertNotIn('airtime_s',result)
        wrong={**cts,'duration_us':200}
        result=control_summary([(1,rts,20),(2,wrong,14),(3,ba,56)],ap,peer)
        self.assertEqual(result['counts'].get('peer_rts_cts_ba_candidates',0),0)
        result=control_summary([(1,rts,20),(2,{**cts,'bad_fcs':True},14),(3,ba,56)],ap,peer)
        self.assertEqual(result['counts'].get('peer_rts_cts_ba_candidates',0),0)

    def test_cts_has_no_transmitter_address_even_with_trailing_bytes(self):
        rt=struct.pack('<BBHI',0,0,8,0)
        p=rt+struct.pack('<HH',0xc4,239)+bytes.fromhex('112233445566')+b'01234567'
        self.assertNotIn('ta',decode(p))

    def test_unavailable_fcs_counter_is_missing_not_zero(self):
        with patch('pathlib.Path.read_text',side_effect=FileNotFoundError):
            self.assertIsNone(fcs_counter('absent-test-device'))

    def test_sender_estimate_uses_no_receiver_snapshot_and_no_self_tx_subtraction(self):
        first=estimate(self.profile,self.old,self.new,self.visible)
        self.new['tx_s']=2.7
        second=estimate(self.profile,self.old,self.new,self.visible)
        self.assertEqual(first['beta'],second['beta'])
        self.assertLessEqual(first['cap_packet_Bps'],40e6)

    def test_drop_unknown_phy_invisible_relay_and_ambiguous_source_hold(self):
        for change,message in [({'capture_drops':1},'dropped'),({'unknown_rate_body_bytes':1},'unknown'),({'relay_unique_body_bytes':1000},'visibility')]:
            with self.assertRaisesRegex(ValueError,message):estimate(self.profile,self.old,self.new,{**self.visible,**change})
        with self.assertRaisesRegex(ValueError,'attribution'):estimate({**self.profile,'exclusive_receiver':False},self.old,self.new,self.visible)

    def test_unqualified_sender_cannot_install_htb(self):
        with patch('rospacer.linux.Shaper') as shaper:
            with self.assertRaisesRegex(ValueError,'held-out'):govern({'sender_radio_calibration':{'validated':False},'native_reader':'unused','cap_packet_Bps':1000},10,'unused')
            shaper.assert_not_called()

    def test_sender_identity_change_or_counter_reset_cannot_estimate(self):
        for change in [{'AP':'other'}, {'boot_id':'new-boot'}]:
            with self.assertRaisesRegex(ValueError,'identity'):
                estimate(self.profile,self.old,{**self.new,**change},self.visible)
        with self.assertRaisesRegex(ValueError,'reset'):
            estimate(self.profile,{**self.old,'bytes':20000000},self.new,self.visible)

    def test_sender_cannot_use_unobserved_ack_or_foreign_receiver_traffic(self):
        with self.assertRaisesRegex(ValueError,'BlockAck'):
            estimate(self.profile,self.old,self.new,{**self.visible,'counts':{'own_ba':1000}})
        with self.assertRaisesRegex(ValueError,'other sender'):
            estimate(self.profile,self.old,self.new,{**self.visible,'counts':{**self.visible['counts'],'unattributed_peer_mpdu':9}})

    def test_sender_channel_change_is_out_of_scope(self):
        for change in [{'frequency_MHz':5180},{'width_MHz':40}]:
            with self.assertRaisesRegex(ValueError,'channel'):
                estimate(self.profile,self.old,{**self.new,**change},self.visible)

    def test_changing_uplink_uses_byte_weighted_window_not_last_rate(self):
        samples=[dict(bytes=0,packets=0,retries=0),dict(bytes=146200,packets=100,retries=0,tx_Bps=150e6),dict(bytes=438600,packets=300,retries=0,tx_Bps=100e6)]
        self.assertAlmostEqual(window_uplink(samples),3/(1/150e6+2/100e6))
        with self.assertRaisesRegex(ValueError,'reset'):window_uplink([samples[1],{**samples[2],'bytes':1}])

    def test_untrained_uplink_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'uplink PHY'):
            estimate({**self.profile,'uplink_Mbps_range':[900,1000]},self.old,self.new,self.visible)

    def test_conservation_profile_uses_source_bytes_not_missing_relay_bytes(self):
        profile={**self.profile,'relay_estimator':'source-station-byte-conservation-v1','PHY_sample_min_frames':128,'PHY_sample_body_coverage':[.25,1.1],'peer_BA_min_count':32}
        visible={**self.visible,'relay_unique_body_bytes':4000000,'relay_serialization_s':.001}
        first=estimate(profile,self.old,self.new,visible)
        second=estimate(profile,self.old,self.new,{**visible,'relay_serialization_s':.02})
        self.assertEqual(first['beta'],second['beta'])
        with self.assertRaisesRegex(ValueError,'visibility'):estimate(profile,self.old,self.new,{**visible,'relay_unique_body_bytes':1000})
        with self.assertRaisesRegex(ValueError,'PHY samples'):estimate(profile,self.old,self.new,{**visible,'counts':{**visible['counts'],'own_relay_mpdu':1}})

    def test_monitor_cleanup_restores_power_even_when_delete_fails(self):
        monitor=SenderMonitor('wlp2s0');monitor.created=True;monitor.power_previous='on'
        with patch.object(monitor,'command',side_effect=[ValueError('delete failed'),'']) as command:
            with self.assertRaisesRegex(ValueError,'delete failed'):monitor.close()
            self.assertEqual(command.call_args_list[-1].args,('iw','dev','wlp2s0','set','power_save','on'))

    def test_bpf_preserves_full_length_before_header_only_receive(self):
        monitor=SenderMonitor('wlp2s0')
        profile={'receiver_MAC':'11:22:33:44:55:66','source_MAC':'aa:bb:cc:dd:ee:ff','AP':self.profile['AP']}
        with patch.object(monitor,'command',return_value='1\n6 0 0 65535\n') as command,patch('ctypes.CDLL') as libc:
            monitor.sock=unittest.mock.Mock();monitor.sock.fileno.return_value=9
            libc.return_value.setsockopt.return_value=0
            monitor.configure_filter(profile)
            self.assertEqual(command.call_args.args[2:4],('-s','65535'))
            self.assertIn('wlan type ctl',command.call_args.args[-1])
            self.assertIn('wlan addr1 '+self.profile['AP'],command.call_args.args[-1])

    def test_capture_flush_failure_cannot_skip_interface_and_power_cleanup(self):
        monitor=SenderMonitor('wlp2s0');monitor.created=True;monitor.power_previous='on'
        monitor.capture=unittest.mock.Mock();monitor.capture.close.side_effect=OSError('disk write')
        with patch.object(monitor,'command',return_value='') as command:
            with self.assertRaisesRegex(OSError,'disk write'):monitor.close()
            self.assertFalse(monitor.created)
            self.assertEqual(command.call_args_list[-1].args,('iw','dev','wlp2s0','set','power_save','on'))


if __name__=='__main__':unittest.main()
