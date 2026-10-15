"""Offline receiver PHY correction: a calibration file, never a RX daemon."""
import copy,math,re

def record(link,info,source_IP,peer_IP,observed_wall_s):
    ap=re.search(r'^Connected to ([0-9a-f:]{17})',link,re.M)
    phy=re.search(r'rx bitrate:\s*([0-9.]+) MBit/s',link)
    channel=re.search(r'channel (\d+) \((\d+) MHz\), width: (\d+) MHz',info)
    if not ap or not phy or not channel:raise ValueError('missing associated receiver PHY/channel calibration')
    rate=float(phy[1])*125000
    if not math.isfinite(rate) or rate<=0:raise ValueError('invalid receiver PHY')
    return {'source_IP':source_IP,'peer_IP':peer_IP,'AP':ap[1],'frequency_MHz':int(channel[2]),'width_MHz':int(channel[3]),'downlink_PHY_Bps':rate,'receiver_observed_wall_s':observed_wall_s,'input_contract':'offline receiver PHY calibration','receiver_feedback_daemon':False,'validated':False}

def attach(cfg,calibration):
    rate=calibration.get('downlink_PHY_Bps')
    if not isinstance(rate,(int,float)) or not math.isfinite(rate) or rate<=0:raise ValueError('positive receiver PHY calibration required')
    if cfg.get('peers')!=[calibration.get('peer_IP')]:raise ValueError('receiver PHY calibration peer mismatch')
    if not calibration.get('AP') or calibration.get('receiver_feedback_daemon') is not False:raise ValueError('offline associated receiver calibration required')
    if 'receiver_feedback' in cfg:raise ValueError('minimal correction must not depend on receiver feedback daemon')
    result=copy.deepcopy(cfg);result['peer_phy_calibration']=copy.deepcopy(calibration)
    result.pop('experimental_ack_trial',None);result.pop('ack_ceiling_packet_Bps',None)
    result['downlink_rate_source']='receiver_offline_calibration'
    result['receiver_feedback_required']=False
    # This corrects a PHY input. It cannot validate counter semantics or O.
    result['survey_semantics_validated']=False
    return result

def rate(cfg):
    cal=cfg.get('peer_phy_calibration')
    if cal is None:return None
    value=cal.get('downlink_PHY_Bps')
    if not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:raise ValueError('invalid offline receiver PHY calibration')
    if cfg.get('peers')!=[cal.get('peer_IP')]:raise ValueError('offline receiver PHY peer mismatch')
    return value
