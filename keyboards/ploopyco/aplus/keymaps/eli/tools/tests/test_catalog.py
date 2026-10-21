import pytest

from ploopy_tools.catalog import CATALOG_PATH, Keycode, load_catalog


@pytest.fixture(scope="module")
def cat():
    return load_catalog(CATALOG_PATH)


def test_loads_all_settings(cat):
    assert len(cat.settings) == 16
    assert len(cat.keycodes) == 7
    assert cat.setting("pointer.dpi").default == 900
    assert cat.keycodes[2] == Keycode("PKC_NIRI", 0x7E04, cat.keycodes[2].label)


def test_u16_encode_big_endian(cat):
    assert cat.setting("pointer.dpi").encode(900) == bytes([0x03, 0x84])


def test_scale(cat):
    s = cat.setting("drag_scroll.divisor_h")
    assert s.encode(0.8) == bytes([0, 80])
    assert s.decode(bytes([0, 24])) == 0.24


def test_enum(cat):
    s = cat.setting("bottom_right.mode")
    assert s.encode("drag_scroll") == b"\x01"
    assert s.decode(b"\x00") == "middle_click"


def test_bool(cat):
    s = cat.setting("wheels.vertical_arrows")
    assert s.encode(True) == b"\x01"
    assert s.decode(b"\x00") is False


@pytest.mark.parametrize(
    "name,value",
    [
        ("pointer.dpi", 50),
        ("accel.takeoff", 0.4),
        ("bottom_right.mode", "sideways"),
        ("pointer.dpi", True),
        ("wheels.vertical_arrows", 1),
    ],
)
def test_validate_rejects(cat, name, value):
    with pytest.raises(ValueError, match=name):
        cat.setting(name).validate(value)


@pytest.mark.parametrize("value", [0.5, 2.0, 2.2, 0.25, 0.2])
def test_accel_roundtrip_within_one_step(cat, value):
    for s in cat.settings:
        if s.type != "accel" or not (s.min <= value <= s.max):
            continue
        back = s.decode(s.encode(value))
        assert abs(back - value) <= (s.via_max - s.via_min) / 60000
        assert back == round(back, 6)


def test_ids_unique_per_channel(cat):
    seen = {(s.channel, s.id) for s in cat.settings}
    assert len(seen) == len(cat.settings)


def test_store_fits(cat):
    used = 5 + sum(s.size for s in cat.settings if s.channel == cat.channel)
    assert used <= cat.custom_config_size - cat.store_offset


def test_unknown_setting_raises_keyerror(cat):
    with pytest.raises(KeyError):
        cat.setting("nope.nope")


def test_dpi_accepts_values_vias_slider_sets(cat):
    # VIA's range slider has no step; the PMW3360 driver rounds down to 100.
    cat.setting("pointer.dpi").validate(1180)


def test_accel_raw_roundtrip_exact(cat):
    # Decoded values must re-encode to the same slider value, or drift checks
    # stack decode rounding on top of the module's truncation.
    for s in cat.settings:
        if s.type == "accel":
            for raw in range(0, 60001):
                value = s.decode(raw.to_bytes(2, "big"))
                if s.min <= value <= s.max:
                    assert int.from_bytes(s.encode(value), "big") == raw, (s.name, raw)


def test_vertical_direction_setting(cat):
    s = cat.setting("wheels.vertical_direction")
    assert (s.id, s.channel, s.options, s.default) == (11, 42, ("clockwise_up", "clockwise_down"), "clockwise_up")
