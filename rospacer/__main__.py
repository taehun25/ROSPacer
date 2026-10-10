import argparse
import ipaddress
import json
from pathlib import Path
import re
import sys
import time

from . import __version__
from .model import quantity, synthesize, identify_overhead
from . import profiles


def json_write(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="ROSPacer prototype: static profiles and sender HTB/fq")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--rmw", choices=("fastdds", "cyclonedds"), required=True)
    for arg, default in (("payload", "1MiB"), ("share", None), ("rtt", "4ms"),
                         ("tau", "1s"), ("out", None), ("dev", None),
                         ("address", None)):
        plan.add_argument("--"+arg, default=default, required=default is None)
    plan.add_argument("--peer", action="append", required=True, help="repeat for each unicast reader")
    plan.add_argument("--rate", type=float, default=10)
    plan.add_argument("--readers", type=int, default=1)
    plan.add_argument("--alpha", type=float, default=.9)
    plan.add_argument("--header", type=int, default=64, help="provisional RTPS overhead, bytes")
    plan.add_argument("--intent", choices=("complete", "latest"), default="complete")
    for name in ("doctor", "probe"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--dev", required=True)
        cmd.add_argument("--out", required=True)
        if name == "probe":
            cmd.add_argument("--seconds", type=float, default=3)
    validate = sub.add_parser("validate")
    validate.add_argument("--xml", required=True)
    validate.add_argument("--schema", required=True)
    gov = sub.add_parser("govern")
    gov.add_argument("--config", required=True)
    gov.add_argument("--mode", choices=("fixed", "adaptive"), default="fixed")
    gov.add_argument("--seconds", type=float, default=10)
    gov.add_argument("--trace", default="govern.csv")
    gov.add_argument("--dry-run", action="store_true")
    cal = sub.add_parser("calibrate")
    cal.add_argument("--config", required=True)
    cal.add_argument("--tx-rate", required=True)
    cal.add_argument("--rx-rate", required=True)
    cal.add_argument("--retries", type=float, required=True)
    cal.add_argument("--relay-in-survey", choices=("yes", "no"), required=True)
    restore_cmd = sub.add_parser("restore")
    restore_cmd.add_argument("--dev", required=True)
    args = parser.parse_args()
    if args.command == "plan":
        for address in (args.address, *args.peer):
            if ipaddress.ip_address(address).version != 4:
                raise ValueError("IPv4 required in prototype")
        if args.readers != len(set(args.peer)):
            raise ValueError("--readers must equal unique --peer addresses for this single-topic prototype")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", args.dev):
            raise ValueError("invalid interface name")
        cfg = synthesize(quantity(args.payload, "bytes"), args.rate, args.readers,
                         quantity(args.share, "rate"), quantity(args.rtt, "time"),
                         quantity(args.tau, "time"), args.alpha, header=args.header, intent=args.intent)
        cfg.update(dev=args.dev, peers=args.peer, middleware=args.rmw,
                   interval_s=.2, relay_in_survey=None, airtime_overhead_s=None,
                   scope="IPv4 UDP to peer(s) and SPDP multicast; includes other UDP to these peers")
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        if args.rmw == "fastdds":
            profiles.fastdds(cfg, out/"middleware.xml", args.address)
            env = 'export RMW_IMPLEMENTATION=rmw_fastrtps_cpp\nexport RMW_FASTRTPS_USE_QOS_FROM_XML=1\nexport FASTRTPS_DEFAULT_PROFILES_FILE="$ROSPACER_PROFILE_DIR/middleware.xml"\n'
        else:
            profiles.cyclone(cfg, out/"middleware.xml", args.dev, args.peer)
            env = 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp\nexport CYCLONEDDS_URI="file://$ROSPACER_PROFILE_DIR/middleware.xml"\n'
        (out/"env.bash").write_text('ROSPACER_PROFILE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"\n'+env,
                                     encoding="utf-8")
        (out/"sysctl.conf").write_text(f'net.core.wmem_max={cfg["socket_tx_bytes"]}\nnet.core.rmem_max={cfg["socket_rx_bytes"]}\n', encoding="utf-8")
        json_write(out/"governor.json", cfg)
        print(json.dumps(cfg, indent=2))
    elif args.command == "validate":
        profiles.validate(args.xml, args.schema)
        print("XML schema validation passed; live vendor parser still required")
    elif args.command in ("doctor", "probe"):
        from .linux import doctor, observe
        if args.command == "doctor":
            obj = doctor(args.dev)
        else:
            if args.seconds <= 0:
                raise ValueError("positive seconds required")
            obj, end = [], time.monotonic()+args.seconds
            while time.monotonic() < end:
                obj.append(observe(args.dev))
                time.sleep(.2)
        json_write(args.out, obj)
        print(f"Saved read-only observations: {args.out}")
    elif args.command == "calibrate":
        cfg = json.loads(Path(args.config).read_text())
        cfg["airtime_overhead_s"] = identify_overhead(cfg["capacity_Bps"],
                quantity(args.tx_rate, "rate"), quantity(args.rx_rate, "rate"),
                args.retries, cfg["unit_bytes"], cfg["header_bytes"])
        cfg["relay_in_survey"] = args.relay_in_survey == "yes"
        json_write(args.config, cfg)
        print("Calibration recorded; relay correction needs independent driver/AP validation")
    elif args.command == "govern":
        from .linux import govern
        cfg = json.loads(Path(args.config).read_text())
        print(json.dumps(govern(cfg, args.mode, args.seconds, args.trace, args.dry_run)))
    elif args.command == "restore":
        from .linux import restore
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", args.dev):
            raise ValueError("invalid interface name")
        print(json.dumps(restore(args.dev)))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ROSPacer: {exc}", file=sys.stderr)
        sys.exit(2)
