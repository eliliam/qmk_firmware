import pytest

from fake_mouse import FakeMouse
from ploopy_tools import cli
from ploopy_tools.catalog import CATALOG_PATH, load_catalog
from ploopy_tools.protocol import POSITIONS, NoDeviceError
from test_mouseconfig import CONFIG


@pytest.fixture(scope="module")
def cat():
    return load_catalog(CATALOG_PATH)


@pytest.fixture
def fake(cat):
    return FakeMouse(cat)


@pytest.fixture
def config_path(tmp_path):
    p = tmp_path / "mouse.toml"
    p.write_text(CONFIG)
    return p


class Calls:
    def __init__(self):
        self.commands = []
        self.renders = 0

    def run(self, argv, **kwargs):
        self.commands.append(argv)

    def render(self, *args):
        self.renders += 1


@pytest.fixture
def calls():
    return Calls()


@pytest.fixture
def ploopy(fake, config_path, calls):
    def invoke(*argv, factory=None):
        return cli.main(
            ["--config", str(config_path), *argv],
            transport_factory=factory or (lambda: fake),
            run=calls.run,
            render=calls.render,
            sleep=lambda s: None,
        )

    return invoke


def test_diff_clean_after_apply(ploopy, capsys):
    assert ploopy("apply") == 0
    assert "9 writes" in capsys.readouterr().out
    assert ploopy("diff") == 0


def test_diff_reports_drift(ploopy, fake, capsys):
    ploopy("apply")
    fake.keymap[0][POSITIONS["TR"]] = 0x00D3
    capsys.readouterr()
    assert ploopy("diff") == 1
    assert "layers.0.TR: mouse=MS_BTN3 config=MEH(KC_SPC)" in capsys.readouterr().out


def test_apply_sets_marker_and_renders(ploopy, fake, calls):
    ploopy("apply")
    assert fake.marker is True
    assert calls.renders == 1


def test_pull_then_diff_clean(ploopy, fake, config_path):
    ploopy("apply")
    fake.values[(42, 10)] = (1600).to_bytes(2, "big")
    fake.values[(24, 3)] = (8801).to_bytes(2, "big")
    assert ploopy("pull") == 0
    assert "dpi = 1600" in config_path.read_text()
    assert ploopy("diff") == 0


def test_get(ploopy, capsys):
    assert ploopy("get", "pointer.dpi") == 0
    assert capsys.readouterr().out.strip() == "900"


def test_set_preserves_comments_and_symlink(fake, tmp_path, calls, capsys):
    real = tmp_path / "dotfiles" / "mouse.toml"
    real.parent.mkdir()
    real.write_text(CONFIG)
    link = tmp_path / "mouse.toml"
    link.symlink_to(real)
    code = cli.main(
        ["--config", str(link), "set", "niri.flick_threshold", "240"],
        transport_factory=lambda: fake,
        run=calls.run,
        render=calls.render,
    )
    assert code == 0
    assert link.is_symlink()
    text = real.read_text()
    assert "flick_threshold = 240 # counts per step" in text
    assert "# Eli's mouse" in text
    assert fake.saved[(42, 1)] == (240).to_bytes(2, "big")
    assert calls.renders == 1


@pytest.mark.parametrize(
    "name,value,stored",
    [("wheels.vertical_arrows", "true", b"\x01"), ("bottom_right.mode", "drag_scroll", b"\x01"), ("drag_scroll.divisor_h", "0.6", bytes([0, 60]))],
)
def test_set_parses_types(ploopy, fake, cat, name, value, stored):
    assert ploopy("set", name, value) == 0
    s = cat.setting(name)
    assert fake.saved[(s.channel, s.id)] == stored


@pytest.mark.parametrize(
    "edit,path",
    [
        (("dpi = 900", "dpi = 900\nspeed = 2"), "settings.pointer.speed"),
        (("dpi = 900", "dpi = 50"), "settings.pointer.dpi"),
        (('BL = "QK_BOOT"', 'BL = "KC_NOPE"'), "layers.1.BL"),
    ],
)
def test_invalid_config_writes_nothing(ploopy, fake, config_path, capsys, edit, path):
    config_path.write_text(CONFIG.replace(*edit))
    assert ploopy("apply") == 2
    err = capsys.readouterr().err
    assert path in err
    assert "Traceback" not in err
    assert fake.writes == 0


def test_set_rejects_bad_value(ploopy, fake, capsys):
    assert ploopy("set", "pointer.dpi", "50") == 2
    assert "pointer.dpi" in capsys.readouterr().err
    assert fake.writes == 0


def test_set_unknown_setting(ploopy, capsys):
    assert ploopy("set", "pointer.speed", "3") == 2
    assert "unknown setting pointer.speed" in capsys.readouterr().err


def test_no_device_message(ploopy, capsys):
    def missing():
        raise NoDeviceError("Ploopy A+ not found: is it plugged in, and does udev grant hidraw access?")

    assert ploopy("diff", factory=missing) == 2
    err = capsys.readouterr().err
    assert err.strip() == "ploopy: Ploopy A+ not found: is it plugged in, and does udev grant hidraw access?"


def test_on_plug_applies_only_when_marker_invalid(ploopy, fake, calls):
    assert ploopy("on-plug") == 0
    assert ["systemctl", "--user", "restart", "voxtype"] in calls.commands
    assert ["notify-send", "Ploopy", "Restored mouse config after reset"] in calls.commands
    assert fake.marker is True
    writes = fake.writes
    calls.commands.clear()
    assert ploopy("on-plug") == 0
    assert fake.writes == writes
    assert not any(c[0] == "notify-send" for c in calls.commands)


def test_on_plug_notifies_on_error(ploopy, config_path, calls):
    config_path.write_text(CONFIG.replace("dpi = 900", "dpi = 50"))
    assert ploopy("on-plug") == 1
    assert any(c[:3] == ["notify-send", "-u", "critical"] for c in calls.commands)


def test_on_plug_waits_for_device(ploopy, fake, calls):
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise NoDeviceError("not yet")
        return fake

    assert ploopy("on-plug", factory=flaky) == 0
    assert len(attempts) == 3


def test_pull_on_broken_config_is_one_line_error(ploopy, config_path, capsys):
    config_path.write_text("[settings.led\n")
    assert ploopy("pull") == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err and "mouse.toml" in err


def test_pull_refuses_values_the_config_would_reject(ploopy, fake, config_path, capsys):
    before = config_path.read_text()
    fake.values[(24, 1)] = (3000).to_bytes(2, "big")  # takeoff 0.25, below the 0.5 floor
    assert ploopy("pull") == 2
    assert "accel.takeoff" in capsys.readouterr().err
    assert config_path.read_text() == before


def test_render_failure_after_apply_is_a_warning(fake, config_path, calls, capsys):
    from ploopy_tools.mouseconfig import ConfigError

    def broken(*args):
        raise ConfigError("cheat sheet template x: boom")

    def invoke(*argv):
        return cli.main(["--config", str(config_path), *argv], transport_factory=lambda: fake, run=calls.run, render=broken, sleep=lambda s: None)

    assert invoke("apply") == 0
    assert "warning" in capsys.readouterr().err
    fake.marker = False
    assert invoke("on-plug") == 0
    assert ["notify-send", "Ploopy", "Restored mouse config after reset"] in calls.commands
    assert not any(c[:3] == ["notify-send", "-u", "critical"] for c in calls.commands)
