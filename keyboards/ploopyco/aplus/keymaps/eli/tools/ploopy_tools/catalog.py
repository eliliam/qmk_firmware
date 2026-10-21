"""The setting catalog: every runtime setting and custom keycode, loaded from
settings.toml in the keymap folder."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CATALOG_PATH = Path(__file__).resolve().parents[2] / "settings.toml"

QK_KB_2 = 0x7E02
ACCEL_VIA_MAX = 60000
TYPES = ("u8", "u16", "bool", "enum", "accel")

Value = int | float | bool | str


class CatalogError(Exception):
    pass


@dataclass(frozen=True)
class Setting:
    name: str
    id: int
    channel: int
    type: Literal["u8", "u16", "bool", "enum", "accel"]
    min: float
    max: float
    default: Value
    label: str
    group: str
    options: tuple[str, ...] = ()
    scale: float = 1.0
    step: int = 1
    via_min: float | None = None
    via_max: float | None = None

    @property
    def c_name(self) -> str:
        return self.name.replace(".", "_")

    @property
    def size(self) -> int:
        return 2 if self.type in ("u16", "accel") else 1

    @property
    def raw_default(self) -> int:
        """The stored integer for the default (scaled, enum index, bool)."""
        return self._to_raw(self.default)

    def validate(self, value: Value) -> None:
        if self.type == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{self.name}: expected true or false, got {value!r}")
            return
        if self.type == "enum":
            if value not in self.options:
                raise ValueError(f"{self.name}: expected one of {', '.join(self.options)}, got {value!r}")
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{self.name}: expected a number, got {value!r}")
        shown_min, shown_max = self._shown(self.min), self._shown(self.max)
        if not shown_min <= value <= shown_max:
            raise ValueError(f"{self.name}: {value} is outside {shown_min}..{shown_max}")
        if self.type != "accel" and abs(value / self.scale - round(value / self.scale)) > 1e-9:
            raise ValueError(f"{self.name}: {value} must be a multiple of {self.scale}")
        if self.step > 1 and round(value / self.scale) % self.step:
            raise ValueError(f"{self.name}: {value} must be a multiple of {self.step}")

    def encode(self, value: Value) -> bytes:
        self.validate(value)
        return self._to_raw(value).to_bytes(self.size, "big")

    def decode(self, data: bytes) -> Value:
        raw = int.from_bytes(data[: self.size], "big")
        if self.type == "bool":
            return bool(raw)
        if self.type == "enum":
            return self.options[raw] if raw < len(self.options) else raw
        if self.type == "accel":
            return round(self.via_min + raw * (self.via_max - self.via_min) / ACCEL_VIA_MAX, 4)
        return self._shown(raw)

    def _shown(self, raw: float) -> int | float:
        if self.scale == 1.0:
            return int(raw) if self.type != "accel" else raw
        return round(raw * self.scale, 6)

    def _to_raw(self, value: Value) -> int:
        if self.type == "bool":
            return int(bool(value))
        if self.type == "enum":
            return self.options.index(value)
        if self.type == "accel":
            return round((value - self.via_min) / (self.via_max - self.via_min) * ACCEL_VIA_MAX)
        return round(value / self.scale)


@dataclass(frozen=True)
class Keycode:
    name: str
    value: int
    label: str


@dataclass(frozen=True)
class Catalog:
    channel: int
    store_offset: int
    custom_config_size: int
    settings: tuple[Setting, ...]
    keycodes: tuple[Keycode, ...]

    def setting(self, name: str) -> Setting:
        for s in self.settings:
            if s.name == name:
                return s
        raise KeyError(name)


def _setting(raw: dict, channel: int) -> Setting:
    kind = raw["type"]
    if kind not in TYPES:
        raise CatalogError(f"{raw['name']}: unknown type {kind!r}")
    options = tuple(raw.get("options", ()))
    if kind == "bool":
        lo, hi = 0, 1
    elif kind == "enum":
        lo, hi = 0, len(options) - 1
    else:
        lo, hi = raw["min"], raw["max"]
    s = Setting(
        name=raw["name"],
        id=raw["id"],
        channel=raw.get("channel", channel),
        type=kind,
        min=lo,
        max=hi,
        default=raw["default"],
        label=raw["label"],
        group=raw["group"],
        options=options,
        scale=raw.get("scale", 1.0),
        step=raw.get("step", 1),
        via_min=raw.get("via_min"),
        via_max=raw.get("via_max"),
    )
    shown_default = s.default if kind in ("bool", "enum", "accel") else s._shown(s.default)
    try:
        s.validate(shown_default)
    except ValueError as e:
        raise CatalogError(f"default out of range: {e}") from e
    # Defaults are written as stored integers in the catalog; keep the shown
    # value on the Setting so the CLI and generator agree.
    return Setting(**{**s.__dict__, "default": shown_default})


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    data = tomllib.loads(Path(path).read_text())
    channel = data["channel"]
    settings = tuple(_setting(raw, channel) for raw in data.get("setting", []))
    names, ids = set(), set()
    for s in settings:
        if s.name in names:
            raise CatalogError(f"duplicate setting name {s.name}")
        if (s.channel, s.id) in ids:
            raise CatalogError(f"duplicate id {s.id} on channel {s.channel} ({s.name})")
        names.add(s.name)
        ids.add((s.channel, s.id))
    keycodes = tuple(
        Keycode(raw["name"], QK_KB_2 + i, raw["label"]) for i, raw in enumerate(data.get("keycode", []))
    )
    return Catalog(
        channel=channel,
        store_offset=data["store_offset"],
        custom_config_size=data["custom_config_size"],
        settings=settings,
        keycodes=keycodes,
    )
