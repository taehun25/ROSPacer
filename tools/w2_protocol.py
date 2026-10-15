"""Frozen three-repetition W2 matrix and DDS comparator definitions."""
import random,math,re,hashlib,xml.etree.ElementTree as E
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rospacer import profiles
from rospacer.model import synthesize

MODES=['default','vendor','static','fixed','adaptive']

class ScopeError(RuntimeError):
    """An intentionally unqualified controller scope, never an operational failure."""

def topic_name(identifier, sender=None):
    raw=str(identifier);safe=re.sub(r'[^A-Za-z0-9_]', '_', raw)
    if safe!=raw:safe+='_'+hashlib.sha256(raw.encode()).hexdigest()[:8]
    return '/w2_'+safe+('_from'+str(sender) if sender is not None else '')

def competition_schedule(condition,seconds,base_port=55944):
    phases=[(0,20,0),(20,20,.5),(40,20,.9),(60,20,0)] if condition=='F' else [(0,seconds,.9)] if condition=='C2' else [(i,2,None if i%4==0 else 0) for i in range(0,seconds,2)]
    result=[];port=base_port
    for offset,duration,factor in phases:
        result.append({'offset':offset,'duration':duration,'factor':factor,'port':port if factor!=0 else None})
        if factor!=0:port+=1
    return result
def matrix(reps=3):
    result=[];rng=random.Random(261014)
    blocks=[('T1_E','T1','E',1.5,MODES),('T1_F','T1','F',.7,MODES),('T3_E','T3','E',1.5,MODES)]
    blocks += [('P0_low_'+str(r),'T1','E',r,['default','static']) for r in [.6,1.]]
    blocks += [('P0_'+c,'T1',c,.5,['default','vendor','static']) for c in ['Clean','C2','D3','B2']]
    blocks += [('P0_D3_adaptive','T1','D3',.5,['adaptive']),('P0_C2_F4','T1','C2',.5,['static_minus_f4'])]
    # Keep all same-AP work together; the co-channel AP block is last.
    b2=[b for b in blocks if b[2]=='B2'];blocks=[b for b in blocks if b[2]!='B2']+b2
    for stage,topology,condition,rho,modes in blocks:
        for rep in range(1,reps+1):
            for rmw in ['fastdds','cyclonedds']:
                order=list(modes)+(['vendor_fc'] if stage in ['T1_E','T1_F','T3_E'] and rmw=='fastdds' else [])
                rng.shuffle(order)
                for mode in order:
                    result.append(dict(id=f'{stage}_{rmw}_{mode}_r{rep}',stage=stage,topology=topology,condition=condition,
                                       rho=rho,mode=mode,rmw=rmw,rep=rep,seconds=80 if condition=='F' else 60,
                                       warmup=10,drain=30,payload=1048576,intent='complete'))
    return result

def topology(name):
    return (['4'],['5']) if name=='T1' else (['4','5'],['12','10'])

def profile(cfg,rmw,mode,path,dev,address,peers,port=55624,peer_ports=None):
    if mode in ['static','fixed','adaptive','static_minus_f4']:
        if mode=='static_minus_f4':cfg={**cfg,'socket_tx_bytes':0,'socket_rx_bytes':212992}
        profiles.fastdds(cfg,path,address) if rmw=='fastdds' else profiles.cyclone(cfg,path,dev,peers)
        if mode=='static_minus_f4' and rmw=='cyclonedds':
            tree=E.parse(path)
            for el in tree.getroot().iter():
                if el.tag.endswith('SocketSendBufferSize'):el.set('min','212992 B');el.set('max','212992 B')
            tree.write(path,encoding='utf-8',xml_declaration=True)
        return
    if rmw=='cyclonedds':
        root=E.Element('CycloneDDS',xmlns='https://cdds.io/config');d=profiles.child(root,'Domain',Id='any');g=profiles.child(d,'General')
        profiles.child(profiles.child(g,'Interfaces'),'NetworkInterface',name=dev);profiles.child(g,'AllowMulticast','spdp')
        ps=profiles.child(profiles.child(d,'Discovery'),'Peers')
        for ip in peers:profiles.child(ps,'Peer',Address=ip)
        if mode=='vendor':
            inn=profiles.child(d,'Internal');profiles.child(inn,'SocketReceiveBufferSize',min='10 MB');profiles.child(inn,'SocketSendBufferSize',min='1 MB')
        profiles.write_xml(root,path);return
    root=E.Element('dds',xmlns='http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles');col=profiles.child(root,'profiles');tr=profiles.child(profiles.child(col,'transport_descriptors'),'transport_descriptor')
    profiles.child(tr,'transport_id','w2_transport');profiles.child(tr,'type','UDPv4' if mode=='default' else 'TCPv4')
    profiles.child(profiles.child(tr,'interfaceWhiteList'),'address',address)
    if mode!='default':
        profiles.child(tr,'sendBufferSize',1048576);profiles.child(tr,'receiveBufferSize',4194304)
        profiles.child(profiles.child(tr,'listening_ports'),'port',port)
    part=profiles.child(col,'participant',profile_name='w2_participant',is_default_profile='true');rtps=profiles.child(part,'rtps')
    profiles.child(rtps,'useBuiltinTransports','false');profiles.child(profiles.child(rtps,'userTransports'),'transport_id','w2_transport')
    if mode!='default':
        builtin=profiles.child(rtps,'builtin');initial=profiles.child(builtin,'initialPeersList')
        for ip,pp in zip(peers,peer_ports):
            tcp=profiles.child(profiles.child(initial,'locator'),'tcpv4');profiles.child(tcp,'address',ip);profiles.child(tcp,'physical_port',pp)
    if mode=='vendor_fc':
        fc=profiles.child(profiles.child(rtps,'flow_controller_descriptor_list'),'flow_controller_descriptor')
        for k,v in [('name','w2_fixed_fc'),('scheduler','FIFO'),('max_bytes_per_period',math.ceil(cfg['capacity_Bps']*.01)),('period_ms',10)]:profiles.child(fc,k,v)
        pub=profiles.child(col,'publisher',profile_name='w2_pub',is_default_profile='true');q=profiles.child(pub,'qos');pm=profiles.child(q,'publishMode')
        profiles.child(pm,'kind','ASYNCHRONOUS');profiles.child(pm,'flow_controller_name','w2_fixed_fc')
        profiles.child(pub,'historyMemoryPolicy','PREALLOCATED_WITH_REALLOC')
    # Variable-size ROS messages need the same RMW allocation policy in all
    # configurations when RMW_FASTRTPS_USE_QOS_FROM_XML is enabled.
    for role in ['publisher','subscriber']:
        endpoint=next((x for x in col if x.tag==role),None)
        if endpoint is None:endpoint=profiles.child(col,role,profile_name='w2_'+role,is_default_profile='true')
        if endpoint.find('historyMemoryPolicy') is None:profiles.child(endpoint,'historyMemoryPolicy','PREALLOCATED_WITH_REALLOC')
    profiles.write_xml(root,path)
