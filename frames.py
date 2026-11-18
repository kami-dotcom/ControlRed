"""Ethernet control messages. These functions do not send traffic."""
import ipaddress
import struct


def mac_bytes(mac):
    return bytes.fromhex(mac.replace(':', '').replace('-', ''))


def mac_text(value):
    return ':'.join(f'{byte:02x}' for byte in value)


def ethernet(source, destination, protocol, payload):
    return mac_bytes(destination) + mac_bytes(source) + struct.pack('!H', protocol) + payload


def arp(source_mac, source_ip, target_mac, target_ip, reply=True, *, frame_source=None):
    payload = struct.pack('!HHBBH', 1, 0x0800, 6, 4, 2 if reply else 1)
    payload += mac_bytes(source_mac) + ipaddress.IPv4Address(source_ip).packed
    payload += mac_bytes(target_mac) + ipaddress.IPv4Address(target_ip).packed
    destination = target_mac if reply else 'ff:ff:ff:ff:ff:ff'
    return ethernet(frame_source or source_mac, destination, 0x0806, payload)


def checksum(data):
    data += b'\0' * (len(data) % 2)
    total = sum(struct.unpack(f'!{len(data) // 2}H', data))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return (~total) & 65535


def icmp6(source_mac, target_mac, source_ip, target_ip, body, hop_limit=255, *, frame_source=None):
    source = ipaddress.IPv6Address(source_ip).packed
    target = ipaddress.IPv6Address(target_ip).packed
    pseudo = source + target + struct.pack('!I3xB', len(body), 58)
    body = body[:2] + struct.pack('!H', checksum(pseudo + body)) + body[4:]
    header = struct.pack('!IHBB', 6 << 28, len(body), 58, hop_limit) + source + target
    return ethernet(frame_source or source_mac, target_mac, 0x86dd, header + body)


def neighbor_advertisement(source_mac, target_mac, source_ip, target_ip, router=False, *, frame_source=None):
    # Unsolicited unicast advertisement with Override. Only the selected endpoint receives it.
    flags = 0x20000000 | (0x80000000 if router else 0)
    body = struct.pack('!BBHI', 136, 0, 0, flags) + ipaddress.IPv6Address(source_ip).packed
    body += bytes([2, 1]) + mac_bytes(source_mac)
    return icmp6(source_mac, target_mac, source_ip, target_ip, body, frame_source=frame_source)


def discovery_v6(context):
    source = next((ip for ip in context.get('local_ipv6', []) if ipaddress.ip_address(ip).is_link_local), None)
    if not source:
        return []
    rs = struct.pack('!BBHI', 133, 0, 0, 0) + bytes([1, 1]) + mac_bytes(context['mac'])
    echo = struct.pack('!BBHHH', 128, 0, 0, 0x4352, 1) + b'ControlRed'
    return [icmp6(context['mac'], '33:33:00:00:00:02', source, 'ff02::2', rs),
            icmp6(context['mac'], '33:33:00:00:00:01', source, 'ff02::1', echo, hop_limit=64)]


def parse_neighbor(packet):
    if len(packet) < 14:
        return None
    source_mac = mac_text(packet[6:12])
    if packet[6] & 1 or packet[6:12] == b'\0' * 6:
        return None
    protocol = struct.unpack_from('!H', packet, 12)[0]
    if protocol == 0x0806 and len(packet) >= 42:
        if packet[14:20] != b'\x00\x01\x08\x00\x06\x04' or packet[22:28] != packet[6:12]:
            return None
        return dict(ip=str(ipaddress.IPv4Address(packet[28:32])), mac=source_mac,
                    router=False, protocol='arp', op=int.from_bytes(packet[20:22], 'big'),
                    target=str(ipaddress.IPv4Address(packet[38:42])))
    if protocol == 0x86dd and len(packet) >= 62 and packet[20] == 58:
        length = int.from_bytes(packet[18:20], 'big')
        if len(packet) < 54 + length or length < 8:
            return None
        body = packet[54:54 + length]
        pseudo = packet[22:54] + struct.pack('!I3xB', length, 58)
        if checksum(pseudo + body) != 0 or body[1] != 0:
            return None
        if body[0] not in {129, 133, 134, 135, 136}:
            return None
        if body[0] in {133, 134, 135, 136} and packet[21] != 255:
            return None
        source = ipaddress.IPv6Address(packet[22:38])
        if source.is_unspecified or source.is_multicast:
            return None
        router = body[0] == 134 and source.is_link_local and length >= 16 and body[6:8] != b'\0\0'
        return dict(ip=str(source), mac=source_mac, router=router, protocol='icmp6')
    return None


def mapping_frames(context, targets, fake_mac, restore=False):
    frames = []
    gateway_mac = context['router_mac']
    # Keep real peers out of Ethernet source learning on the controller's port.
    # ARP/NDP payloads still advertise the correct peer MAC when restoring.
    frame_source = context['mac'] if restore else None
    for ip, mac in sorted(targets):
        # The protected addresses are excluded even if a caller supplies an invalid target.
        if mac in {context['mac'], gateway_mac} or ip in {context['ip'], context['gateway']}:
            continue
        router_source = gateway_mac if restore else fake_mac
        client_source = context.get('owners', {}).get(ip, mac) if restore else fake_mac
        if ipaddress.ip_address(ip).version == 4:
            frames.append(arp(router_source, context['gateway'], mac, ip, frame_source=frame_source))
            frames.append(arp(client_source, ip, gateway_mac, context['gateway'], frame_source=frame_source))
        else:
            for router_ip in context.get('routers_v6', []):
                frames.append(neighbor_advertisement(router_source, mac, router_ip, ip, router=True, frame_source=frame_source))
                frames.append(neighbor_advertisement(client_source, gateway_mac, ip, router_ip, frame_source=frame_source))
    return frames
