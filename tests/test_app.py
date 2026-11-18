import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Handler, Server
from engine import Controller
from network import DemoNetwork


class RecordingNetwork(DemoNetwork):
    def __init__(self):
        self.calls = []
        self.failure = False
        self.moved = False
        self.scans = 0

    def scan(self, context):
        self.scans += 1
        devices = super().scan(context)
        if self.moved:
            devices['192.168.1.99'] = devices.pop('192.168.1.20')
        return devices

    def mapping(self, context, targets, restore=False):
        self.calls.append((set(targets), restore))
        if self.failure and not restore:
            raise OSError('Simulated transmission failure')


def wait_for(check, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.02)
    raise AssertionError('Operation timed out')


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.network = RecordingNetwork()
        self.controller = Controller(self.network, self.directory.name, demo=True)
        wait_for(lambda: self.controller.snapshot()['last_scan'])
        self.mac = '02:00:00:00:00:14'

    def tearDown(self):
        self.controller.close()
        self.directory.cleanup()

    def command(self, action, **body):
        self.controller.submit(action, body)
        wait_for(lambda: not self.controller.snapshot()['busy'])

    def test_block_restore_and_protected_devices(self):
        self.command('block', mac=self.mac, blocked=True)
        self.assertTrue(self.controller.device(self.mac)['blocked'])
        self.assertIn(({('192.168.1.20', self.mac)}, False), self.network.calls)
        self.command('block', mac='02:00:00:00:00:01', blocked=True)
        self.assertFalse(self.controller.device('02:00:00:00:00:01')['blocked'])
        self.assertTrue(self.controller.device(self.mac)['blocked'])
        self.command('block', mac=self.mac, blocked=False)
        self.assertFalse(self.controller.affected)
        self.assertTrue(self.network.calls[-1][1])

    def test_alias_survives_restart(self):
        self.command('rename', mac=self.mac, name='Teléfono del salón')
        self.controller.close()
        self.controller = Controller(self.network, self.directory.name, demo=True)
        wait_for(lambda: self.controller.snapshot()['last_scan'])
        self.assertEqual(self.controller.device(self.mac)['alias'], 'Teléfono del salón')

    def test_dhcp_change_restores_old_address(self):
        self.command('block', mac=self.mac, blocked=True)
        self.network.moved = True
        self.command('scan')
        wait_for(lambda: ('192.168.1.99', self.mac) in self.controller.affected)
        self.assertIn(({('192.168.1.20', self.mac)}, True), self.network.calls)
        self.assertNotIn(('192.168.1.20', self.mac), self.controller.affected)

    def test_partial_failure_restores_attempted_targets(self):
        self.network.failure = True
        self.command('block', mac=self.mac, blocked=True)
        self.assertFalse(self.controller.affected)
        self.assertFalse(self.controller.device(self.mac)['blocked'])
        self.assertIn('Simulated transmission failure', self.controller.snapshot()['error'])
        self.assertTrue(self.network.calls[-1][1])

    def test_manual_discovery_keeps_blocking_without_panel_until_shutdown(self):
        self.command('block', mac=self.mac, blocked=True)
        self.controller.last_heartbeat = time.monotonic() - 30
        scans = self.network.scans
        calls = len(self.network.calls)
        # Advance beyond the old scan and panel-disconnect deadlines.
        with patch('engine.time', wraps=time) as clock:
            clock.monotonic.return_value = time.monotonic() + 120
            wait_for(lambda: len(self.network.calls) > calls)
            self.assertEqual(self.network.scans, scans)
            self.assertTrue(self.controller.device(self.mac)['blocked'])
            self.assertFalse(any(restore for _, restore in self.network.calls))
            self.command('scan')
            self.assertEqual(self.network.scans, scans + 1)
            self.assertTrue(self.controller.device(self.mac)['blocked'])
        self.assertTrue(self.controller.close())
        self.assertTrue(self.network.calls[-1][1])

    def test_missing_scan_response_keeps_block_until_explicit_release(self):
        self.command('block', mac=self.mac, blocked=True)
        original = self.network.scan
        def missing_device(context):
            result = original(context)
            result.pop('192.168.1.20')
            return result
        self.network.scan = missing_device
        self.command('scan')
        self.assertFalse(self.controller.device(self.mac)['online'])
        calls = len(self.network.calls)
        self.controller.next_send = 0
        wait_for(lambda: len(self.network.calls) > calls)
        self.assertEqual(self.controller.affected, {('192.168.1.20', self.mac)})
        self.assertFalse(any(restore for _, restore in self.network.calls))
        self.command('release')
        self.assertFalse(self.controller.affected)

    def test_recovery_journal(self):
        self.controller.close()
        journal = Path(self.directory.name) / 'recovery.json'
        journal.write_text(json.dumps(dict(context=self.controller.context,
                                           targets=[['192.168.1.20', self.mac]])), encoding='utf-8')
        self.controller = Controller(self.network, self.directory.name, demo=True)
        wait_for(lambda: self.network.calls)
        self.assertTrue(self.network.calls[-1][1])
        wait_for(lambda: not self.controller.affected)

    def test_mac_policy_follows_new_addresses_before_next_scan(self):
        self.command('block', mac=self.mac, blocked=True)
        self.controller.context['routers_v6'] = ['fe80::1']
        self.network.discovered_neighbors = lambda context: {
            '192.168.1.20': '00:99:88:77:66:55',
            '192.168.1.99': self.mac,
            'fe80::20': self.mac,
            '2001:db8::20': self.mac,
        }
        expected = {('192.168.1.99', self.mac), ('fe80::20', self.mac), ('2001:db8::20', self.mac)}
        wait_for(lambda: self.controller.affected == expected)
        self.assertTrue(self.controller.device(self.mac)['blocked'])
        self.assertEqual(self.controller.device(self.mac)['ip'], '192.168.1.99')
        self.command('release')
        self.assertFalse(self.controller.affected)
        self.assertEqual(self.network.calls[-1], (expected, True))

    def test_initial_scan_failure_can_be_retried(self):
        self.controller.close()
        normal_scan = self.network.scan
        self.network.scan = lambda context: (_ for _ in ()).throw(OSError('temporary capture failure'))
        self.controller = Controller(self.network, self.directory.name, demo=True)
        wait_for(lambda: self.controller.snapshot()['error'])
        self.network.scan = normal_scan
        self.command('scan')
        self.assertTrue(self.controller.snapshot()['last_scan'])
        self.assertEqual(self.controller.snapshot()['error'], '')

    def test_api_authentication_origin_and_payloads(self):
        server = Server(('127.0.0.1', 0), Handler)
        server.controller = self.controller
        server.token = 'test-session'
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'

        def request(path, token='test-session', body=None, origin=None):
            headers = {'X-Control-Token': token, 'Content-Type': 'application/json'}
            if origin:
                headers['Origin'] = origin
            data = None if body is None else json.dumps(body).encode()
            req = urllib.request.Request(base + path, data=data, headers=headers)
            return urllib.request.urlopen(req, timeout=3)

        try:
            with self.assertRaises(urllib.error.HTTPError) as denied:
                request('/api/state', token='wrong')
            self.assertEqual(denied.exception.code, 403)
            with self.assertRaises(urllib.error.HTTPError) as denied:
                request('/api/block', body={'mac': self.mac, 'blocked': True}, origin='http://foreign.example')
            self.assertEqual(denied.exception.code, 403)
            with self.assertRaises(urllib.error.HTTPError) as invalid:
                request('/api/block', body={'mac': self.mac, 'blocked': 'true'})
            self.assertEqual(invalid.exception.code, 400)
            for path, body in [('/api/mode', {'mode': True}), ('/api/allow', {'mac': self.mac, 'allowed': 'yes'}),
                               ('/api/allow', {'mac': self.mac, 'allowed': True, 'name': 42})]:
                with self.assertRaises(urllib.error.HTTPError) as invalid:
                    request(path, body=body)
                self.assertEqual(invalid.exception.code, 400)
            with request('/api/state') as response:
                self.assertEqual(len(json.load(response)['devices']), 6)
            with request('/api/block', body={'mac': self.mac, 'blocked': True}) as response:
                self.assertEqual(response.status, 202)
            wait_for(lambda: self.controller.device(self.mac)['blocked'])
            for path in ['/', '/app.js', '/style.css']:
                with request(path) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
