"""Discovery and access control bound to a physical Windows network adapter."""
from i18n import message, error_message
import ctypes
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from frames import arp, discovery_v6, mapping_frames, parse_neighbor
from npcap import Npcap


def normalize_mac(value):
    return value.lower().replace('-', ':')


def physical_contexts(adapters):
    contexts = []
    for adapter in adapters:
        description = (adapter['label'] + ' ' + adapter.get('description', '')).lower()
        virtual = any(word in description for word in ('wireguard', 'wintun', 'openvpn', 'tap-windows', 'vpn', 'virtual', 'loopback'))
        if virtual or adapter.get('type') not in {'Ethernet', 'Wireless80211'} or not adapter['mac']:
            continue
        subnet = ipaddress.ip_network(f"{adapter['ip']}/{adapter['mask']}", strict=False)
        if ipaddress.ip_address(adapter['gateway']) not in subnet:
            continue
        contexts.append(dict(id=f"{adapter['ip']}@{adapter['gateway']}",
                             adapter_guid=adapter['guid'], interface='\\Device\\NPF_' + adapter['guid'],
                             label=adapter['label'], ip=adapter['ip'], mac=normalize_mac(adapter['mac']),
                             gateway=adapter['gateway'], subnet=str(subnet),
                             local_ipv6=adapter.get('ipv6', []), routers_v6=[]))
    return sorted(contexts, key=lambda item: (item['label'], item['id']))


class Network:
    def __init__(self):
        self.capture = None
        self.routes = {}
        self.neighbors = {}
        self.router_advertisements = {}
        self.fake_mac = '02:' + ':'.join(f'{b:02x}' for b in secrets.token_bytes(5))
        self.problem = ''
        self.can_block = False

    def interfaces(self):
        if os.name != 'nt':
            raise OSError(message('err_windows'))
        script = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
