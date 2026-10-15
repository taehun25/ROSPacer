"""Sender-local W1 calibration, held-out validation and finite budget control.

Only calibration/validation access the receiver's existing iw/iperf3 over SSH.
The online governor has no SSH or receiver telemetry input. Operating costs are
scoped to the checked MT7921 driver, not physical airtime or intrinsic O.
"""
import copy
import csv
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import statistics
import subprocess
import sys
import time
from collections import deque

from .linux import Shaper, observe
from .minphy_radio import estimate
from .peer_phy import record
from .sender_radio import window_uplink

MODULES = ('mt76', 'mt792x_lib', 'mt7921e')
PORT = 55946


def write(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(argv, timeout=10):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{argv[0]} failed: {p.stderr.strip()}')
    return p.stdout


def identity(dev):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', dev):
        raise ValueError('invalid interface')
    info = checked(['iw', 'dev', dev, 'info'])
    channel = re.search(r'channel (\d+) \((\d+) MHz\), width: (\d+) MHz', info)
    link = checked(['iw', 'dev', dev, 'link'])
    ap = re.search(r'^Connected to ([0-9a-f:]{17})', link, re.M)
    if not channel or not ap:
        raise ValueError('associated Wi-Fi channel required')
    driver = Path(f'/sys/class/net/{dev}/device/driver').resolve().name
    if driver != 'mt7921e' or (int(channel[2]), int(channel[3])) != (5745, 80):
        raise ValueError('W1 validated scope is MT7921 on channel149/80MHz')
    return dict(AP=ap[1], frequency_MHz=int(channel[2]), width_MHz=int(channel[3]),
                kernel_modules={n: Path('/sys/module', n, 'srcversion').read_text().strip() for n in MODULES},
                dev=dev, driver=driver)


def sample(dev):
    r = observe(dev)
    ap = re.search(r'^Station ([0-9a-f:]{17})', r['station_raw'], re.M)
    if not ap:
        raise ValueError('source AP unavailable')
    r.update(AP=ap[1], boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    frequency = re.search(r'frequency:\s*(\d+)[^\n]*\[in use\]', r['survey_raw'])
    if not frequency:
        raise ValueError('associated survey frequency unavailable')
    r['frequency_MHz'] = int(frequency[1])
    for key in ('active_s', 'busy_s', 'tx_s', 'bytes', 'packets', 'retries', 'tx_Bps'):
        if key not in r:
            raise ValueError('missing source counter: '+key)
    return r


def route(dev, source, peer):
    for value in (source, peer):
        if ipaddress.ip_address(value).version != 4:
            raise ValueError('IPv4 data route required')
    r = json.loads(checked(['ip', '-j', 'route', 'get', peer, 'from', source]))
    if not r or r[0].get('dev') != dev:
        raise ValueError('data must route over the specified Wi-Fi interface')


class Peer:
    """Standard receiver tools only; strict host key and explicit identity."""
    def __init__(self, args):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9_.:%-]+', args.peer_ssh):
            raise ValueError('invalid SSH target')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', args.peer_dev):
            raise ValueError('invalid receiver interface')
        self.args = args
        self.base = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                     '-o', 'ConnectTimeout=5', '-o', 'IPQoS=none', '-o', 'IdentitiesOnly=yes',
                     '-i', str(Path(args.ssh_key).expanduser()), '-o', 'UserKnownHostsFile='+str(Path(args.known_hosts).expanduser()),
                     '-o', 'HostKeyAlias='+args.host_key_alias, args.peer_ssh]

    def argv(self, command):
        return self.base+[shlex.join(command)]

    def phy(self):
        a = self.args
        link = checked(self.argv(['iw', 'dev', a.peer_dev, 'link']))
        info = checked(self.argv(['iw', 'dev', a.peer_dev, 'info']))
        return record(link, info, a.source, a.peer, time.time())


def windows(rows, started=None, ended=None, idle=False):
    out = []
    for i, b in enumerate(rows):
        if not idle and not started+4 <= b['monotonic_s'] <= ended-2:
            continue
        earlier = [a for a in rows[:i] if b['monotonic_s']-a['monotonic_s'] >= 3]
        if earlier:
            a = earlier[-1]
            span = [r for r in rows if a['monotonic_s'] <= r['monotonic_s'] <= b['monotonic_s']]
            out.append((a, {**b, 'window_tx_Bps': window_uplink(span, 14)} if not idle else b))
    return out


