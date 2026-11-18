# Third-party components

## Wireshark manufacturer registry

data/manuf.gz was downloaded from the [official Wireshark generated registry](https://www.wireshark.org/download/automated/data/manuf.gz) on 2026-11-17. It contains MAC allocation names and retains its original header, including the generating TShark version and canonical source URL. Manufacturer names are shown verbatim.

## Npcap

Npcap is an external prerequisite and is not redistributed in the source package or Windows executable. Users obtain it from [npcap.com](https://npcap.com/#download), under the terms provided by its publisher.

## Python and PyInstaller

The source runs on Python's standard library. Windows builds embed the Python runtime using PyInstaller. Their respective terms continue to apply to those components. Build requirements are separate from application requirements.

Scapy is not used by this version and is not included in the prepared source package.
