import pytest

from ploopy_tools.catalog import CATALOG_PATH, load_catalog
from ploopy_tools.keycodes import Codec, KeycodeError


@pytest.fixture(scope="module")
def codec():
    return Codec.load(load_catalog(CATALOG_PATH))


@pytest.mark.parametrize(
    "name,code",
    [
        ("MS_BTN1", 0x00D1),
        ("KC_TRNS", 0x0001),
        ("KC_ESC", 0x0029),
        ("HYPR(KC_LEFT)", 0x0F50),
        ("MEH(KC_SPC)", 0x072C),
        ("LCTL(KC_A)", 0x0104),
        ("RSFT(KC_A)", 0x1204),
        ("TG(1)", 0x5261),
        ("MO(2)", 0x5222),
        ("TO(3)", 0x5203),
        ("LT(1,KC_A)", 0x4104),
        ("QK_BOOT", 0x7C00),
        ("PKC_NIRI", 0x7E04),
        ("PKC_BOTTOM_RIGHT", 0x7E08),
        ("MA_TOGG", 0x77C0),
        ("MA_LMT", 0x77C4),
        ("DPI_CONFIG", 0x7E00),
        ("DRAG_SCROLL", 0x7E01),
        ("0x7FFF", 0x7FFF),
    ],
)
def test_roundtrip(codec, name, code):
    assert codec.encode(name) == code
    assert codec.decode(code) == name


@pytest.mark.parametrize(
    "alias,code",
    [("_______", 0x0001), ("KC_TRANSPARENT", 0x0001), ("KC_ESCAPE", 0x0029), ("QK_BOOTLOADER", 0x7C00), ("hypr(kc_left)", 0x0F50), ("LT(1, KC_A)", 0x4104)],
)
def test_aliases_encode(codec, alias, code):
    assert codec.encode(alias) == code


def test_unknown_name_raises(codec):
    with pytest.raises(KeycodeError, match="KC_NOPE"):
        codec.encode("KC_NOPE")


def test_bad_function_arg_raises(codec):
    with pytest.raises(KeycodeError, match="TG"):
        codec.encode("TG(99)")