def interval_rate(server):
    items = [s for interval in server.get('intervals', []) for s in interval.get('streams', [])]
    seconds = sum(s['seconds'] for s in items)
    if seconds <= 0 or sum(s['bytes'] for s in items) <= 0:
        raise ValueError('receiver has no nonzero iperf intervals')
    return sum(s['bytes'] for s in items)/seconds


def udp_counters(raw):
    lines = raw.splitlines()
    for a, b in zip(lines, lines[1:]):
        if a.startswith('Udp:') and b.startswith('Udp:'):
            return dict(zip(a.split()[1:], map(int, b.split()[1:])))
    raise ValueError('UDP counters unavailable')


def udp_trial(args, peer, folder, mbps, seconds):
    """Runs on sender, launches finite standard receiver server, keeps raw logs."""
    folder.mkdir(exist_ok=False)
    route(args.dev, args.source, args.peer)
    server = client = None
    rows, errors = [], []
    local_before = udp_counters(Path('/proc/net/snmp').read_text())
    receiver_before = udp_counters(checked(peer.argv(['cat', '/proc/net/snmp']))) if mbps else None
    if mbps:
        command = ['timeout', '-k', '2', str(seconds+30), 'iperf3', '-s', '-1',
                   '-B', args.peer, '-p', str(PORT), '-J', '-i', '.2']
        server = subprocess.Popen(peer.argv(command), stdout=open(folder/'server.json', 'w'),
                                  stderr=open(folder/'server.stderr', 'w'), start_new_session=True)
        ready = False
        for _ in range(3):
            listeners = checked(peer.argv(['ss', '-H', '-lnt']))
            if re.search(r':'+str(PORT)+r'\s', listeners):
                ready = True
                break
            if server.poll() is not None:
                break
            time.sleep(.5)
        if not ready:
            if server.poll() is None:
                os.killpg(server.pid, signal.SIGTERM); server.wait(timeout=3)
            raise RuntimeError('receiver iperf listener not ready; no measurement dispatched')
        client = subprocess.Popen(['iperf3', '-c', args.peer, '-B', args.source, '-p', str(PORT),
                                   '-u', '-b', str(int(mbps*1e6)), '-l', '1400', '-w', str(args.socket_bytes), '--connect-timeout', '5000', '-t', str(seconds), '-J'],
                                  stdout=open(folder/'client.json', 'w'), stderr=open(folder/'client.stderr', 'w'),
                                  start_new_session=True)
    start = time.monotonic()
    try:
        while time.monotonic() < start+seconds:
            tick = time.monotonic()
            try:
                rows.append(sample(args.dev))
            except (ValueError, OSError, RuntimeError) as e:
                errors.append(str(e))
            time.sleep(max(0, .2-(time.monotonic()-tick)))
        if client and client.wait(timeout=10) != 0:
            raise RuntimeError('iperf client failed; inspect preserved logs')
        if server and server.wait(timeout=10) != 0:
            raise RuntimeError('receiver server failed; inspect preserved logs')
    finally:
        for p in (client, server):
            if p and p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()
        result = dict(rows=rows, errors=errors, start_monotonic=start, end_monotonic=time.monotonic(),
                      rate_mbps=mbps, socket_bytes=args.socket_bytes, sender_host=os.uname().nodename, receiver_online_feedback=False)
        write(folder/'source.json', result)
    if errors:
        raise ValueError('source counter collection incomplete')
    if mbps:
        result['receiver_payload_Bps'] = interval_rate(json.loads((folder/'server.json').read_text()))
        receiver_after = udp_counters(checked(peer.argv(['cat', '/proc/net/snmp'])))
        result['receiver_udp_delta'] = {k: receiver_after[k]-receiver_before[k] for k in receiver_before}
        local_after = udp_counters(Path('/proc/net/snmp').read_text())
        result['sender_udp_delta'] = {k: local_after[k]-local_before[k] for k in local_before}
        write(folder/'source.json', result)
    return result