@([System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | Where-Object { $_.OperationalStatus -eq 'Up' } | ForEach-Object {
    $adapter = $_
    $config = $adapter.GetIPProperties()
    $gateway = $config.GatewayAddresses | Where-Object { $_.Address.AddressFamily -eq 'InterNetwork' } | Select-Object -First 1
    $ipv6 = @($config.UnicastAddresses | Where-Object { $_.Address.AddressFamily -eq 'InterNetworkV6' } | ForEach-Object { $_.Address.ToString().Split('%')[0] })
    foreach ($address in $config.UnicastAddresses) {
      if ($gateway -and $address.Address.AddressFamily -eq 'InterNetwork') {
        [pscustomobject]@{
            guid = $adapter.Id
            label = $adapter.Name
            description = $adapter.Description
            type = $adapter.NetworkInterfaceType.ToString()
            ip = $address.Address.ToString()
            mask = $address.IPv4Mask.ToString()
            mac = ($adapter.GetPhysicalAddress().GetAddressBytes() | ForEach-Object { $_.ToString('x2') }) -join ':'
            gateway = $gateway.Address.ToString()
            ipv6 = $ipv6
        }
      }
    }
}) | ConvertTo-Json -Depth 4 -Compress
"""
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError(message('err_adapters'))
        adapters = json.loads(result.stdout.decode('utf-8-sig').strip() or '[]')
        if isinstance(adapters, dict):
            adapters = [adapters]
        contexts = physical_contexts(adapters)
        self.routes = {context['id']: context for context in contexts}
        try:
            self.capture = Npcap()
            self.can_block = True
            self.problem = ''
        except OSError as error:
            self.problem = error_message(error)
        return contexts

    def observe(self, context):
        if not self.capture:
            return
        subnet = ipaddress.ip_network(context['subnet'])
        neighbors = self.neighbors.setdefault(context['id'], {})
        routers = self.router_advertisements.setdefault(context['id'], {})
        for packet in self.capture.read(context['interface']):
            neighbor = parse_neighbor(packet)
            if not neighbor or neighbor['mac'] in {self.fake_mac, context['mac']}:
                continue
            address = ipaddress.ip_address(neighbor['ip'])
            if address.version == 4 and (address not in subnet or neighbor.get('op') not in {1, 2}):
                continue
            neighbors[neighbor['ip']] = (neighbor['mac'], time.monotonic())
            if neighbor['router']:
                routers[neighbor['ip']] = (neighbor['mac'], time.monotonic())
        discovered_routers = {ip for ip, (mac, seen) in routers.items()
                              if mac == context.get('router_mac') and time.monotonic() - seen < 600}
        # Retain previously used router addresses so every changed entry can be restored.
        context['routers_v6'] = sorted(set(context.get('routers_v6', [])) | discovered_routers)

    def discovered_neighbors(self, context):
        if not self.can_block:
            return {}
        self.observe(context)
        return {ip: mac for ip, (mac, seen) in self.neighbors.get(context['id'], {}).items()
                if time.monotonic() - seen < 120}

    def scan(self, context):
        subnet = ipaddress.ip_network(context['subnet'])
        if subnet.num_addresses > 1024:
            raise RuntimeError(message('err_network_size'))
        addresses = [str(ip) for ip in subnet.hosts() if str(ip) != context['ip']]
        if not self.capture:
            with ThreadPoolExecutor(max_workers=32) as pool:
                replies = dict(filter(None, pool.map(lambda ip: self.windows_arp(ip, context['ip']), addresses)))
        else:
            try:
                self.capture.open(context['interface'])
                self.can_block = True
                self.problem = ''
            except OSError as error:
                self.can_block = False
                self.problem = error_message(error)
                raise
            self.capture.read(context['interface'])
            started = time.monotonic()
            for offset in range(0, len(addresses), 32):
                requests = [arp(context['mac'], context['ip'], '00:00:00:00:00:00', ip, reply=False)
                            for ip in addresses[offset:offset + 32]]
                self.capture.send(context['interface'], requests)
                self.observe(context)
                time.sleep(0.01)
            self.capture.send(context['interface'], discovery_v6(context))
            deadline = time.monotonic() + 2.5
            while time.monotonic() < deadline:
                self.observe(context)
                time.sleep(0.03)
            replies = {ip: mac for ip, (mac, seen) in self.neighbors.get(context['id'], {}).items()
                       if seen >= started}
        replies[context['ip']] = context['mac']
        return replies

    @staticmethod
    def windows_arp(ip, local):
        destination = int.from_bytes(socket.inet_aton(ip), 'little')
        source = int.from_bytes(socket.inet_aton(local), 'little')
        buffer = ctypes.create_string_buffer(8)
        length = ctypes.c_ulong(6)
        result = ctypes.windll.iphlpapi.SendARP(destination, source, buffer, ctypes.byref(length))
        if result == 0 and length.value == 6:
            return ip, ':'.join(f'{b:02x}' for b in buffer.raw[:6])
        return None

    def mapping(self, context, targets, restore=False):
        if not targets:
            return
        if not self.can_block:
            raise RuntimeError(self.problem)
        frames = mapping_frames(context, targets, self.fake_mac, restore)
        for _ in range(3 if restore else 1):
            self.capture.send(context['interface'], frames)
            if restore:
                time.sleep(0.08)

    def close(self):
        if self.capture:
            self.capture.close()


class DemoNetwork:
    """Explicitly simulated devices for UI previews and integration checks."""
    can_block = True
    problem = ''

    def interfaces(self):
        return [dict(id='demo', label=message('demo_network'), interface='demo', ip='192.168.1.10',
                     mac='02:00:00:00:00:0a', gateway='192.168.1.1', subnet='192.168.1.0/24', routers_v6=[])]

    def scan(self, context):
        time.sleep(0.15)
        return {f'192.168.1.{n}': f'02:00:00:00:00:{n:02x}' for n in [1, 10, 20, 30, 40, 50]}

    def discovered_neighbors(self, context):
        return {}

    def mapping(self, context, targets, restore=False):
        pass

    def close(self):
        pass

    @staticmethod
    def name(ip):
        return {'192.168.1.20': message('demo_phone'), '192.168.1.30': 'Samsung TV',
                '192.168.1.40': message('demo_laptop'), '192.168.1.50': message('demo_printer')}.get(ip, '')

