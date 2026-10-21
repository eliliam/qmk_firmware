"""An in-memory stand-in for the A+ firmware's VIA raw HID handling, matching
quantum/via.c and keymaps/eli/settings.c."""

from ploopy_tools.catalog import Catalog

MARKER_ID = 254


class FakeMouse:
    def __init__(self, catalog: Catalog, layers: int = 8):
        self.catalog = catalog
        self.keymap = [[0x0001] * 8 for _ in range(layers)]
        self.values = {(s.channel, s.id): s.encode(s.default) for s in catalog.settings}
        self.saved = dict(self.values)
        self.marker = False
        self.saves: list[int] = []
        self.writes = 0
        self.packets: list[bytes] = []
        self.pending: list[bytes] = []  # input reports waiting to be read
        self.noise: list[bytes] = []  # reports another program's commands produce on the next write

    def drain(self) -> None:
        self.pending.clear()

    def write(self, packet: bytes) -> None:
        self.pending.extend(self.noise)
        self.noise = []
        self.pending.append(self.exchange(packet))

    def read(self) -> bytes | None:
        return self.pending.pop(0) if self.pending else None

    def _setting(self, channel: int, vid: int):
        for s in self.catalog.settings:
            if s.channel == channel and s.id == vid:
                return s
        return None

    def exchange(self, packet: bytes) -> bytes:
        assert len(packet) == 32
        self.packets.append(packet)
        r = bytearray(packet)
        cmd = packet[0]
        if cmd == 0x01:
            r[1:3] = (13).to_bytes(2, "big")
        elif cmd == 0x11:
            r[1] = len(self.keymap)
        elif cmd == 0x04:
            layer, _row, col = packet[1:4]
            r[4:6] = self.keymap[layer][col].to_bytes(2, "big")
        elif cmd == 0x05:
            layer, _row, col = packet[1:4]
            self.keymap[layer][col] = int.from_bytes(packet[4:6], "big")
            self.writes += 1
        elif cmd in (0x07, 0x08, 0x09):
            channel, vid = packet[1], packet[2]
            if cmd == 0x09 and channel in (24, self.catalog.channel):
                self.saved = dict(self.values)
                self.saves.append(channel)
            elif channel == self.catalog.channel and vid == MARKER_ID:
                if cmd == 0x07:
                    self.marker = True
                    self.writes += 1
                else:
                    r[3] = int(self.marker)
            else:
                s = self._setting(channel, vid)
                if s is None:
                    r[0] = 0xFF
                elif cmd == 0x07:
                    self.values[(channel, vid)] = bytes(packet[3 : 3 + s.size])
                    self.writes += 1
                else:
                    r[3 : 3 + s.size] = self.values[(channel, vid)]
        else:
            r[0] = 0xFF
        return bytes(r)
