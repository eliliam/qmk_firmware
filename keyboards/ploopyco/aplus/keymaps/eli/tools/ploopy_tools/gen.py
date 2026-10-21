"""Generate settings_catalog.h (firmware) and via.json (VIA definition) from
the setting catalog.

    uv run --project tools python -m ploopy_tools.gen [--check]
"""

import argparse
import json
import re
import sys
from pathlib import Path

from .catalog import ACCEL_VIA_MAX, CATALOG_PATH, Catalog, Setting, load_catalog

KEYMAP_DIR = CATALOG_PATH.parent
HEADER_PATH = KEYMAP_DIR / "settings_catalog.h"
VIA_PATH = KEYMAP_DIR / "via.json"
INFO_JSON_PATH = KEYMAP_DIR.parents[1] / "info.json"

MARKER_ID = 254
MAGIC = 0xE1
HEADER_BYTES = 5  # magic, length, marker[3]

BANNER = "Generated from settings.toml by tools/ploopy_tools/gen.py. Do not edit."


def _ctype(s: Setting) -> str:
    return "uint16_t" if s.size == 2 else "uint8_t"


def _store_settings(cat: Catalog) -> list[Setting]:
    return sorted((s for s in cat.settings if s.channel == cat.channel), key=lambda s: s.id)


def render_header(cat: Catalog) -> str:
    store = _store_settings(cat)
    rows = " \\\n".join(
        f"    X({s.c_name}, {s.id}, {_ctype(s)}, {s.raw_default}, {int(s.min)}, {int(s.max)})"
        for s in store
    )
    fields = "\n".join(f"    {_ctype(s)} {s.c_name};" for s in store)
    keycodes = ",\n".join(f"    {k.name} = QK_KB_{k.value - 0x7E00}" for k in cat.keycodes)
    return f"""// {BANNER}
#pragma once

#include <stdint.h>
#include "quantum_keycodes.h"

#define ELI_SETTINGS_CHANNEL {cat.channel}
#define ELI_SETTINGS_STORE_OFFSET {cat.store_offset}
#define ELI_SETTINGS_MARKER_ID {MARKER_ID}
#define ELI_SETTINGS_MAGIC 0x{MAGIC:02X}

_Static_assert(VIA_EEPROM_CUSTOM_CONFIG_SIZE == {cat.custom_config_size}, "VIA_EEPROM_CUSTOM_CONFIG_SIZE must match settings.toml");

/* X(field, value id, type, default, min, max), in id order. Values are the
   stored integers: scaled settings hold value / scale, bools 0/1, enums an
   option index. */
#define ELI_SETTINGS(X) \\
{rows}

/* Stored at ELI_SETTINGS_STORE_OFFSET in the VIA custom config. New fields
   are only ever appended. */
typedef struct __attribute__((packed)) {{
    uint8_t magic;
    uint8_t length;
    uint8_t marker[3];
{fields}
}} eli_settings_t;

_Static_assert(ELI_SETTINGS_STORE_OFFSET + sizeof(eli_settings_t) <= VIA_EEPROM_CUSTOM_CONFIG_SIZE, "settings store does not fit");

enum eli_keycodes {{
{keycodes}
}};
"""


def load_info_json(path: Path) -> dict:
    text = Path(path).read_text()
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))


def _kle(info: dict) -> list:
    keys = sorted(info["layouts"]["LAYOUT"]["layout"], key=lambda k: (k["y"], k["x"]))
    rows, cur_y = [], 0.0
    for y in sorted({k["y"] for k in keys}):
        row, cur_x = [], 0.0
        for k in (k for k in keys if k["y"] == y):
            props = {}
            if not row and y != cur_y:
                props["y"] = round(y - cur_y, 4)
            if k["x"] != cur_x:
                props["x"] = round(k["x"] - cur_x, 4)
            for dim in ("w", "h"):
                if dim in k:
                    props[dim] = k[dim]
            if props:
                row.append(props)
            row.append(f"{k['matrix'][0]},{k['matrix'][1]}")
            cur_x = k["x"] + k.get("w", 1)
        rows.append(row)
        cur_y = y + 1
    return rows


def _control(s: Setting) -> dict:
    content = [f"id_{s.c_name}", s.channel, s.id]
    if s.type == "bool":
        return {"label": s.label, "type": "toggle", "content": content}
    if s.type == "enum":
        options = [[o.replace("_", " ").capitalize(), i] for i, o in enumerate(s.options)]
        return {"label": s.label, "type": "dropdown", "options": options, "content": content}
    if s.type == "accel":
        return {"label": s.label, "type": "range", "options": [0, ACCEL_VIA_MAX], "content": content}
    return {"label": s.label, "type": "range", "options": [int(s.min), int(s.max)], "content": content}


def render_via(cat: Catalog, info: dict) -> dict:
    groups: dict[str, list] = {}
    for s in cat.settings:
        groups.setdefault(s.group, []).append(_control(s))
    custom = [
        {"name": "DPI Config", "title": "Cycle DPI (board)", "shortName": "DPI"},
        {"name": "Drag Scroll", "title": "Drag scroll (board)", "shortName": "Drag"},
    ] + [{"name": k.label, "title": k.name, "shortName": k.name.removeprefix("PKC_")[:6]} for k in cat.keycodes]
    return {
        "name": "Ploopy A+ (eli)",
        "vendorId": "0x5043",
        "productId": "0x81DB",
        "matrix": {"rows": 1, "cols": 8},
        "keycodes": ["qmk_lighting"],
        "customKeycodes": custom,
        "menus": [
            {"label": "Eli", "content": [{"label": g, "content": c} for g, c in groups.items()]},
        ],
        "layouts": {"keymap": _kle(info)},
    }


def _outputs(cat: Catalog) -> tuple[str, str]:
    header = render_header(cat)
    via = json.dumps(render_via(cat, load_info_json(INFO_JSON_PATH)), indent=2) + "\n"
    return header, via


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", help="exit 1 if the outputs are out of date")
    p.add_argument("--header", type=Path, default=HEADER_PATH)
    p.add_argument("--via", type=Path, default=VIA_PATH)
    args = p.parse_args(argv)
    header, via = _outputs(load_catalog(CATALOG_PATH))
    targets = ((args.header, header), (args.via, via))
    if args.check:
        stale = [str(path) for path, text in targets if not path.exists() or path.read_text() != text]
        for path in stale:
            print(f"out of date: {path}", file=sys.stderr)
        return 1 if stale else 0
    for path, text in targets:
        path.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
