"""Persistent access policy, keyed by the router's MAC rather than its IP."""
from i18n import message
import copy
import json
import re


def normalize_mac(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{2}([:-])[0-9a-fA-F]{2}(?:\1[0-9a-fA-F]{2}){4}', value.strip()):
        raise ValueError(message('err_mac_format'))
    mac = value.strip().lower().replace('-', ':')
    if int(mac[:2], 16) & 1 or mac == '00:00:00:00:00:00':
        raise ValueError(message('err_mac_individual'))
    return mac


def empty_policy():
    return dict(mode='manual', allowed={})


class AccessStore:
    def __init__(self, path):
        self.path = path
        self.data = None

    def load(self, router_mac):
        if self.data is None:
            try:
                value = json.loads(self.path.read_text(encoding='utf-8'))
            except FileNotFoundError:
                value = dict(version=1, networks={})
            except (OSError, ValueError) as error:
                raise RuntimeError(message('err_policy_read')) from error
            try:
                if value['version'] != 1 or not isinstance(value['networks'], dict):
                    raise ValueError('Invalid policy file')
                for router, policy in value['networks'].items():
                    if normalize_mac(router) != router or policy['mode'] not in {'manual', 'allowlist'} or not isinstance(policy['allowed'], dict):
                        raise ValueError('Invalid network policy')
                    for mac, name in policy['allowed'].items():
                        if normalize_mac(mac) != mac or not isinstance(name, str) or len(name) > 60:
                            raise ValueError('Invalid allowed device')
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError(message('err_policy_invalid')) from error
            self.data = value
        return copy.deepcopy(self.data['networks'].get(router_mac, empty_policy()))

    def save(self, router_mac, policy):
        self.load(router_mac)
        updated = copy.deepcopy(self.data)
        updated['networks'][router_mac] = copy.deepcopy(policy)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(updated, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.path)
        self.data = updated