def fit_profile(trials, peer_phy, scope):
    idle_pairs = windows(trials[0]['rows'], idle=True)
    if not idle_pairs:
        raise ValueError('insufficient idle calibration')
    idle = sum(b['busy_s']-a['busy_s'] for a, b in idle_pairs)/sum(b['active_s']-a['active_s'] for a, b in idle_pairs)
    pairs = [p for t in trials[1:] for p in windows(t['rows'], t['start_monotonic'], t['end_monotonic'])]
    numerator = denominator = 0.
    for a, b in pairs:
        dt = b['active_s']-a['active_s']; n = b['packets']-a['packets']
        if dt <= 0 or n <= 0 or a['AP'] != scope['AP'] or b['AP'] != scope['AP']:
            raise ValueError('calibration counter/AP mismatch')
        retry = (b['retries']-a['retries'])/n
        base = (b['tx_s']-a['tx_s'])*b['window_tx_Bps']/peer_phy/(1+retry)
        busy = b['busy_s']-a['busy_s']-idle*dt
        numerator += base*busy; denominator += base*base
    if denominator <= 0:
        raise ValueError('self TX calibration unavailable')
    scale = numerator/denominator
    sat = trials[-1]
    ps = windows(sat['rows'], sat['start_monotonic'], sat['end_monotonic'])
    if not ps:
        raise ValueError('insufficient capacity calibration')
    a, b = ps[0][0], ps[-1][1]
    span = [r for r in sat['rows'] if a['monotonic_s'] <= r['monotonic_s'] <= b['monotonic_s']]
    up = window_uplink(span, 14); n = b['packets']-a['packets']
    frame = (b['bytes']-a['bytes'])/n; ip = frame-14; retry = (b['retries']-a['retries'])/n
    capacity = sat['receiver_payload_Bps']
    service = (1400/capacity-(1+retry)*ip/up-ip/peer_phy)/(1+retry/2)
    if not all(math.isfinite(v) and v >= 0 for v in (idle, scale, service)) or not 1400 <= frame <= 1514:
        raise ValueError('inconsistent effective calibration')
    return dict(**scope, busy_semantics='excludes_self_tx', idle_busy_fraction=idle,
                relay_model='scaled_sender_tx_duration', relay_tx_scale=scale,
                service_effective_overhead_s=service, peer_rx_phy_Bps=peer_phy,
                capacity_payload_Bps=capacity, ceiling_packet_Bps=.9*capacity*frame/1400,
                alpha=.9, validated=False, receiver_feedback_daemon=False,
                source_sha256=digest(Path(__file__).with_name('minphy_radio.py')),
                calibration_code_sha256=digest(__file__), calibrated_UTC=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                scope='MT7921/channel149/80MHz, one peer, effective operating budget; not physical beta/O')


def evaluate(profile, trial):
    ps = windows(trial['rows'], trial['start_monotonic'], trial['end_monotonic'])
    groups = {}
    for mode in ('receiver_phy_calibrated', 'downlink_equals_uplink'):
        values, residual, errors = [], [], {}
        for a, b in ps:
            candidate = {**profile, 'peer_rx_phy_Bps': b['window_tx_Bps']} if mode == 'downlink_equals_uplink' else profile
            try:
                e = estimate(candidate, a, b)
                values.append(e['raw_UDP_payload_Mbps']); residual.append(e['beta'])
            except (ValueError, KeyError) as e:
                errors[str(e)] = errors.get(str(e), 0)+1
        measured = trial['receiver_payload_Bps']*8/1e6
        predicted = statistics.median(values) if values else None
        error = abs(predicted-measured)/measured if predicted is not None else None
        fraction = len(values)/len(ps) if ps else 0
        groups[mode] = dict(eligible_windows=len(ps), valid_windows=len(values), usable_fraction=fraction,
                            predicted_Mbps=predicted, measured_Mbps=measured, relative_error=error,
                            residual_median=statistics.median(residual) if residual else None, hold_reasons=errors,
                            passed=fraction >= .95 and error is not None and error <= .2)
    groups['comparison_contract'] = 'same frozen modified model; only downlink PHY input replaced; not proof of original equations'
    groups['original_beta_decomposition_qualified'] = False
    return groups


