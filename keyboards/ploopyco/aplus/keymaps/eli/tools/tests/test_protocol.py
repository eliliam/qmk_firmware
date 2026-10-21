import pytest

from fake_mouse import FakeMouse
from ploopy_tools.catalog import CATALOG_PATH, load_catalog
from ploopy_tools.protocol import POSITIONS, Mouse, MouseError


@pytest.fixture(scope="module")
def cat():
    return load_catalog(CATALOG_PATH)


@pytest.fixture
def fake(cat):
    return FakeMouse(cat)


@pytest.fixture
def mouse(fake):
    return Mouse(fake)


def test_version(mouse):
    assert mouse.protocol_version() == 13


def test_layer_count(mouse):
    assert mouse.layer_count() == 8


def test_keycode_roundtrip(mouse, fake):
    mouse.set_keycode(1, POSITIONS["BL"], 0x7C00)
    assert fake.keymap[1][0] == 0x7C00
    assert mouse.get_keycode(1, POSITIONS["BL"]) == 0x7C00


def test_positions_match_layout():
    assert POSITIONS == {"TLL": 1, "TL": 2, "TR": 3, "TRR": 4, "BL": 0, "BR": 5, "LW": 6, "RW": 7}


@pytest.mark.parametrize(
    "name,value",
    [
        ("niri.flick_threshold", 240),
        ("drag_scroll.divisor_v", 0.3),
        ("wheels.vertical_arrows", True),
        ("bottom_right.mode", "drag_scroll"),
        ("accel.takeoff", 1.5),
    ],
)
def test_setting_roundtrip_each_type(mouse, cat, name, value):
    s = cat.setting(name)
    mouse.set_setting(s, value)
    assert mouse.get_setting(s) == value


def test_save_sends_channel(mouse, fake):
    mouse.save(42)
    mouse.save(24)
    assert fake.saves == [42, 24]


def test_unhandled_raises(mouse, cat):
    from dataclasses import replace

    bogus = replace(cat.setting("niri.flick_threshold"), id=99)
    with pytest.raises(MouseError, match="unhandled"):
        mouse.get_setting(bogus)


def test_marker_invalid_on_fresh_store(mouse):
    assert mouse.marker_valid() is False
    mouse.set_marker()
    assert mouse.marker_valid() is True


def test_packets_are_32_bytes(mouse, fake):
    mouse.protocol_version()
    mouse.get_keycode(0, 0)
    assert all(len(p) == 32 for p in fake.packets)


def test_echo_mismatch_raises(cat):
    class Garbled:
        def __init__(self):
            self.queue = []

        def drain(self):
            pass

        def write(self, packet):
            self.queue.append(bytes([0x42]) + packet[1:])

        def read(self):
            return self.queue.pop(0) if self.queue else None

    with pytest.raises(MouseError, match="no reply"):
        Mouse(Garbled()).protocol_version()


def test_skips_replies_meant_for_another_program(mouse, fake):
    # hidraw copies every reply to every open handle, so VIA's replies can
    # arrive before ours while it is connected.
    fake.noise = [bytes([0x01, 0x00, 0x0D]).ljust(32, b"\x00"), bytes([0x08, 42, 1, 0, 200]).ljust(32, b"\x00")]
    fake.keymap[0][6] = 0x7E04
    assert mouse.get_keycode(0, 6) == 0x7E04


def test_drains_stale_input_before_sending(mouse, fake):
    fake.pending.append(bytes([0x04, 0, 0, 6, 0x12, 0x34]).ljust(32, b"\x00"))
    fake.keymap[0][6] = 0x7E04
    assert mouse.get_keycode(0, 6) == 0x7E04


def test_unhandled_still_detected_through_noise(mouse, fake, cat):
    from dataclasses import replace

    fake.noise = [bytes([0x02, 0x06]).ljust(32, b"\x00")]
    with pytest.raises(MouseError, match="unhandled"):
        mouse.get_setting(replace(cat.setting("niri.flick_threshold"), id=99))


def test_no_matching_reply_times_out(cat):
    class Silent:
        def drain(self):
            pass

        def write(self, packet):
            pass

        def read(self):
            return None

    with pytest.raises(MouseError, match="no reply"):
        Mouse(Silent()).protocol_version()
