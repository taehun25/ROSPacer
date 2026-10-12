from pathlib import Path
import xml.etree.ElementTree as E


def child(parent, tag, text=None, **attrs):
    el = E.SubElement(parent, tag, attrs)
    if text is not None:
        el.text = str(text)
    return el


def duration(parent, tag, seconds):
    d = child(parent, tag)
    child(d, "sec", int(seconds))
    child(d, "nanosec", round((seconds-int(seconds))*1e9))


def write_xml(root, path):
    E.indent(root)
    E.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def fastdds(cfg, path, address):
    root = E.Element("dds", xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles")
    collection = child(root, "profiles")
    transports = child(collection, "transport_descriptors")
    tr = child(transports, "transport_descriptor")
    child(tr, "transport_id", "rospacer_udp")
    child(tr, "type", "UDPv4")
    child(tr, "maxMessageSize", cfg["unit_bytes"])
    child(tr, "sendBufferSize", cfg["socket_tx_bytes"])
    child(tr, "receiveBufferSize", cfg["socket_rx_bytes"])
    child(child(tr, "interfaceWhiteList"), "address", address)
    child(tr, "non_blocking_send", "false")
    participant = child(collection, "participant", profile_name="rospacer_participant", is_default_profile="true")
    rtps = child(participant, "rtps")
    child(rtps, "useBuiltinTransports", "false")
    child(child(rtps, "userTransports"), "transport_id", "rospacer_udp")
    for role in ("publisher", "subscriber"):
        endpoint = child(collection, role, profile_name=f"rospacer_{role}", is_default_profile="true")
        topic = child(endpoint, "topic")
        child(topic, "kind", "NO_KEY")
        hist = child(topic, "historyQos")
        child(hist, "kind", "KEEP_ALL" if cfg["intent"] == "complete" else "KEEP_LAST")
        child(hist, "depth", cfg["cache_samples"])
        limits = child(topic, "resourceLimitsQos")
        for tag in ("max_samples", "max_samples_per_instance", "allocated_samples"):
            child(limits, tag, cfg["cache_samples"])
        child(limits, "max_instances", 1)
        qos = child(endpoint, "qos")
        reliable = child(qos, "reliability")
        child(reliable, "kind", "RELIABLE")
        duration(reliable, "max_blocking_time", 1.0)
        if role == "publisher":
            child(child(qos, "publishMode"), "kind", "SYNCHRONOUS")
            child(child(qos, "data_sharing"), "kind", "OFF")
        times = child(endpoint, "times")
        if role == "publisher":
            duration(times, "heartbeatPeriod", cfg["feedback_s"])
        else:
            duration(times, "heartbeatResponseDelay", .005)
        child(endpoint, "historyMemoryPolicy", "PREALLOCATED_WITH_REALLOC")
    write_xml(root, path)


def cyclone(cfg, path, dev, peer):
    root = E.Element("CycloneDDS", xmlns="https://cdds.io/config")
    domain = child(root, "Domain", Id="any")
    general = child(domain, "General")
    child(child(general, "Interfaces"), "NetworkInterface", name=dev)
    child(general, "AllowMulticast", "spdp")
    child(general, "MaxMessageSize", f'{cfg["unit_bytes"]} B')
    # W1 UInt8MultiArray captures: the first fragment carries INFO_TS and
    # needs68 bytes of RTPS framing. A64-byte reserve emitted1476-byte UDP
    # payloads despite MaxMessageSize1472 and bypassed the unfragmented filter.
    # Preserve larger caller-provided reserves for other types/configurations.
    cfg["fragment_bytes"] = cfg["unit_bytes"]-max(68,cfg["header_bytes"])
    child(general, "FragmentSize", f'{cfg["fragment_bytes"]} B')
    peers = child(child(domain, "Discovery"), "Peers")
    for address in ([peer] if isinstance(peer, str) else peer):
        child(peers, "Peer", Address=address)
    internal = child(domain, "Internal")
    t = f'{cfg["feedback_s"]*1000:g} ms'
    child(internal, "HeartbeatInterval", t, min="5 ms", max=t, minsched=t)
    child(internal, "NackDelay", "5 ms")
    for tag, key in (("SocketSendBufferSize", "socket_tx_bytes"),
                     ("SocketReceiveBufferSize", "socket_rx_bytes")):
        val = f'{cfg[key]} B'
        child(internal, tag, min=val, max=val)
    whc = child(internal, "Watermarks")
    child(whc, "WhcAdaptive", "false")
    child(whc, "WhcHigh", f'{cfg["cache_bytes"]} B')
    child(whc, "WhcHighInit", f'{cfg["cache_bytes"]} B')
    child(whc, "WhcLow", f'{max(cfg["payload_bytes"], cfg["cache_bytes"]//2)} B')
    write_xml(root, path)


def validate(xml_path, schema_path):
    try:
        from lxml import etree
    except ImportError:
        raise RuntimeError("XML schema validation requires python3-lxml")
    try:
        schema = etree.XMLSchema(etree.parse(str(schema_path)))
        schema.assertValid(etree.parse(str(xml_path)))
    except (etree.XMLSchemaParseError, etree.DocumentInvalid, etree.XMLSyntaxError) as exc:
        raise RuntimeError(f"XML validation failed: {exc}") from exc
    return True
