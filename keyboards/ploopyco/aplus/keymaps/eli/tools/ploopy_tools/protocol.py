"""VIA raw HID protocol: the commands VIA itself uses to read and write the
button map and custom settings (quantum/via.c, keymaps/eli/settings.c)."""

from typing import Protocol

from .catalog import Setting, Value

VENDOR_ID = 0x5043
PRODUCT_ID = 0x81DB
USAGE_PAGE = 0xFF60
USAGE = 0x61
REPORT_SIZE = 32
TIMEOUT_MS = 1000

CMD_PROTOCOL_VERSION = 0x01
CMD_GET_KEYCODE = 0x04
CMD_SET_KEYCODE = 0x05
CMD_CUSTOM_SET = 0x07
CMD_CUSTOM_GET = 0x08
CMD_CUSTOM_SAVE = 0x09
CMD_LAYER_COUNT = 0x11
UNHANDLED = 0xFF
# How many leading request bytes each reply echoes (quantum/via.c). Used to
# tell our replies apart from replies to another program's commands.
ECHO_BYTES = {
    CMD_PROTOCOL_VERSION: 1,
    CMD_GET_KEYCODE: 4,
    CMD_SET_KEYCODE: 6,
    CMD_CUSTOM_SET: 3,
    CMD_CUSTOM_GET: 3,
    CMD_CUSTOM_SAVE: 3,
    CMD_LAYER_COUNT: 1,
}
# Replies to skip before giving up on ours.
MAX_FOREIGN_REPLIES = 16

SETTINGS_CHANNEL = 42
MARKER_ID = 254

# Button position names (LAYOUT() order) to matrix column; the row is 0.
POSITIONS = {"TLL": 1, "TL": 2, "TR": 3, "TRR": 4, "BL": 0, "BR": 5, "LW": 6, "RW": 7}


class MouseError(Exception):
    pass


class NoDeviceError(MouseError):
    pass


class Transport(Protocol):
    """One open raw HID handle. hidraw copies every input report to every
    open handle, so while VIA is connected `read` can return replies to
    VIA's commands too."""

    def drain(self) -> None: ...

    def write(self, packet: bytes) -> None: ...

    def read(self) -> bytes | None: ...


class HidTransport:
    """The A+'s raw HID interface through hidapi's hidraw backend. (The
    module named `hid` is the libusb backend, which can't see usage pages.)"""

    def __init__(self, device):
        self._device = device

    @classmethod
    def open(cls) -> "HidTransport":
        import hidraw

        for info in hidraw.enumerate(VENDOR_ID, PRODUCT_ID):
            if info["usage_page"] == USAGE_PAGE and info["usage"] == USAGE:
                device = hidraw.device()
                try:
                    device.open_path(info["path"])
                except OSError as e:
                    raise NoDeviceError(f"cannot open {info['path'].decode()}: {e} (hidraw permission?)") from e
                return cls(device)
        raise NoDeviceError("Ploopy A+ not found: is it plugged in, and does udev grant hidraw access?")

    def drain(self) -> None:
        # read(n, 0) means "no timeout" (blocks), so drain in non-blocking mode.
        try:
            self._device.set_nonblocking(1)
            while self._device.read(REPORT_SIZE):
                pass
            self._device.set_nonblocking(0)
        except OSError as e:
            raise MouseError(f"USB transfer failed: {e}") from e

    def write(self, packet: bytes) -> None:
        try:
            self._device.write(b"\x00" + packet)
        except OSError as e:
            raise MouseError(f"USB transfer failed: {e}") from e

    def read(self) -> bytes | None:
        try:
            reply = bytes(self._device.read(REPORT_SIZE, TIMEOUT_MS))
        except OSError as e:
            raise MouseError(f"USB transfer failed: {e}") from e
        return reply if len(reply) == REPORT_SIZE else None


class Mouse:
    def __init__(self, transport: Transport):
        self._transport = transport

    def _send(self, *payload: int) -> bytes:
        packet = bytes(payload).ljust(REPORT_SIZE, b"\x00")
        echo = ECHO_BYTES[packet[0]]
        self._transport.drain()
        self._transport.write(packet)
        for _ in range(MAX_FOREIGN_REPLIES):
            reply = self._transport.read()
            if reply is None:
                break
            if reply[1:echo] != packet[1:echo] or reply[0] not in (packet[0], UNHANDLED):
                continue  # a reply to another program's command (e.g. VIA)
            if reply[0] == UNHANDLED:
                raise MouseError(f"unhandled: the mouse rejected command {packet[:3].hex(' ')}")
            return reply
        raise MouseError(f"no reply from the mouse to command {packet[:3].hex(' ')} (timed out)")

    def protocol_version(self) -> int:
        return int.from_bytes(self._send(CMD_PROTOCOL_VERSION)[1:3], "big")

    def layer_count(self) -> int:
        return self._send(CMD_LAYER_COUNT)[1]

    def get_keycode(self, layer: int, col: int) -> int:
        return int.from_bytes(self._send(CMD_GET_KEYCODE, layer, 0, col)[4:6], "big")

    def set_keycode(self, layer: int, col: int, code: int) -> None:
        self._send(CMD_SET_KEYCODE, layer, 0, col, code >> 8, code & 0xFF)

    def get_setting(self, s: Setting) -> Value:
        return s.decode(self._send(CMD_CUSTOM_GET, s.channel, s.id)[3 : 3 + s.size])

    def set_setting(self, s: Setting, value: Value) -> None:
        self._send(CMD_CUSTOM_SET, s.channel, s.id, *s.encode(value))

    def save(self, channel: int) -> None:
        self._send(CMD_CUSTOM_SAVE, channel, 0)

    def marker_valid(self) -> bool:
        return self._send(CMD_CUSTOM_GET, SETTINGS_CHANNEL, MARKER_ID)[3] == 1

    def set_marker(self) -> None:
        self._send(CMD_CUSTOM_SET, SETTINGS_CHANNEL, MARKER_ID, 1)
