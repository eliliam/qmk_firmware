"""The mouse config (TOML in dotfiles): the desired button map and settings,
and how it compares to and gets written onto the mouse."""

from dataclasses import dataclass, field
from pathlib import Path

import tomlkit

from .catalog import Catalog, Value, load_catalog
from .keycodes import Codec, KeycodeError
from .protocol import POSITIONS, Mouse

LAYERS = 8
TRANSPARENT = "KC_TRNS"


class ConfigError(ValueError):
    pass


@dataclass
class MouseState:
    settings: dict[str, Value] = field(default_factory=dict)
    layers: dict[int, dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Difference:
    path: str
    mouse: str
    config: str


def _empty_layers() -> dict[int, dict[str, str]]:
    return {layer: {pos: TRANSPARENT for pos in POSITIONS} for layer in range(LAYERS)}


def read_state(mouse: Mouse, cat: Catalog, codec: Codec) -> MouseState:
    layers = {
        layer: {pos: codec.decode(mouse.get_keycode(layer, col)) for pos, col in POSITIONS.items()}
        for layer in range(LAYERS)
    }
    settings = {s.name: mouse.get_setting(s) for s in cat.settings}
    return MouseState(settings, layers)


def load_config(path: Path, cat: Catalog, codec: Codec) -> MouseState:
    """Parse and fully validate the mouse config. Raises ConfigError naming
    the TOML path of the first problem."""
    try:
        doc = tomlkit.parse(Path(path).read_text()).unwrap()
    except FileNotFoundError:
        raise ConfigError(f"{path}: mouse config not found") from None
    except tomlkit.exceptions.ParseError as e:
        raise ConfigError(f"{path}: {e}") from None

    for key in doc:
        if key not in ("settings", "layers"):
            raise ConfigError(f"{key}: unknown section")

    settings: dict[str, Value] = {}
    known = {s.name for s in cat.settings}
    for group, table in doc.get("settings", {}).items():
        if not isinstance(table, dict):
            raise ConfigError(f"settings.{group}: expected a table")
        for key, value in table.items():
            name = f"{group}.{key}"
            if name not in known:
                raise ConfigError(f"settings.{name}: unknown setting")
            try:
                cat.setting(name).validate(value)
            except ValueError as e:
                raise ConfigError(f"settings.{e}") from None
            settings[name] = value
    for s in cat.settings:
        if s.name not in settings:
            raise ConfigError(f"settings.{s.name}: missing")

    layers = _empty_layers()
    for layer_key, table in doc.get("layers", {}).items():
        if not layer_key.isdigit() or int(layer_key) >= LAYERS:
            raise ConfigError(f"layers.{layer_key}: layers are 0..{LAYERS - 1}")
        for pos, name in table.items():
            path_ = f"layers.{layer_key}.{pos}"
            if pos not in POSITIONS:
                raise ConfigError(f"{path_}: unknown position (use {', '.join(POSITIONS)})")
            if not isinstance(name, str):
                raise ConfigError(f"{path_}: expected a keycode name")
            try:
                layers[int(layer_key)][pos] = codec.decode(codec.encode(name))
            except KeycodeError as e:
                raise ConfigError(f"{path_}: {e}") from None
    return MouseState(settings, layers)


def _same(cat: Catalog, name: str, a: Value, b: Value) -> bool:
    s = cat.setting(name)
    try:
        return s.encode(a) == s.encode(b)
    except ValueError:
        return a == b


def _show(value: Value) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def diff(mouse: MouseState, config: MouseState, cat: Catalog | None = None) -> list[Difference]:
    cat = cat or load_catalog()
    found = []
    for s in cat.settings:
        a, b = mouse.settings[s.name], config.settings[s.name]
        if not _same(cat, s.name, a, b):
            found.append(Difference(f"settings.{s.name}", _show(a), _show(b)))
    for layer in range(LAYERS):
        for pos in POSITIONS:
            a, b = mouse.layers[layer][pos], config.layers[layer][pos]
            if a != b:
                found.append(Difference(f"layers.{layer}.{pos}", a, b))
    return found


def write_state(mouse: Mouse, target: MouseState, current: MouseState, cat: Catalog, codec: Codec) -> int:
    """Write only what differs, then save each touched settings channel once.
    Returns the number of writes."""
    writes = 0
    for layer in range(LAYERS):
        for pos, col in POSITIONS.items():
            if target.layers[layer][pos] != current.layers[layer][pos]:
                mouse.set_keycode(layer, col, codec.encode(target.layers[layer][pos]))
                writes += 1
    channels = []
    for s in cat.settings:
        if not _same(cat, s.name, target.settings[s.name], current.settings[s.name]):
            mouse.set_setting(s, target.settings[s.name])
            writes += 1
            if s.channel not in channels:
                channels.append(s.channel)
    for channel in channels:
        mouse.save(channel)
    return writes


def save_config(path: Path, state: MouseState, cat: Catalog) -> None:
    """Update the mouse config in place, keeping comments and layout. Opens
    the file for writing (no rename), so a stow symlink stays a symlink."""
    path = Path(path)
    doc = tomlkit.parse(path.read_text()) if path.exists() else tomlkit.document()

    settings = doc.setdefault("settings", tomlkit.table(is_super_table=True))
    for s in cat.settings:
        group, key = s.name.split(".", 1)
        table = settings.setdefault(group, tomlkit.table())
        value = state.settings[s.name]
        if key in table and not isinstance(value, bool) and isinstance(table[key], (int, float)):
            if _same(cat, s.name, table[key].unwrap(), value):
                continue
        table[key] = value

    layers = doc.setdefault("layers", tomlkit.table(is_super_table=True))
    for layer in range(LAYERS):
        keys = state.layers[layer]
        name = str(layer)
        if all(v == TRANSPARENT for v in keys.values()):
            if name in layers:
                del layers[name]
            continue
        table = layers.setdefault(name, tomlkit.table())
        for pos in POSITIONS:
            if table.get(pos) != keys[pos]:
                table[pos] = keys[pos]

    with open(path, "w") as f:
        f.write(tomlkit.dumps(doc))
