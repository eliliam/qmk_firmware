"""Convert between QMK keycode names (as written in keymap.c and the mouse
config) and the 16-bit values VIA reads and writes."""

import json
import re
from pathlib import Path

from .catalog import Catalog

TABLE_PATH = Path(__file__).resolve().parents[1] / "keycodes.json"

# Board keycodes (keyboards/ploopyco/ploopyco.h) and the drashna
# pointing_device_accel module's keycodes, numbered from QK_COMMUNITY_MODULE
# in the order of its qmk_module.json.
EXTRA = {
    "DPI_CONFIG": 0x7E00,
    "DRAG_SCROLL": 0x7E01,
    "MA_TOGG": 0x77C0,
    "MA_TKOF": 0x77C1,
    "MA_GROW": 0x77C2,
    "MA_OFST": 0x77C3,
    "MA_LMT": 0x77C4,
}

# 5-bit modifier field (bits 8-12 of a QK_MODS keycode); bit 4 = right hand.
MODS = {
    "LCTL": 0x01, "LSFT": 0x02, "LALT": 0x04, "LGUI": 0x08,
    "RCTL": 0x11, "RSFT": 0x12, "RALT": 0x14, "RGUI": 0x18,
    "LCS": 0x03, "LCA": 0x05, "LSA": 0x06, "MEH": 0x07,
    "LCG": 0x09, "LSG": 0x0A, "LAG": 0x0C, "LCAG": 0x0D, "HYPR": 0x0F,
}
MOD_NAMES = {v: k for k, v in MODS.items()}

LAYER_FUNCS = {"TO": 0x5200, "MO": 0x5220, "DF": 0x5240, "TG": 0x5260, "OSL": 0x5280, "TT": 0x52C0}
LAYER_FUNC_NAMES = {v: k for k, v in LAYER_FUNCS.items()}
LT_BASE = 0x4000

CALL = re.compile(r"^([A-Z_]+)\((.*)\)$")


class KeycodeError(ValueError):
    pass


def _preferred(names: list[str]) -> str:
    """The shortest proper name, so MS_BTN1 beats QK_MOUSE_BUTTON_1."""
    candidates = [n for n in names if n[0].isalpha()] or names
    return min(candidates, key=len)


class Codec:
    def __init__(self, table: dict, catalog: Catalog):
        self._by_name: dict[str, int] = {}
        self._by_code: dict[int, str] = {}
        for code_hex, names in table["keycodes"].items():
            code = int(code_hex, 16)
            for n in names:
                self._by_name[n] = code
            self._by_code[code] = _preferred(names)
        extra = dict(EXTRA)
        extra.update({k.name: k.value for k in catalog.keycodes})
        for name, code in extra.items():
            self._by_name[name] = code
            self._by_code[code] = name

    @classmethod
    def load(cls, catalog: Catalog) -> "Codec":
        return cls(json.loads(TABLE_PATH.read_text()), catalog)

    def encode(self, name: str) -> int:
        text = re.sub(r"\s+", "", name).upper()
        if text in self._by_name:
            return self._by_name[text]
        if text.startswith("0X"):
            try:
                code = int(text, 16)
            except ValueError:
                raise KeycodeError(f"bad hex keycode {name!r}") from None
            if 0 <= code <= 0xFFFF:
                return code
            raise KeycodeError(f"keycode {name!r} is outside 0x0000..0xFFFF")
        m = CALL.match(text)
        if not m:
            raise KeycodeError(f"unknown keycode {name!r}")
        func, arg = m.groups()
        if func in MODS:
            inner = self.encode(arg)
            if inner > 0xFF:
                raise KeycodeError(f"{func}() needs a basic keycode, got {arg!r}")
            return (MODS[func] << 8) | inner
        if func in LAYER_FUNCS:
            layer = self._layer(func, arg, 31)
            return LAYER_FUNCS[func] | layer
        if func == "LT":
            layer_text, _, key = arg.partition(",")
            layer = self._layer(func, layer_text, 15)
            inner = self.encode(key)
            if inner > 0xFF:
                raise KeycodeError(f"LT() needs a basic keycode, got {key!r}")
            return LT_BASE | (layer << 8) | inner
        raise KeycodeError(f"unknown keycode function {func}() in {name!r}")

    def decode(self, code: int) -> str:
        if code in self._by_code:
            return self._by_code[code]
        if 0x0100 <= code <= 0x1FFF and (code >> 8) in MOD_NAMES and (code & 0xFF) in self._by_code:
            return f"{MOD_NAMES[code >> 8]}({self._by_code[code & 0xFF]})"
        if 0x4000 <= code <= 0x4FFF and (code & 0xFF) in self._by_code:
            return f"LT({(code >> 8) & 0xF},{self._by_code[code & 0xFF]})"
        if (code & ~0x1F) in LAYER_FUNC_NAMES:
            return f"{LAYER_FUNC_NAMES[code & ~0x1F]}({code & 0x1F})"
        return f"0x{code:04X}"

    @staticmethod
    def _layer(func: str, text: str, highest: int) -> int:
        if not text.isdigit() or int(text) > highest:
            raise KeycodeError(f"{func}() needs a layer 0..{highest}, got {text!r}")
        return int(text)
