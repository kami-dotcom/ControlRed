"""Offline manufacturer lookup using Wireshark's IEEE-derived public registry."""
from i18n import message
import functools
import gzip
import re
from pathlib import Path


@functools.lru_cache(maxsize=1)
def database():
    entries = {}
    source = Path(__file__).resolve().parent / 'data' / 'manuf.gz'
    with gzip.open(source, 'rt', encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('#') or not line.strip():
                continue
            columns = line.rstrip().split('\t')
            if len(columns) < 3:
                continue
            block = columns[0].strip().split('/')
            bits = int(block[1]) if len(block) == 2 else 24
            if bits in {24, 28, 36}:
                prefix = block[0].replace(':', '').upper()[:bits // 4]
                entries[prefix] = columns[2].strip()
    return entries


def manufacturer(mac):
    compact = mac.replace(':', '').replace('-', '').upper()
    if not re.fullmatch('[0-9A-F]{12}', compact):
        return message('vendor_invalid')
    first = int(compact[:2], 16)
    if first & 1:
        return message('vendor_group')
    if first & 2:
        return message('vendor_private')
    registry = database()
    for length in (9, 7, 6):
        if compact[:length] in registry:
            return registry[compact[:length]]
    return message('vendor_unknown')