def calibrate(args):
    scope = identity(args.dev); route(args.dev, args.source, args.peer)
    roots = json.loads(checked(['tc', '-j', 'qdisc', 'show', 'dev', args.dev]))
    if any(q.get('root') and q['kind'] != 'noqueue' for q in roots):
        raise ValueError('calibration requires noqueue and idle application traffic')
    folder = Path(args.out); folder.mkdir(parents=True, exist_ok=False)
    (folder/'calibration_code.py').write_bytes(Path(__file__).read_bytes())
    peer = Peer(args); phy = peer.phy()
    if (phy['AP'], phy['frequency_MHz'], phy['width_MHz']) != (scope['AP'], scope['frequency_MHz'], scope['width_MHz']):
        raise ValueError('receiver is not on the calibration AP/channel')
    write(folder/'peer_phy.json', phy)
    ping = checked(['ping', '-I', args.dev, '-c', '20', '-i', '.2', '-W', '2', args.peer], timeout=45)
    match = re.search(r'= [0-9.]+/([0-9.]+)/', ping)
    if not match:
        raise ValueError('RTT calibration unavailable')
    rtt = args.rtt if args.rtt is not None else float(match[1])/1000
    if not math.isfinite(rtt) or rtt <= 0 or not math.isfinite(args.hz) or args.hz <= 0:
        raise ValueError('positive finite RTT and publication rate required')
    write(folder/'rtt.json', {'ping_raw': ping, 'rtt_s': rtt, 'override': args.rtt is not None})
    trials = []
    for name, mbps, seconds in [('idle', 0, 8), ('load50', 50, args.seconds), ('load150', 150, args.seconds), ('capacity', 600, args.seconds)]:
        print('CALIBRATE '+name, flush=True)
        trials.append(udp_trial(args, peer, folder/name, mbps, seconds))
    profile = fit_profile(trials, phy['downlink_PHY_Bps'], scope)
    profile.update(source_IP=args.source, peer_IP=args.peer, calibration_socket_bytes=args.socket_bytes)
    write(folder/'profile.json', profile)
    from .model import synthesize
    from . import profiles
    cfg = synthesize(1048576, args.hz, 1, profile['capacity_payload_Bps'], rtt, 1)
    cfg.update(dev=args.dev, peers=[args.peer], cap_packet_Bps=profile['ceiling_packet_Bps'],
               middleware=args.rmw, receiver_feedback_required=False, downlink_rate_source='receiver_offline_calibration')
    write(folder/'governor.json', cfg)
    profiles.fastdds(cfg, folder/'middleware.xml', args.source) if args.rmw == 'fastdds' else profiles.cyclone(cfg, folder/'middleware.xml', args.dev, args.peer)
    bundle_application_files(folder, cfg, args.rmw, args.socket_bytes)
    write(folder/'manifest.json', dict(sender_host=os.uname().nodename, calculation_host=os.uname().nodename,
                                      peer_access='standard iw/finite iperf3 over Wi-Fi SSH only during calibration',
                                      profile_sha256=digest(folder/'profile.json'), production_approved=False))
    print(json.dumps({'bundle': str(folder), 'capacity_Mbps': profile['capacity_payload_Bps']*8/1e6}), flush=True)


def bundle_application_files(folder, cfg, rmw, calibration_socket_bytes):
    """Application setup artifacts; does not apply global kernel settings."""
    folder = Path(folder)
    env = 'ROSPACER_PROFILE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"\n'
    if rmw == 'fastdds':
        env += 'export RMW_IMPLEMENTATION=rmw_fastrtps_cpp RMW_FASTRTPS_USE_QOS_FROM_XML=1\nexport FASTRTPS_DEFAULT_PROFILES_FILE="$ROSPACER_PROFILE_DIR/middleware.xml"\n'
    else:
        env += 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp\nexport CYCLONEDDS_URI="file://$ROSPACER_PROFILE_DIR/middleware.xml"\n'
    (folder/'env.bash').write_text(env)
    maxima = {'net.core.wmem_max': max(cfg['socket_tx_bytes'], calibration_socket_bytes),
              'net.core.rmem_max': max(cfg['socket_rx_bytes'], calibration_socket_bytes)}
    (folder/'sysctl.conf').write_text(''.join(f'{k}={v}\n' for k,v in maxima.items()))


def validate(args):
    bundle = Path(args.bundle); profile = json.loads((bundle/'profile.json').read_text())
    check_scope(profile, args.dev)
    if (args.source, args.peer) != (profile['source_IP'], profile['peer_IP']):
        raise ValueError('calibration endpoint mismatch')
    if args.socket_bytes != profile['calibration_socket_bytes']:
        raise ValueError('validation socket setting differs from calibration')
    folder = Path(args.out); folder.mkdir(parents=True, exist_ok=False)
    trial = udp_trial(args, Peer(args), folder/'measurement', 600, args.seconds)
    result = evaluate(profile, trial)
    result.update(condition=args.condition, profile_sha256=digest(bundle/'profile.json'),
                  sender_host=os.uname().nodename, refit_after_validation=False,
                  validation_code_sha256=digest(__file__))
    (folder/'validation_code.py').write_bytes(Path(__file__).read_bytes())
    write(folder/'validation.json', result)
    print(json.dumps(result), flush=True)


