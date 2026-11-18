import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from access import AccessStore, normalize_mac
from engine import Controller
from test_app import RecordingNetwork, wait_for


class AllowlistTests(unittest.TestCase):
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

    def restart(self):
        self.controller.close()
        self.controller = Controller(self.network, self.directory.name, demo=True)
        wait_for(lambda: self.controller.snapshot()['last_scan'])

    def test_default_manual_and_protected_exceptions(self):
        self.assertEqual(self.controller.snapshot()['policy']['mode'], 'manual')
        self.assertFalse(self.controller.affected)
        self.command('mode', mode='allowlist')
        devices = self.controller.snapshot()['devices']
        self.assertEqual(len(self.controller.affected), 4)
        for device in devices:
            self.assertEqual(device['blocked'], not device['protected'])
        self.command('allow', mac=self.controller.context['mac'], allowed=False)
        self.assertIn('automáticamente', self.controller.snapshot()['error'])
        self.assertFalse(self.controller.device(self.controller.context['mac'])['blocked'])
        self.assertEqual(len(self.controller.affected), 4)

    def test_allow_restore_revoke_and_restart(self):
        self.command('mode', mode='allowlist')
        self.command('allow', mac=self.mac, allowed=True)
        self.assertNotIn(('192.168.1.20', self.mac), self.controller.affected)
        self.assertIn(({('192.168.1.20', self.mac)}, True), self.network.calls)
        self.restart()
        wait_for(lambda: len(self.controller.affected) == 3)
        self.assertFalse(self.controller.device(self.mac)['blocked'])
        self.assertEqual(self.controller.snapshot()['policy']['mode'], 'allowlist')
        self.command('block', mac=self.mac, blocked=True)
        self.assertIn(('192.168.1.20', self.mac), self.controller.affected)
        self.assertEqual(self.controller.snapshot()['policy']['entries'], [])

    def test_preapprove_mac_and_detect_unknown_before_scan(self):
        permitted = 'aa:bb:cc:dd:ee:02'
        unknown = '02:00:00:00:01:03'
        self.command('allow', mac=' AA-BB-CC-DD-EE-02 ', allowed=True, name='Mi equipo')
        self.command('mode', mode='allowlist')
        self.network.discovered_neighbors = lambda context: {'192.168.1.88': permitted, '192.168.1.89': unknown}
        wait_for(lambda: ('192.168.1.89', unknown) in self.controller.affected)
        self.assertNotIn(('192.168.1.88', permitted), self.controller.affected)
        self.assertEqual(self.controller.device(permitted)['alias'], 'Mi equipo')
        self.assertTrue(self.controller.device(permitted)['allowed'])
        self.command('allow', mac=permitted, allowed=False)
        self.assertIn(('192.168.1.88', permitted), self.controller.affected)

    def test_allowance_follows_mac_across_ipv4_ipv6_changes(self):
        self.command('allow', mac=self.mac, allowed=True)
        self.command('mode', mode='allowlist')
        self.controller.context['routers_v6'] = ['fe80::1']
        intruder = '02:00:00:00:01:04'
        self.network.discovered_neighbors = lambda context: {
            '192.168.1.20': intruder, '192.168.1.99': self.mac, 'fe80::20': self.mac,
            '2001:db8::20': self.mac, 'fe80::99': intruder,
        }
        wait_for(lambda: ('fe80::99', intruder) in self.controller.affected)
        self.assertIn(('192.168.1.20', intruder), self.controller.affected)
        self.assertFalse(any(mac == self.mac for _, mac in self.controller.affected))
        self.assertEqual(self.controller.device(self.mac)['ip'], '192.168.1.99')

    def test_pause_survives_scans_and_permission_edits_until_resume(self):
        self.command('mode', mode='allowlist')
        self.command('release')
        self.command('scan')
        self.command('allow', mac=self.mac, allowed=True)
        self.assertTrue(self.controller.snapshot()['policy']['paused'])
        self.assertFalse(self.controller.affected)
        self.command('resume')
        self.assertEqual(len(self.controller.affected), 3)
        self.assertFalse(self.controller.snapshot()['policy']['paused'])

    def test_allowlist_stays_active_without_panel_and_blocks_new_devices(self):
        for device in self.controller.snapshot()['devices']:
            if not device['protected']:
                self.command('allow', mac=device['mac'], allowed=True)
        self.command('mode', mode='allowlist')
        self.assertFalse(self.controller.affected)
        self.controller.last_heartbeat = time.monotonic() - 30
        unknown = '02:00:00:00:01:03'
        scans = self.network.scans
        self.network.discovered_neighbors = lambda context: {'192.168.1.89': unknown}
        with patch('engine.time', wraps=time) as clock:
            clock.monotonic.return_value = time.monotonic() + 120
            wait_for(lambda: ('192.168.1.89', unknown) in self.controller.affected)
        self.assertFalse(self.controller.snapshot()['policy']['paused'])
        self.assertEqual(self.network.scans, scans)
        self.command('release')
        self.assertFalse(self.controller.affected)

    def test_transmission_failure_pauses_without_forgetting_list(self):
        self.command('allow', mac=self.mac, allowed=True)
        self.network.failure = True
        self.command('mode', mode='allowlist')
        self.assertTrue(self.controller.snapshot()['policy']['paused'])
        self.assertFalse(self.controller.affected)
        self.assertTrue(self.network.calls[-1][1])
        self.network.failure = False
        self.command('scan')
        self.assertFalse(self.controller.affected)
        self.command('resume')
        self.assertEqual(len(self.controller.affected), 3)

    def test_manual_mode_restores_and_keeps_saved_entries(self):
        self.command('allow', mac=self.mac, allowed=True)
        self.command('mode', mode='allowlist')
        self.command('mode', mode='manual')
        self.assertFalse(self.controller.affected)
        self.assertEqual(len(self.controller.snapshot()['policy']['entries']), 1)
        self.command('block', mac=self.mac, blocked=True)
        self.assertIn(('192.168.1.20', self.mac), self.controller.affected)
        self.command('mode', mode='allowlist')
        self.assertNotIn(('192.168.1.20', self.mac), self.controller.affected)

    def test_invalid_and_failed_writes_preserve_permissions(self):
        self.command('allow', mac=self.mac, allowed=True)
        before = (Path(self.directory.name) / 'access.json').read_bytes()
        for invalid in ['garbage', 'ff:ff:ff:ff:ff:ff', '00:00:00:00:00:00', '01:00:00:00:00:02']:
            self.command('allow', mac=invalid, allowed=True)
            self.assertTrue(self.controller.snapshot()['error'])
        with patch.object(self.controller.access_store, 'save', side_effect=OSError('Disk unavailable')):
            self.command('allow', mac=self.mac, allowed=False)
        self.assertEqual((Path(self.directory.name) / 'access.json').read_bytes(), before)
        self.assertTrue(self.controller.device(self.mac)['allowed'])

    def test_permissions_are_isolated_per_router(self):
        self.command('allow', mac=self.mac, allowed=True)
        self.command('mode', mode='allowlist')
        router_b = '02:00:00:00:02:01'
        original = self.network.scan
        def other_network(context):
            result = original(context)
            result[context['gateway']] = router_b
            return result
        self.network.scan = other_network
        self.command('select', id='demo')
        self.assertFalse(self.controller.affected)
        self.assertEqual(self.controller.snapshot()['policy']['mode'], 'manual')
        self.assertEqual(self.controller.snapshot()['policy']['entries'], [])
        self.command('mode', mode='allowlist')
        self.network.scan = original
        self.command('select', id='demo')
        wait_for(lambda: len(self.controller.affected) == 3)
        self.assertTrue(self.controller.device(self.mac)['allowed'])

    def test_corrupt_file_is_reported_and_preserved(self):
        self.controller.close()
        path = Path(self.directory.name) / 'access.json'
        path.write_text('{invalid', encoding='utf-8')
        self.controller = Controller(self.network, self.directory.name, demo=True)
        wait_for(lambda: self.controller.snapshot()['error'])
        self.command('mode', mode='allowlist')
        self.assertFalse(self.controller.affected)
        self.assertEqual(path.read_text(encoding='utf-8'), '{invalid')


class PolicyFormatTests(unittest.TestCase):
    def test_mac_validation_and_private_addresses(self):
        self.assertEqual(normalize_mac(' 02-11-22-33-44-66 '), '02:11:22:33:44:66')
        for value in ['AA:BB-CC:DD:EE:02', 'aabbccddee02', None]:
            with self.assertRaises(ValueError):
                normalize_mac(value)

    def test_invalid_schema_is_rejected_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'access.json'
            for value in [[], {'version': 2, 'networks': {}}, {'version': 1, 'networks': {'invalid': {}}}]:
                path.write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaises(RuntimeError):
                    AccessStore(path).load('02:00:00:00:00:01')


if __name__ == '__main__':
    unittest.main()
