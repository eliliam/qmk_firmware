import pytest

from fake_mouse import FakeMouse
from ploopy_tools.catalog import CATALOG_PATH, load_catalog
from ploopy_tools.keycodes import Codec
from ploopy_tools.mouseconfig import ConfigError, diff, load_config, read_state, save_config, write_state
from ploopy_tools.protocol import POSITIONS, Mouse

CONFIG = """\
# Eli's mouse
[settings.niri]
flick_threshold = 200 # counts per step
tap_term = 250
idle_reset = 200

[settings.drag_scroll]
divisor_h = 0.8
divisor_v = 0.24

[settings.wheels]
vertical_arrows = false
horizontal_arrows = false

[settings.bottom_right]
mode = "middle_click"

[settings.led]
brightness = 4

[settings.pointer]
dpi = 900

[settings.accel]
enabled = true
takeoff = 2.0
growth_rate = 0.25
offset = 2.2
limit = 0.2

[layers.0]
TLL = "MS_BTN4"
TL = "MS_BTN5"
TR = "MEH(KC_SPC)"
TRR = "MS_BTN2"
BL = "MS_BTN1"
BR = "PKC_BOTTOM_RIGHT"
LW = "PKC_NIRI"
RW = "TG(1)"

[layers.1]
BL = "QK_BOOT"
"""


@pytest.fixture(scope="module")
def cat():
    return load_catalog(CATALOG_PATH)


@pytest.fixture(scope="module")
def codec(cat):
    return Codec.load(cat)


@pytest.fixture
def config_path(tmp_path):
    p = tmp_path / "mouse.toml"
    p.write_text(CONFIG)
    return p


@pytest.fixture
def fake(cat):
    return FakeMouse(cat)


def test_load_config(config_path, cat, codec):
    state = load_config(config_path, cat, codec)
    assert state.settings["pointer.dpi"] == 900
    assert state.layers[0]["LW"] == "PKC_NIRI"
    assert state.layers[1]["BL"] == "QK_BOOT"
    assert state.layers[1]["TL"] == "KC_TRNS"
    assert state.layers[7]["RW"] == "KC_TRNS"


def test_read_state_names(fake, cat, codec):
    fake.keymap[0][POSITIONS["BR"]] = 0x7E08
    state = read_state(Mouse(fake), cat, codec)
    assert state.layers[0]["BR"] == "PKC_BOTTOM_RIGHT"
    assert state.settings["niri.flick_threshold"] == 200


def test_diff_lists_drift(fake, config_path, cat, codec):
    mouse = Mouse(fake)
    target = load_config(config_path, cat, codec)
    write_state(mouse, target, read_state(mouse, cat, codec), cat, codec)
    mouse.set_setting(cat.setting("pointer.dpi"), 1600)
    mouse.set_keycode(0, POSITIONS["TR"], 0x00D3)
    found = {d.path: d for d in diff(read_state(mouse, cat, codec), target)}
    assert set(found) == {"settings.pointer.dpi", "layers.0.TR"}
    assert (found["settings.pointer.dpi"].mouse, found["settings.pointer.dpi"].config) == ("1600", "900")
    assert found["layers.0.TR"].config == "MEH(KC_SPC)"


def test_apply_writes_only_changes(fake, config_path, cat, codec):
    mouse = Mouse(fake)
    target = load_config(config_path, cat, codec)
    first = write_state(mouse, target, read_state(mouse, cat, codec), cat, codec)
    assert first == 9  # 8 layer-0 keys + layer-1 BL; settings already at defaults
    assert fake.saves == []
    assert write_state(mouse, target, read_state(mouse, cat, codec), cat, codec) == 0


def test_write_state_saves_touched_channels(fake, config_path, cat, codec):
    mouse = Mouse(fake)
    target = load_config(config_path, cat, codec)
    target.settings["pointer.dpi"] = 1200
    target.settings["accel.takeoff"] = 1.0
    write_state(mouse, target, read_state(mouse, cat, codec), cat, codec)
    assert sorted(fake.saves) == [24, 42]
    assert fake.saved[(42, 10)] == (1200).to_bytes(2, "big")