def check_scope(profile, dev):
    now = identity(dev)
    for key in ('AP', 'frequency_MHz', 'width_MHz', 'driver', 'dev', 'kernel_modules'):
        if now[key] != profile[key]:
            raise ValueError('recalibration required: '+key+' changed')
    if profile['source_sha256'] != digest(Path(__file__).with_name('minphy_radio.py')):
        raise ValueError('budget estimator changed')


def require_qualification(profile_path, validation_paths):
    if not validation_paths:
        raise ValueError('independent validation required')
    records = [json.loads(Path(p).read_text()) for p in validation_paths]
    if any(r['profile_sha256'] != digest(profile_path) for r in records):
        raise ValueError('validation does not match frozen profile')
    for r in records:
        c = r['receiver_phy_calibrated']
        predicted, measured = c['predicted_Mbps'], c['measured_Mbps']
        if predicted is None or not all(math.isfinite(x) and x > 0 for x in (predicted, measured)):
            raise ValueError('invalid independent capacity evidence')
        if c['eligible_windows'] <= 0 or not 0 <= c['valid_windows'] <= c['eligible_windows']:
            raise ValueError('invalid independent window counts')
        error = abs(predicted-measured)/measured
        fraction = c['valid_windows']/c['eligible_windows']
        if abs(error-c['relative_error']) > 1e-9 or abs(fraction-c['usable_fraction']) > 1e-9:
            raise ValueError('inconsistent independent validation summary')
        if error > .2 or fraction < .95:
            raise ValueError('independent budget evidence failed')
    if not any(r['condition'] == 'Clean' and r['receiver_phy_calibrated']['passed'] for r in records):
        raise ValueError('independent Clean budget validation must pass')
    if any(not r['receiver_phy_calibrated']['passed'] for r in records):
        raise ValueError('requested budget validation failed')
    return sorted({r['condition'] for r in records})


def step(profile, samples, boot, now):
    if samples[-1]['boot_id'] != boot or samples[-1]['AP'] != profile['AP']:
        raise ValueError('source identity/AP changed; recalibration required')
    if samples[-1].get('frequency_MHz', profile.get('frequency_MHz')) != profile.get('frequency_MHz'):
        raise ValueError('source channel changed; recalibration required')
    if now-samples[0]['monotonic_s'] < 2:
        raise ValueError('source observation warming up')
    if now-samples[-1]['monotonic_s'] > 1:
        raise ValueError('stale source observation')
    if any(b['monotonic_s']-a['monotonic_s'] > 1 for a, b in zip(samples, list(samples)[1:])):
        raise ValueError('source observation gap; hold until a continuous window is available')
    current = {**samples[-1], 'window_tx_Bps': window_uplink(list(samples), 14)}
    return estimate(profile, samples[0], current)


