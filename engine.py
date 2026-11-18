from i18n import message, error_message
import copy
import ipaddress
import json
import logging
import queue
import socket
import threading
import time
from pathlib import Path
from access import AccessStore, empty_policy, normalize_mac
from vendors import manufacturer


def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


class Controller:
    """A single worker owns all network mutations, including shutdown restoration."""
    def __init__(self, network, data_dir, demo=False):
        self.network = network
        self.demo = demo
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.alias_path = self.data_dir / 'names.json'
        self.journal_path = self.data_dir / 'recovery.json'
        self.aliases = self.read_json(self.alias_path, {})
        self.access_store = AccessStore(self.data_dir / 'access.json')
        self.policy = empty_policy()
        self.policy_loaded = False
        self.policy_paused = False
        self.affected = set()
        self.context = None
        self.lock = threading.RLock()
        self.commands = queue.Queue()
        self.names = queue.Queue()
        self.stopping = threading.Event()
        self.last_heartbeat = time.monotonic()
        self.next_send = 0
        self.last_attempt = {}
        self.state = dict(version='4.1', ready=False, demo=demo, scanning=False, busy=False, closing=False,
                          interfaces=[], context=None, devices=[], events=[], error='',
                          problem='', can_block=False, last_scan=None, scan_mode='manual',
                          policy=dict(mode='manual', paused=False, entries=[]))
        self.worker = threading.Thread(target=self.run, name='network-worker', daemon=True)
        self.worker.start()
        for _ in range(3):
            threading.Thread(target=self.resolve_names, daemon=True).start()

    @staticmethod
    def read_json(path, default):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return default
        except (OSError, ValueError):
            logging.exception('Could not read %s', path)
            return default

    def event(self, text):
        with self.lock:
            self.state['events'].insert(0, dict(time=time.time(), text=text))
            del self.state['events'][60:]

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def heartbeat(self):
        self.last_heartbeat = time.monotonic()

    def submit(self, action, body):
        with self.lock:
            if self.state['closing']:
                raise ValueError(message('err_closing'))
            if self.state['busy'] or self.state['scanning']:
                raise ValueError(message('err_busy'))
            self.state['busy'] = True
        self.commands.put((action, body))

    def run(self):
        try:
            interfaces = self.network.interfaces()
            with self.lock:
                self.state.update(ready=True, interfaces=interfaces, can_block=self.network.can_block,
                                  problem=self.network.problem)
            if interfaces:
                try:
                    self.select(interfaces[0]['id'])
                except Exception as error:
                    self.fail(error)
            else:
                raise RuntimeError(message('err_connect_network'))
            while not self.stopping.is_set():
                try:
                    action, body = self.commands.get(timeout=0.25)
                except queue.Empty:
                    action, body = None, {}
                try:
                    if action:
                        self.handle(action, body)
                    # Discovery scans are explicit. Enforcement and passive neighbor
                    # observation continue even when the browser is closed or asleep.
                    if time.monotonic() >= self.next_send and not self.stopping.is_set():
                        self.next_send = time.monotonic() + 2
                        self.enforce()
                except ValueError as error:
                    with self.lock:
                        self.state['error'] = error_message(error)
                    self.event(error_message(error))
                except Exception as error:
                    self.fail(error)
                finally:
                    with self.lock:
                        self.state['busy'] = False
        except Exception as error:
            self.fail(error)
        finally:
            try:
                self.release_all()
            except Exception as error:
                self.fail(error, restore=False)
            self.network.close()

    def handle(self, action, body):
        with self.lock:
            self.state['error'] = ''
        if action == 'scan':
            self.refresh()
        elif action == 'select':
            self.select(body['id'])
        elif action == 'rename':
            self.rename(body['mac'], body['name'])
        elif action == 'block':
            self.block(body['mac'], body['blocked'])
        elif action == 'mode':
            self.set_mode(body['mode'])
        elif action == 'allow':
            self.allow(body['mac'], body['allowed'], body.get('name'))
        elif action == 'resume':
            self.resume_policy()
        elif action == 'release':
            self.release_all()
            self.event(message('event_released'))
        else:
            raise ValueError(message('err_unknown_action'))

    def fail(self, error, restore=True):
        logging.exception('Network operation failed')
        problem_message = error_message(error)
        if restore:
            try:
                self.release_all()
            except Exception as restoration_error:
                problem_message = message('err_restore', error=problem_message, detail=error_message(restoration_error))
        with self.lock:
            self.state.update(error=problem_message, scanning=False, busy=False,
                              can_block=self.network.can_block, problem=self.network.problem)
        self.event(problem_message)

    def select(self, interface_id):
        context = next((item.copy() for item in self.state['interfaces'] if item['id'] == interface_id), None)
        if context is None:
            raise ValueError(message('err_unknown_adapter'))
        self.release_all()
        self.context = context
        self.policy = empty_policy()
        self.policy_loaded = False
        self.policy_paused = False
        with self.lock:
            self.state.update(context=context.copy(), devices=[], last_scan=None, error='')
            self.sync_policy()
        self.refresh()
        journal = self.read_json(self.journal_path, {})
        saved_context = journal.get('context', {})
        keys = ('id', 'router_mac', 'mac', 'subnet')
        if journal.get('targets') and all(saved_context.get(k) == self.context.get(k) for k in keys):
            self.affected = {tuple(item) for item in journal['targets']}
            self.context['routers_v6'] = sorted(set(self.context.get('routers_v6', [])) | set(saved_context.get('routers_v6', [])))
            self.restore(self.affected.copy())
            self.event(message('event_recovered'))

    def refresh(self):
        if self.context is None:
            return
        with self.lock:
            self.state['scanning'] = True
        try:
            online = self.network.scan(self.context)
            router_mac = online.get(self.context['gateway'])
            if not router_mac:
                raise RuntimeError(message('err_router_no_response'))
            if self.context.get('router_mac', router_mac) != router_mac:
                raise RuntimeError(message('err_gateway_changed'))
            self.context['router_mac'] = router_mac
            if not self.policy_loaded:
                self.policy = self.access_store.load(router_mac)
                self.policy_loaded = True
                self.policy_paused = not self.network.can_block
            online.update(self.network.discovered_neighbors(self.context))
            self.context['owners'] = dict(online)
            now = time.time()
            self.merge_devices(online, full_scan=True)
            with self.lock:
                self.state.update(context=copy.deepcopy(self.context), last_scan=now, error='',
                                  can_block=self.network.can_block, problem=self.network.problem)
        finally:
            with self.lock:
                self.state['scanning'] = False

    def merge_devices(self, observed, full_scan=False):
        """Learn new MACs between scans and discard addresses reassigned by DHCP."""
        now = time.time()
        address_order = lambda ip: (ipaddress.ip_address(ip).version, int(ipaddress.ip_address(ip)))
        with self.lock:
            previous = {d['mac']: d for d in self.state['devices']}
            by_mac = {}
            for ip, mac in observed.items():
                by_mac.setdefault(mac, set()).add(ip)
            for mac, device in previous.items():
                if full_scan:
                    device['online'] = False
                device['addresses'] = [ip for ip in device.get('addresses', [device['ip']])
                                       if observed.get(ip, mac) == mac]
                if not device['addresses']:
                    device['online'] = False
                else:
                    device['ip'] = sorted(device['addresses'], key=address_order)[0]
            for mac, latest in by_mac.items():
                device = previous.get(mac, dict(mac=mac, hostname='', blocked=False, addresses=[]))
                addresses = latest if full_scan else latest | set(device['addresses'])
                addresses = sorted(addresses, key=address_order)
                protected = mac in {self.context['router_mac'], self.context['mac']} or any(
                    ip in {self.context['ip'], self.context['gateway']} for ip in addresses)
                device.update(ip=addresses[0], addresses=addresses, online=True, last_seen=now, protected=protected)
                device['manufacturer'] = manufacturer(mac)
                device['role'] = 'Router' if mac == self.context['router_mac'] else ('Este PC' if mac == self.context['mac'] else '')
                device['alias'] = self.aliases.get(self.alias_key(mac), self.policy['allowed'].get(mac, ''))
                previous[mac] = device
                if not device['hostname'] and now - self.last_attempt.get(mac, 0) > 120:
                    self.last_attempt[mac] = now
                    self.names.put((self.context['id'], device['ip'], mac))
            self.state['devices'] = sorted(previous.values(), key=lambda d: (not d['protected'], address_order(d['ip'])))
            self.sync_policy()

    def sync_policy(self):
        with self.lock:
            devices = {d['mac']: d for d in self.state['devices']}
            for device in devices.values():
                device['allowed'] = device['protected'] or device['mac'] in self.policy['allowed']
                if device['protected']:
                    device['blocked'] = False
                elif self.policy['mode'] == 'allowlist':
                    device['blocked'] = not self.policy_paused and not device['allowed']
            entries = []
            for mac, label in sorted(self.policy['allowed'].items()):
                device = devices.get(mac, {})
                alias = self.aliases.get(self.alias_key(mac), label) if self.context else label
                entries.append(dict(mac=mac, name=alias or device.get('hostname', ''),
                                    manufacturer=manufacturer(mac), online=device.get('online', False)))
            self.state['policy'] = dict(mode=self.policy['mode'], paused=self.policy_paused, entries=entries)

    def require_policy(self):
        if not self.context or not self.policy_loaded:
            raise ValueError(message('err_scan_before_policy'))

    def require_blocking(self):
        self.require_policy()
        if not self.network.can_block:
            raise ValueError(self.network.problem or message('err_blocking_unavailable'))

    def set_mode(self, mode):
        self.require_policy()
        if mode not in {'manual', 'allowlist'}:
            raise ValueError(message('err_invalid_mode'))
        if mode == 'allowlist':
            self.require_blocking()
        updated = copy.deepcopy(self.policy)
        updated['mode'] = mode
        self.access_store.save(self.context['router_mac'], updated)
        self.release_all()
        self.policy = updated
        self.policy_paused = False
        self.sync_policy()
        self.enforce()
        self.event(message('event_allowlist') if mode == 'allowlist'
                   else message('event_manual'))

    def allow(self, mac, allowed, name=None):
        self.require_policy()
        mac = normalize_mac(mac)
        if type(allowed) is not bool or (name is not None and (not isinstance(name, str) or len(name.strip()) > 60)):
            raise ValueError(message('err_invalid_permission'))
        if mac in {self.context['mac'], self.context['router_mac']} or any(d['mac'] == mac and d['protected'] for d in self.state['devices']):
            raise ValueError(message('err_auto_allowed'))
        updated = copy.deepcopy(self.policy)
        if allowed:
            updated['allowed'][mac] = name.strip() if name is not None else updated['allowed'].get(mac, '')
        else:
            updated['allowed'].pop(mac, None)
        self.access_store.save(self.context['router_mac'], updated)
        self.policy = updated
        with self.lock:
            for device in self.state['devices']:
                if device['mac'] == mac:
                    device['alias'] = self.aliases.get(self.alias_key(mac), self.policy['allowed'].get(mac, ''))
        self.sync_policy()
        self.enforce()
        self.event(message('event_allowed' if allowed else 'event_revoked', mac=mac))

    def resume_policy(self):
        self.require_blocking()
        if self.policy['mode'] != 'allowlist':
            raise ValueError(message('err_enable_allowlist'))
        self.policy_paused = False
        self.sync_policy()
        self.enforce()
        self.event(message('event_resumed'))

    def alias_key(self, mac):
        return f"{self.context['router_mac']}|{mac}"

    def device(self, mac):
        result = next((d for d in self.state['devices'] if d['mac'] == mac), None)
        if result is None:
            raise ValueError(message('err_device_missing'))
        return result

    def rename(self, mac, name):
        if not isinstance(name, str) or len(name.strip()) > 60:
            raise ValueError(message('err_name_length'))
        with self.lock:
            device = self.device(mac)
            new_aliases = dict(self.aliases)
            new_aliases[self.alias_key(mac)] = name.strip()
            save_json(self.alias_path, new_aliases)
            self.aliases = new_aliases
            device['alias'] = name.strip()
            self.sync_policy()
            self.event(message('event_renamed'))

    def block(self, mac, blocked):
        if type(blocked) is not bool:
            raise ValueError(message('err_invalid_block'))
        if self.policy['mode'] == 'allowlist':
            self.allow(mac, not blocked)
            return
        with self.lock:
            device = self.device(mac)
            if device['protected']:
                raise ValueError(message('err_protected'))
            if blocked and (not device['online'] or not self.network.can_block):
                raise ValueError(self.network.problem or message('err_locate_device'))
            if blocked and ':' in device['ip'] and not self.context.get('routers_v6'):
                raise ValueError(message('err_ipv6_gateway'))
            device['blocked'] = blocked
            name = device['alias'] or device['hostname'] or device['ip']
        self.enforce()
        self.event(message('event_blocked' if blocked else 'event_restored', name=name))

    def journal(self):
        save_json(self.journal_path, dict(context=self.context, targets=sorted(self.affected)))

    def restore(self, targets):
        if not targets:
            return
        self.network.mapping(self.context, targets, restore=True)
        self.affected.difference_update(targets)
        self.journal()

    def enforce(self):
        if self.context is None:
            return
        observed = self.network.discovered_neighbors(self.context)
        if not self.policy_loaded:
            return
        self.merge_devices(observed)
        with self.lock:
            self.context.setdefault('owners', {}).update(observed)
            targets = {(ip, d['mac']) for d in self.state['devices']
                       if d['blocked'] and not d['protected']
                       for ip in d.get('addresses', [d['ip']])
                       if ':' not in ip or self.context.get('routers_v6')}
            self.state['context'] = copy.deepcopy(self.context)
        self.restore(self.affected - targets)
        if targets:
            self.affected.update(targets)
            self.journal()  # Write recovery information before changing any neighbor mapping.
            self.network.mapping(self.context, targets)

    def release_all(self):
        with self.lock:
            self.policy_paused = True
            for device in self.state['devices']:
                device['blocked'] = False
            self.sync_policy()
        self.restore(self.affected.copy())

    def resolve_names(self):
        while not self.stopping.is_set():
            try:
                network_id, ip, mac = self.names.get(timeout=1)
            except queue.Empty:
                continue
            try:
                name = self.network.name(ip) if self.demo else socket.gethostbyaddr(ip)[0]
                with self.lock:
                    if self.context and self.context['id'] == network_id:
                        device = self.device(mac)
                        if device['ip'] == ip:
                            device['hostname'] = name if self.demo else name[:120]
            except (OSError, ValueError):
                pass

    def close(self):
        with self.lock:
            self.state['closing'] = True
        self.stopping.set()
        self.worker.join(timeout=50)
        return not self.worker.is_alive() and not self.affected
