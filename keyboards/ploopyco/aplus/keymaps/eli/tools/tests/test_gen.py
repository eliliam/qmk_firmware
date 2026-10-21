import shutil

import pytest

from ploopy_tools import gen
from ploopy_tools.catalog import CATALOG_PATH, load_catalog


@pytest.fixture(scope="module")
def cat():
    return load_catalog(CATALOG_PATH)


@pytest.fixture(scope="module")
def info():
    return gen.load_info_json(gen.INFO_JSON_PATH)


def test_header_has_struct_and_ids(cat):
    h = gen.render_header(cat)
    assert "#define ELI_SETTINGS_CHANNEL 42" in h
    assert "#define ELI_SETTINGS_STORE_OFFSET 20" in h
    assert "#define ELI_SETTINGS_MARKER_ID 254" in h
    assert "#define ELI_SETTINGS_MAGIC 0xE1" in h
    assert "_Static_assert(VIA_EEPROM_CUSTOM_CONFIG_SIZE == 128" in h
    assert "X(niri_flick_threshold, 1, uint16_t, 200, 20, 2000)" in h
    assert "X(drag_scroll_divisor_h, 4, uint16_t, 80, 5, 1000)" in h
    assert "X(bottom_right_mode, 8, uint8_t, 0, 0, 1)" in h
    assert "X(wheels_vertical_arrows, 6, uint8_t, 0, 0, 1)" in h
    assert "accel" not in h.split("#define ELI_SETTINGS(X)")[1].split("\n\n")[0]
    assert "PKC_NIRI = QK_KB_4" in h
    assert "PKC_TGL_VERT_SCRL = QK_KB_2" in h
    assert "uint8_t marker[3];" in h


def test_header_fields_in_id_order(cat):
    h = gen.render_header(cat)
    struct = h.split("typedef struct")[1].split("} eli_settings_t;")[0]
    assert struct.index("niri_flick_threshold") < struct.index("pointer_dpi")


def test_via_definition(cat, info):
    v = gen.render_via(cat, info)
    assert v["vendorId"] == "0x5043"
    assert v["productId"] == "0x81DB"
    assert v["matrix"] == {"rows": 1, "cols": 8}
    legends = [k for row in v["layouts"]["keymap"] for k in row if isinstance(k, str)]
    assert sorted(legends) == [f"0,{c}" for c in range(8)]
    labels = [k["name"] for k in v["customKeycodes"]]
    assert labels[:2] == ["DPI Config", "Drag Scroll"]
    assert len(labels) == 9
    assert labels[4] == "Niri navigation (hold)"
    sections = {s["label"]: s["content"] for menu in v["menus"] for s in menu["content"]}
    assert set(sections) == {"Niri navigation", "Drag scroll", "Wheels", "Buttons", "Lighting", "Pointer", "Acceleration"}
    flick = sections["Niri navigation"][0]
    assert flick["type"] == "range"
    assert flick["options"] == [20, 2000]
    assert flick["content"] == ["id_niri_flick_threshold", 42, 1]
    mode = sections["Buttons"][0]
    assert mode["type"] == "dropdown"
    assert mode["options"] == [["Middle click", 0], ["Drag scroll", 1]]
    accel = {c["content"][0]: c for c in sections["Acceleration"]}
    assert accel["id_accel_takeoff"]["content"] == ["id_accel_takeoff", 24, 1]
    # The slider must not reach below the takeoff floor (0.5 of 0..5).
    assert accel["id_accel_takeoff"]["options"] == [6000, 60000]
    assert accel["id_accel_offset"]["options"] == [0, 60000]
    assert accel["id_accel_enabled"]["type"] == "toggle"


def test_check_detects_stale(tmp_path, cat):
    header = tmp_path / "settings_catalog.h"
    via = tmp_path / "via.json"
    assert gen.main(["--header", str(header), "--via", str(via)]) == 0
    assert gen.main(["--check", "--header", str(header), "--via", str(via)]) == 0
    header.write_text(header.read_text() + "// edited\n")
    assert gen.main(["--check", "--header", str(header), "--via", str(via)]) == 1


def test_committed_outputs_are_current():
    assert gen.main(["--check"]) == 0


def test_header_has_accel_takeoff_floor(cat):
    assert "#define ELI_ACCEL_TAKEOFF_MIN_RAW 6000" in gen.render_header(cat)
