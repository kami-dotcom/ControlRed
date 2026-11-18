"""Small binding to the installed Npcap driver, pinned to a Windows adapter GUID."""
from i18n import message
import ctypes as c
import os
from pathlib import Path


class PacketHeader(c.Structure):
    # Windows timeval uses two 32-bit longs, including in 64-bit processes.
    _fields_ = [('seconds', c.c_int32), ('microseconds', c.c_int32),
                ('captured', c.c_uint32), ('length', c.c_uint32)]


class FilterProgram(c.Structure):
    _fields_ = [('length', c.c_uint), ('instructions', c.c_void_p)]


class Npcap:
    def __init__(self):
        folder = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/Npcap'
        if not (folder / 'wpcap.dll').exists():
            raise OSError(message('err_install_npcap'))
        self.directory = os.add_dll_directory(str(folder))
        self.dll = c.CDLL(str(folder / 'wpcap.dll'))
        signatures = {
            'pcap_open_live': ([c.c_char_p, c.c_int, c.c_int, c.c_int, c.c_char_p], c.c_void_p),
            'pcap_close': ([c.c_void_p], None),
            'pcap_datalink': ([c.c_void_p], c.c_int),
            'pcap_setnonblock': ([c.c_void_p, c.c_int, c.c_char_p], c.c_int),
            'pcap_sendpacket': ([c.c_void_p, c.c_char_p, c.c_int], c.c_int),
            'pcap_next_ex': ([c.c_void_p, c.POINTER(c.POINTER(PacketHeader)), c.POINTER(c.c_void_p)], c.c_int),
            'pcap_geterr': ([c.c_void_p], c.c_char_p),
            'pcap_compile': ([c.c_void_p, c.POINTER(FilterProgram), c.c_char_p, c.c_int, c.c_uint32], c.c_int),
            'pcap_setfilter': ([c.c_void_p, c.POINTER(FilterProgram)], c.c_int),
            'pcap_freecode': ([c.POINTER(FilterProgram)], None),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.dll, name)
            function.argtypes = arguments
            function.restype = result
        self.handles = {}

    def open(self, interface):
        if interface in self.handles:
            return self.handles[interface]
        error = c.create_string_buffer(256)
        handle = self.dll.pcap_open_live(interface.encode('ascii'), 2048, 0, 20, error)
        if not handle:
            raise OSError(message('err_open_adapter', detail=error.value.decode(errors='replace')))
        try:
            if self.dll.pcap_datalink(handle) != 1:
                raise OSError(message('err_physical_adapter'))
            if self.dll.pcap_setnonblock(handle, 1, error) != 0:
                raise OSError(error.value.decode(errors='replace'))
            program = FilterProgram()
            if self.dll.pcap_compile(handle, c.byref(program), b'arp or icmp6', 1, 0xffffffff) != 0:
                raise OSError(self.dll.pcap_geterr(handle).decode(errors='replace'))
            try:
                if self.dll.pcap_setfilter(handle, c.byref(program)) != 0:
                    raise OSError(self.dll.pcap_geterr(handle).decode(errors='replace'))
            finally:
                self.dll.pcap_freecode(c.byref(program))
        except Exception:
            self.dll.pcap_close(handle)
            raise
        self.handles[interface] = handle
        return handle

    def send(self, interface, packets):
        handle = self.open(interface)
        for packet in packets:
            if self.dll.pcap_sendpacket(handle, packet, len(packet)) != 0:
                raise OSError(self.dll.pcap_geterr(handle).decode(errors='replace'))

    def read(self, interface, limit=2048):
        handle = self.open(interface)
        header = c.POINTER(PacketHeader)()
        data = c.c_void_p()
        result = []
        for _ in range(limit):
            status = self.dll.pcap_next_ex(handle, c.byref(header), c.byref(data))
            if status == 0:
                break
            if status < 0:
                raise OSError(self.dll.pcap_geterr(handle).decode(errors='replace'))
            length = header.contents.captured
            if 14 <= length <= 2048:
                result.append(c.string_at(data, length))
        return result

    def close(self):
        for handle in self.handles.values():
            self.dll.pcap_close(handle)
        self.handles.clear()
        self.directory.close()
