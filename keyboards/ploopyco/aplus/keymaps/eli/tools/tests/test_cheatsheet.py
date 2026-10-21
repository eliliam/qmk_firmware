import json
import re

import pytest

from ploopy_tools.catalog import CATALOG_PATH, load_catalog
from ploopy_tools.cheatsheet import render_beside_config, render_cheatsheet
from ploopy_tools.mouseconfig import ConfigError, MouseState
from ploopy_tools.protocol import POSITIONS

TEMPLATE = """{
  "device": "Ploopy A+",
  "updated": {{ today | tojson }},
  "panels": [
    {% for layer in layers %}
    {"kind": "buttons", "title": "Layer {{ layer.index }}", "keys": {
      {% for pos, k in layer.buttons.items() %}
      {{ pos | tojson }}: {"label": {{ k.label | tojson }}, "detail": {{ k.detail | tojson }}}{{ "," if not loop.last }}
      {% endfor %}
    }}{{ "," if not loop.last }}
    {% endfor %}
  ],
  "footer": {{ ("Each " ~ s["niri.flick_threshold"] ~ " counts is one step") | tojson }}
}
"""

LABELS = """\
["MS_BTN1"]
label = "Left\\nClick"
detail = "Button 1"

["MEH(KC_SPC)"]
label = "Dictation"
"""


@pytest.fixture(scope="module")
def cat():
    return load_catalog(CATALOG_PATH)


def state(cat, **layer0):
    layers = {n: {p: "KC_TRNS" for p in POSITIONS} for n in range(8)}
    layers[0].update(layer0)
    return MouseState({s.name: s.default for s in cat.settings}, layers)


@pytest.fixture
def files(tmp_path):
    (tmp_path / "cheatsheet.json.j2").write_text(TEMPLATE)
    (tmp_path / "labels.toml").write_text(LABELS)
    return tmp_path


def keymap_json(html: str) -> dict:
    block = re.search(r'<script type="application/json" id="KEYMAP">\n(.*?)\n</script>', html, re.S).group(1)
    return json.loads(block)


def render(cat, files, st):
    out = files / "cheatsheet.html"
    render_cheatsheet(st, cat, files / "cheatsheet.json.j2", files / "labels.toml", out)
    return keymap_json(out.read_text())


def test_labels_and_fallback(cat, files):
    data = render(cat, files, state(cat, BL="MS_BTN1", TR="MEH(KC_SPC)", TL="KC_A"))
    keys = data["panels"][0]["keys"]
    assert keys["BL"] == {"label": "Left\nClick", "detail": "Button 1"}
    assert keys["TR"]["label"] == "Dictation"
    assert keys["TL"] == {"label": "KC_A", "detail": ""}


def test_setting_in_text(cat, files):
    st = state(cat, BL="MS_BTN1")
    st.settings["niri.flick_threshold"] = 240
    assert render(cat, files, st)["footer"] == "Each 240 counts is one step"


def test_empty_layers_skipped(cat, files):
    data = render(cat, files, state(cat, BL="MS_BTN1"))
    assert [p["title"] for p in data["panels"]] == ["Layer 0"]


def test_drawing_code_kept(cat, files):
    render(cat, files, state(cat, BL="MS_BTN1"))
    html = (files / "cheatsheet.html").read_text()
    assert "__KEYMAP_JSON__" not in html.split("</script>", 1)[1]
    assert "<svg" in html or "createElementNS" in html


def test_bad_template_raises(cat, files):
    (files / "cheatsheet.json.j2").write_text('{"panels": [ {{ s["nope"] }} ]}')
    with pytest.raises(ConfigError, match="cheat sheet"):
        render(cat, files, state(cat))


def test_invalid_json_raises(cat, files):
    (files / "cheatsheet.json.j2").write_text('{"panels": [,]}')
    with pytest.raises(ConfigError, match="cheat sheet"):
        render(cat, files, state(cat))


def test_beside_config_missing_files_warns(cat, tmp_path, capsys):
    render_beside_config(state(cat), cat, tmp_path / "mouse.toml")
    assert "cheat sheet" in capsys.readouterr().err
    assert not (tmp_path / "cheatsheet.html").exists()


def test_beside_config_writes_output(cat, files):
    render_beside_config(state(cat, BL="MS_BTN1"), cat, files / "mouse.toml")
    assert keymap_json((files / "cheatsheet.html").read_text())["panels"][0]["title"] == "Layer 0"
