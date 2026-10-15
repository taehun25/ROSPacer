"""Phase metrics for the four predeclared windows of dynamic competition F."""
from rospacer.metrics import percentile

def f_windows(pub, sub, start_wall_ns, seconds_per_phase=20, clock_validated=False):
    unique={}
    for x in sub['records']:
        if 'seq' in x and x['seq'] not in unique:unique[x['seq']]=x
    out=[]
    for phase,factor in enumerate([0,.5,.9,0]):
        lo=start_wall_ns+int(phase*seconds_per_phase*1e9);hi=lo+int(seconds_per_phase*1e9)
        sent=[x for x in pub['records'] if lo-start_wall_ns<=x['publish_start_ns']-pub['measurement_started_ns']<hi-start_wall_ns]
        originated=[x for x in unique.values() if lo<=x['publisher_wall_ns']<hi]
        arrived=[x for x in unique.values() if lo<=x['arrival_wall_ns']<hi]
        latency=[(x['arrival_wall_ns']-x['publisher_wall_ns'])/1e6 for x in originated] if clock_validated else []
        out.append({'phase':phase,'competition_factor':factor,'seconds':seconds_per_phase,
                    'publish_attempts':len(sent),'publish_succeeded':sum(x.get('publish_succeeded',False) for x in sent),
                    'received_messages_originating_in_phase':len(originated),
                    'p99_latency_of_messages_originating_in_phase_ms':percentile(latency,.99) if latency else None,
                    'arrival_window_goodput_Mbps':len(arrived)*pub['payload_bytes']*8/seconds_per_phase/1e6 if clock_validated else None,
                    'definition':'latency groups by embedded publication time, even if received later; goodput groups by arrival time; clock-qualified only'})
    return out