def test_accel_rounding_is_not_drift(fake, config_path, cat, codec):
    mouse = Mouse(fake)
    target = load_config(config_path, cat, codec)
    write_state(mouse, target, read_state(mouse, cat, codec), cat, codec)
    target.settings["accel.offset"] = 2.2001  # within one 0..60000 step of 2.2
    assert diff(read_state(mouse, cat, codec), target) == []


@pytest.mark.parametrize(
    "edit,path",
    [
        (("[settings.pointer]\ndpi = 900", "[settings.pointer]\ndpi = 900\nspeed = 3"), "settings.pointer.speed"),
        (("dpi = 900", "dpi = 50"), "settings.pointer.dpi"),
        (('BL = "QK_BOOT"', 'BL = "KC_NOPE"'), "layers.1.BL"),
        (('[layers.1]\nBL = "QK_BOOT"', '[layers.1]\nXX = "QK_BOOT"'), "layers.1.XX"),
        (("[layers.1]", "[layers.9]"), "layers.9"),
        (("tap_term = 250\n", ""), "settings.niri.tap_term"),
    ],
)
def test_invalid_config_raises_with_path(config_path, cat, codec, edit, path):
    config_path.write_text(CONFIG.replace(*edit))
    with pytest.raises(ConfigError, match=path.replace(".", r"\.")):
        load_config(config_path, cat, codec)


def test_save_config_keeps_comments(config_path, cat, codec):
    state = load_config(config_path, cat, codec)
    state.settings["niri.flick_threshold"] = 240
    state.layers[1]["BL"] = "KC_TRNS"
    save_config(config_path, state, cat)
    text = config_path.read_text()
    assert "# Eli's mouse" in text
    assert "flick_threshold = 240 # counts per step" in text
    assert "[layers.1]" not in text
    assert load_config(config_path, cat, codec).settings["niri.flick_threshold"] == 240


def test_firmware_truncation_is_not_drift(fake, config_path, cat, codec):
    # The accel module truncates float -> 0..60000, so 0.25 reads back as raw
    # 2885 while 0.25 encodes to 2886.
    mouse = Mouse(fake)
    target = load_config(config_path, cat, codec)
    write_state(mouse, target, read_state(mouse, cat, codec), cat, codec)
    fake.values[(24, 2)] = (2885).to_bytes(2, "big")
    assert diff(read_state(mouse, cat, codec), target, cat) == []
    assert write_state(mouse, target, read_state(mouse, cat, codec), cat, codec) == 0


def test_growth_rate_033_is_not_drift_after_truncation(fake, config_path, cat, codec):
    # Review finding: 0.33 encodes to 3848, the firmware reads back 3847.
    mouse = Mouse(fake)
    config_path.write_text(CONFIG.replace("growth_rate = 0.25", "growth_rate = 0.33"))
    target = load_config(config_path, cat, codec)
    write_state(mouse, target, read_state(mouse, cat, codec), cat, codec)
    fake.values[(24, 2)] = (3847).to_bytes(2, "big")
    pulled = read_state(mouse, cat, codec)
    assert diff(pulled, target, cat) == []
    fake.values[(24, 2)] = (int.from_bytes(cat.setting("accel.growth_rate").encode(pulled.settings["accel.growth_rate"]), "big") - 1).to_bytes(2, "big")
    assert diff(read_state(mouse, cat, codec), pulled, cat) == []


@pytest.mark.parametrize(
    "text,path",
    [
        (CONFIG.replace("dpi = 900", "dpi = 900\ndpi = 900"), "dpi"),
        (CONFIG.replace("[layers.1]\nBL = \"QK_BOOT\"", "[layers]\n1 = \"KC_A\""), "layers.1"),
        ("layers = []\n" + CONFIG.split("[layers.0]")[0], "layers"),
        ("settings = 3\n", "settings"),
        (CONFIG.replace("[settings.led]", "[settings.led\n"), "mouse.toml"),
    ],
)
def test_malformed_config_raises_config_error(config_path, cat, codec, text, path):
    config_path.write_text(text)
    with pytest.raises(ConfigError, match=path):
        load_config(config_path, cat, codec)


def test_save_config_on_broken_file_raises_config_error(config_path, cat, codec):
    state = load_config(config_path, cat, codec)
    config_path.write_text("[settings.led\n")
    with pytest.raises(ConfigError, match="mouse.toml"):
        save_config(config_path, state, cat)
