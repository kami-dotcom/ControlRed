import copy
import ipaddress
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frames import arp, checksum, icmp6, mac_text, mapping_frames, parse_neighbor
from network import Network, physical_contexts
from vendors import database, manufacturer


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.context = dict(ip='192.168.1.10', mac='00:10:20:30:40:50',
                            gateway='192.168.1.1', router_mac='00:11:22:33:44:55',
                            interface='physical-guid', routers_v6=['fe80::1'],
                            id='test', subnet='192.168.1.0/24')
        self.mac = '00:aa:bb:cc:dd:ee'
        self.fake = '02:00:00:00:00:99'

    def test_ipv4_blocks_both_directions_and_restores_real_macs(self):
        packets = mapping_frames(self.context, {('192.168.1.20', self.mac)}, self.fake)
        self.assertEqual(len(packets), 2)
        toward_phone, toward_router = map(parse_neighbor, packets)
        self.assertEqual((toward_phone['ip'], toward_phone['target']), ('192.168.1.1', '192.168.1.20'))
        self.assertEqual((toward_router['ip'], toward_router['target']), ('192.168.1.20', '192.168.1.1'))
        self.assertTrue(all(packet['mac'] == self.fake for packet in (toward_phone, toward_router)))
        restored = mapping_frames(self.context, {('192.168.1.20', self.mac)}, self.fake, True)
        self.assertEqual(mac_text(restored[0][22:28]), self.context['router_mac'])
        self.assertEqual(mac_text(restored[1][22:28]), self.mac)
        self.assertEqual(mac_text(restored[0][:6]), self.mac)
        self.assertEqual(mac_text(restored[1][:6]), self.context['router_mac'])

    def test_ipv6_unicast_override_checksum_and_restoration(self):
        packets = mapping_frames(self.context, {('2001:db8::20', self.mac)}, self.fake)
        self.assertEqual(len(packets), 2)
        for packet in packets:
            self.assertFalse(packet[0] & 1, 'The blockade must stay unicast.')
            self.assertEqual(packet[21], 255)
            self.assertEqual(packet[54], 136)
            body = packet[54:]
            pseudo = packet[22:54] + struct.pack('!I3xB', len(body), 58)
            self.assertEqual(checksum(pseudo + body), 0)
            self.assertTrue(int.from_bytes(packet[58:62], 'big') & 0x20000000)
            self.assertEqual(packet[78:80], b'\x02\x01')
        self.assertEqual(str(ipaddress.ip_address(packets[0][22:38])), 'fe80::1')
        self.assertEqual(str(ipaddress.ip_address(packets[1][22:38])), '2001:db8::20')
        restore = mapping_frames(self.context, {('2001:db8::20', self.mac)}, self.fake, True)
        self.assertEqual(restore[0][80:86].hex(), '001122334455')
        self.assertEqual(restore[1][80:86].hex(), '00aabbccddee')
        for packet in restore:
            body = packet[54:]
            pseudo = packet[22:54] + struct.pack('!I3xB', len(body), 58)
            self.assertEqual(checksum(pseudo + body), 0)

    def test_reassigned_ip_restores_new_owner(self):
        self.context['owners'] = {'192.168.1.20': '00:99:88:77:66:55'}
        packets = mapping_frames(self.context, {('192.168.1.20', self.mac)}, self.fake, True)
        self.assertEqual(mac_text(packets[1][22:28]), '00:99:88:77:66:55')

    def test_restoration_preserves_switch_forwarding_for_other_devices(self):
        forwarding = {self.context['router_mac']: 'router-port', self.mac: 'client-port'}
        packets = mapping_frames(self.context, {('192.168.1.20', self.mac),
                                                ('2001:db8::20', self.mac)}, self.fake, True)
        for packet in packets:
            source = mac_text(packet[6:12])
            self.assertEqual(source, self.context['mac'])
            forwarding[source] = 'controller-port'
        self.assertEqual(forwarding[self.context['router_mac']], 'router-port')
        self.assertEqual(forwarding[self.mac], 'client-port')

    def test_injected_restoration_does_not_create_false_neighbors(self):
        network = Network()
        network.capture = Mock()
        network.capture.read.return_value = mapping_frames(
            self.context, {('192.168.1.20', self.mac), ('2001:db8::20', self.mac)}, self.fake, True)
        network.observe(self.context)
        self.assertEqual(network.neighbors, {'test': {}})

    def test_router_and_local_pc_never_targeted(self):
        targets = {(self.context['ip'], self.context['mac']),
                   ('fe80::1', self.context['router_mac']),
                   (self.context['gateway'], self.mac)}
        self.assertEqual(mapping_frames(self.context, targets, self.fake), [])

    def test_vpn_adapter_does_not_replace_physical_adapter(self):
        physical = dict(guid='{physical}', label='Ethernet', description='Realtek', type='Ethernet',
                        ip='192.168.1.10', mask='255.255.255.0', gateway='192.168.1.1', mac=self.context['mac'])
        tunnel = dict(physical, guid='{vpn}', label='VPN', description='WireGuard Tunnel')
        contexts = physical_contexts([tunnel, physical])
        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0]['interface'], '\\Device\\NPF_{physical}')
        network = Network()
        network.can_block = True
        network.capture = Mock()
        network.mapping(self.context, {('192.168.1.20', self.mac)})
        self.assertEqual(network.capture.send.call_args.args[0], 'physical-guid')

    def test_invalid_and_damaged_discovery_frames_are_rejected(self):
        self.assertIsNone(parse_neighbor(b'\0' * 5))
        body = struct.pack('!BBHI', 136, 0, 0, 0x20000000) + ipaddress.IPv6Address('fe80::20').packed
        packet = icmp6(self.mac, self.context['mac'], 'fe80::20', 'fe80::10', body)
        self.assertIsNotNone(parse_neighbor(packet))
        damaged = bytearray(packet)
        damaged[-1] ^= 1
        self.assertIsNone(parse_neighbor(bytes(damaged)))

    def test_manufacturer_registry_and_private_mac(self):
        self.assertGreater(len(database()), 50000)
        self.assertIn('ASUSTek', manufacturer('b0:82:e2:00:00:01'))
        self.assertEqual(manufacturer('02:11:22:33:44:55'), 'MAC privada / local')
        self.assertEqual(manufacturer('invalid'), 'MAC inválida')
        registry = database()
        for size in (7, 9):
            prefix = next(key for key in registry if len(key) == size and int(key[:2], 16) & 3 == 0)
            self.assertEqual(manufacturer(prefix.ljust(12, '0')), registry[prefix])
