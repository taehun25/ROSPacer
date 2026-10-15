from pathlib import Path
p=Path(__file__).with_name('traffic.py');s=p.read_text()
s=s.replace('    a = p.parse_args()', '    p.add_argument("--start-wall",type=float,default=0)\n    p.add_argument("--warmup-seconds",type=float,default=0)\n    a = p.parse_args()')
s=s.replace('            end = time.monotonic()+a.seconds\n            measurement_started_ns', '''            if a.start_wall:
                while time.time()<a.start_wall:time.sleep(min(.1,a.start_wall-time.time()))
            warm_end=time.monotonic()+a.warmup_seconds
            warm_due=time.monotonic()
            while time.monotonic()<warm_end:
                msg.data[:16]=array('B',struct.pack("!QQ",2**64-1,time.time_ns()))
                try:endpoint.publish(msg)
                except Exception as exc:publisher_errors.append('warmup: '+str(exc))
                warm_due+=1/a.hz
                rclpy.spin_once(node,timeout_sec=0)
                time.sleep(max(0,min(warm_due-time.monotonic(),warm_end-time.monotonic())))
            Path(a.out).with_suffix('.start.json').write_text(json.dumps({'wall_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),'nominal_wall':a.start_wall+a.warmup_seconds}))
            end = time.monotonic()+a.seconds
            measurement_started_ns''')
s=s.replace('                duplicates += int(seq in ids)','                if seq>=a.count:return\n                duplicates += int(seq in ids)')
s=s.replace('            while len(ids) < a.count and time.monotonic() < end:', '            if a.start_wall:end=time.monotonic()+max(0,a.start_wall+a.warmup_seconds+a.seconds+a.drain_seconds+8-time.time())\n            while time.monotonic() < end:')
s=s.replace('"Small ROS 2 smoke source/sink; not a replacement for a research benchmark.', '"W2 source/sink, derived from the retained W1 source; explicit warmup and raw timing.')
out=p.with_name('w2_traffic.py');out.write_text(s)
compile(s,str(out),'exec');print(str(out))