def govern(args):
    bundle = Path(args.bundle); cfg = json.loads((bundle/'governor.json').read_text())
    profile = json.loads((bundle/'profile.json').read_text()); dev = cfg['dev']
    check_scope(profile, dev); conditions = require_qualification(bundle/'profile.json', args.validation)
    route(dev, profile['source_IP'], profile['peer_IP'])
    if 'receiver_feedback' in cfg:
        raise ValueError('receiver feedback prohibited')
    folder = Path(args.out); folder.mkdir(parents=True, exist_ok=False)
    shaper = Shaper(cfg); samples = deque(); updates = changes = 0; errors = {}; error = None
    cap = min(cfg['cap_packet_Bps'], profile['ceiling_packet_Bps']); cfg['cap_packet_Bps'] = cap
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    old_signal = signal.getsignal(signal.SIGTERM)
    def stop(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try:
        shaper.install()
        token = Path('/proc/self/stat').read_text().split()[21]
        helper = subprocess.Popen([sys.executable, '-m', 'rospacer.sender_ack_live', '--out', str(folder),
                                   '--seconds', str(args.seconds+5), '--guard-pid', str(os.getpid()),
                                   '--guard-start-token', token, '--guard-dev', dev],
                                  stdin=subprocess.DEVNULL, stdout=open(folder/'guard.log', 'w'),
                                  stderr=subprocess.STDOUT, start_new_session=True)
        write(folder/'guard.json', {'pid': helper.pid})
        end = time.monotonic()+args.seconds
        with (folder/'trace.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['monotonic_s', 'status', 'cap_packet_Bps', 'residual', 'theta', 'error', 'class_json', 'qdisc_json'])
            writer.writeheader()
            while time.monotonic() < end:
                tick = time.monotonic(); row = dict(monotonic_s=tick, status='fixed' if args.mode == 'fixed' else 'hold', cap_packet_Bps=cap, error='')
                if args.mode == 'adaptive':
                    try:
                        samples.append(sample(dev))
                        while len(samples) > 2 and samples[1]['monotonic_s'] < tick-3:
                            samples.popleft()
                        e = step(profile, samples, boot, time.monotonic())
                        target = min(cfg['cap_packet_Bps'], max(1000, .7*cap+.3*e['cap_packet_Bps']))
                        if abs(target-cap) > .5:
                            shaper.change(target); changes += 1
                        cap = target; updates += 1
                        row.update(status='updated', cap_packet_Bps=cap, residual=e['beta'], theta=e['theta'])
                    except (ValueError, KeyError) as e:
                        row['error'] = str(e); errors[str(e)] = errors.get(str(e), 0)+1
                        # Never bridge resets/AP changes with an older observation window.
                        if 'reset' in str(e) or 'identity' in str(e) or 'AP' in str(e):
                            samples.clear()
                row.update(class_json=shaper.class_stats(), qdisc_json=shaper.stats())
                writer.writerow(row); f.flush(); time.sleep(max(0, .2-(time.monotonic()-tick)))
    except BaseException as e:
        error = type(e).__name__+': '+str(e)
    finally:
        shaper.close(); (folder/'shaper.end').write_text('end'); signal.signal(signal.SIGTERM, old_signal)
        roots = json.loads(checked(['tc', '-j', 'qdisc', 'show', 'dev', dev]))
        result = dict(sender_host=os.uname().nodename, updates=updates, HTB_changes=changes,
                      hold_reasons=errors, error=error, restored=all(q['kind'] == 'noqueue' for q in roots),
                      receiver_access_during_govern=False, qualified_budget_conditions=conditions,
                      original_beta_decomposition_qualified=False, formal_performance_approved=False,
                      profile_sha256=digest(bundle/'profile.json'), mode=args.mode, controller_code_sha256=digest(__file__))
        (folder/'controller_code.py').write_bytes(Path(__file__).read_bytes())
        write(folder/'summary.json', result); print(json.dumps(result), flush=True)
    if error and not error.startswith('KeyboardInterrupt'):
        raise RuntimeError(error)


def add_commands(sub):
    for name in ('sender-calibrate', 'sender-validate'):
        p = sub.add_parser(name, help='sender-local standard-tool offline calibration/validation')
        for field in ('dev', 'source', 'peer', 'peer-ssh', 'ssh-key', 'known-hosts', 'host-key-alias', 'out'):
            p.add_argument('--'+field, required=True)
        p.add_argument('--peer-dev', default='wlp2s0')
        p.add_argument('--seconds', type=int, choices=range(10, 31), default=15)
        p.add_argument('--socket-bytes', type=int, choices=(131072, 1048576), default=131072,
                       help='UDP socket request; requires adequate preconfigured sender/receiver kernel maxima')
        if name == 'sender-calibrate':
            p.add_argument('--rmw', choices=('fastdds', 'cyclonedds'), default='fastdds')
            p.add_argument('--hz', type=float, default=30)
            p.add_argument('--rtt', type=float, help='optional RTT seconds override; default is local Wi-Fi ping measurement')
        else:
            p.add_argument('--bundle', required=True)
            p.add_argument('--condition', choices=('Clean', 'B2', 'C2'), required=True)
    p = sub.add_parser('sender-govern', help='finite W1 sender-only online budget control; no receiver SSH')
    p.add_argument('--bundle', required=True); p.add_argument('--validation', action='append', required=True)
    p.add_argument('--out', required=True); p.add_argument('--seconds', type=int, choices=range(1, 181), default=60)
    p.add_argument('--mode', choices=('adaptive', 'fixed'), default='adaptive')


def dispatch(args):
    {'sender-calibrate': calibrate, 'sender-validate': validate, 'sender-govern': govern}[args.command](args)
