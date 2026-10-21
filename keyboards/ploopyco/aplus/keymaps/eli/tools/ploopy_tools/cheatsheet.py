"""Render the cheat sheet: a Jinja2 template in dotfiles produces the KEYMAP
JSON, which goes into drawing.html's data slot."""

import datetime
import json
import sys
import tomllib
from pathlib import Path

import jinja2

from .catalog import Catalog
from .mouseconfig import TRANSPARENT, ConfigError, MouseState

DRAWING_PATH = Path(__file__).with_name("drawing.html")
SLOT = "\n__KEYMAP_JSON__\n"
TEMPLATE_NAME = "cheatsheet.json.j2"
LABELS_NAME = "labels.toml"
OUTPUT_NAME = "cheatsheet.html"


def _context(state: MouseState, labels: dict) -> dict:
    def key(layer: int, pos: str) -> dict:
        name = state.layers[layer][pos]
        entry = labels.get(name, {})
        return {"name": name, "label": entry.get("label", name), "detail": entry.get("detail", "")}

    layers = [
        {"index": n, "buttons": {pos: key(n, pos) for pos in keys}}
        for n, keys in sorted(state.layers.items())
        if any(v != TRANSPARENT for v in keys.values())
    ]
    return {"s": dict(state.settings), "key": key, "layers": layers, "today": datetime.date.today().isoformat()}


def render_cheatsheet(state: MouseState, cat: Catalog, template: Path, labels: Path, out: Path) -> None:
    try:
        label_table = tomllib.loads(Path(labels).read_text())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"cheat sheet labels {labels}: {e}") from None
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    try:
        text = env.from_string(Path(template).read_text()).render(_context(state, label_table))
        data = json.loads(text)
    except (jinja2.TemplateError, json.JSONDecodeError) as e:
        raise ConfigError(f"cheat sheet template {template}: {e}") from None
    keymap_json = json.dumps(data, indent=2, ensure_ascii=False).replace("</", "<\\/")
    html = DRAWING_PATH.read_text().replace(SLOT, f"\n{keymap_json}\n", 1)
    with open(out, "w") as f:
        f.write(html)


def render_beside_config(state: MouseState, cat: Catalog, config_path: Path) -> None:
    """Render using the template and labels next to the mouse config. Missing
    files skip rendering with a warning; the cheat sheet is optional."""
    folder = Path(config_path).parent
    template, labels = folder / TEMPLATE_NAME, folder / LABELS_NAME
    missing = [p.name for p in (template, labels) if not p.exists()]
    if missing:
        print(f"ploopy: cheat sheet not rendered ({', '.join(missing)} missing in {folder})", file=sys.stderr)
        return
    render_cheatsheet(state, cat, template, labels, folder / OUTPUT_NAME)
