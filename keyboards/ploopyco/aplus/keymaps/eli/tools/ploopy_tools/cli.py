"""ploopy: inspect and change Eli's Ploopy A+ at runtime.

The mouse config (default ~/.config/ploopy/mouse.toml) is the source of
truth. `apply` makes the mouse match it, `pull` copies the mouse into it,
`set` changes one setting on both."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from .catalog import Catalog, Value, load_catalog
from .keycodes import Codec, KeycodeError
from .mouseconfig import ConfigError, MouseState, diff, load_config, read_state, save_config, write_state
from .protocol import HidTransport, Mouse, MouseError, NoDeviceError

DEFAULT_CONFIG = Path.home() / ".config" / "ploopy" / "mouse.toml"
PLUG_WAIT_SECONDS = 10
PLUG_POLL_SECONDS = 0.5


def _default_render(state: MouseState, cat: Catalog, config_path: Path) -> None:
    from .cheatsheet import render_beside_config

    render_beside_config(state, cat, config_path)


def _parse_value(text: str, kind: str) -> Value:
    if kind == "bool":
        if text.lower() in ("true", "on", "1", "yes"):
            return True
        if text.lower() in ("false", "off", "0", "no"):
            return False
        return text
    if kind == "enum":
        return text
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


class App:
    def __init__(self, config_path: Path, transport_factory, run, render, sleep):
        self.config_path = config_path
        self.transport_factory = transport_factory
        self.run = run
        self.render = render
        self.sleep = sleep
        self.cat = load_catalog()
        self.codec = Codec.load(self.cat)

    def mouse(self) -> Mouse:
        return Mouse(self.transport_factory())

    def config(self) -> MouseState:
        return load_config(self.config_path, self.cat, self.codec)

    def cmd_diff(self, args) -> int:
        config = self.config()
        found = diff(read_state(self.mouse(), self.cat, self.codec), config, self.cat)
        for d in found:
            print(f"{d.path}: mouse={d.mouse} config={d.config}")
        return 1 if found else 0

    def apply(self, mouse: Mouse | None = None) -> int:
        config = self.config()
        mouse = mouse or self.mouse()
        writes = write_state(mouse, config, read_state(mouse, self.cat, self.codec), self.cat, self.codec)
        mouse.set_marker()
        self.render(config, self.cat, self.config_path)
        return writes

    def cmd_apply(self, args) -> int:
        print(f"applied: {self.apply()} writes")
        return 0

    def cmd_pull(self, args) -> int:
        state = read_state(self.mouse(), self.cat, self.codec)
        save_config(self.config_path, state, self.cat)
        self.render(state, self.cat, self.config_path)
        print(f"pulled into {self.config_path}")
        return 0

    def _setting(self, name: str):
        try:
            return self.cat.setting(name)
        except KeyError:
            raise ConfigError(f"unknown setting {name}") from None

    def cmd_get(self, args) -> int:
        value = self.mouse().get_setting(self._setting(args.name))
        print(str(value).lower() if isinstance(value, bool) else value)
        return 0

    def cmd_set(self, args) -> int:
        s = self._setting(args.name)
        value = _parse_value(args.value, s.type)
        try:
            s.validate(value)
        except ValueError as e:
            raise ConfigError(str(e)) from None
        config = self.config()
        mouse = self.mouse()
        mouse.set_setting(s, value)
        mouse.save(s.channel)
        config.settings[s.name] = value
        save_config(self.config_path, config, self.cat)
        self.render(config, self.cat, self.config_path)
        return 0

    def cmd_on_plug(self, args) -> int:
        self.run(["systemctl", "--user", "restart", "voxtype"], check=False)
        try:
            mouse = self._wait_for_mouse()
            if mouse.marker_valid():
                print("mouse config already applied; nothing to do")
                return 0
            writes = self.apply(mouse)
            print(f"restored mouse config after reset: {writes} writes")
            self.run(["notify-send", "Ploopy", "Restored mouse config after reset"], check=False)
            return 0
        except (MouseError, ConfigError, KeycodeError) as e:
            print(f"ploopy: {e}", file=sys.stderr)
            self.run(["notify-send", "-u", "critical", "Ploopy", f"Could not restore mouse config: {e}"], check=False)
            return 1

    def _wait_for_mouse(self) -> Mouse:
        attempts = int(PLUG_WAIT_SECONDS / PLUG_POLL_SECONDS)
        for attempt in range(attempts):
            try:
                return self.mouse()
            except NoDeviceError:
                if attempt == attempts - 1:
                    raise
                self.sleep(PLUG_POLL_SECONDS)
        raise NoDeviceError("unreachable")


def main(argv=None, *, transport_factory=None, run=subprocess.run, render=None, sleep=time.sleep) -> int:
    p = argparse.ArgumentParser(prog="ploopy", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=Path(os.environ.get("PLOOPY_CONFIG", DEFAULT_CONFIG)), help="mouse config path")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("diff", help="show drift between the mouse and the mouse config (exit 1 if any)")
    sub.add_parser("apply", help="make the mouse match the mouse config")
    sub.add_parser("pull", help="copy the mouse's state into the mouse config")
    g = sub.add_parser("get", help="print one setting from the mouse")
    g.add_argument("name")
    s = sub.add_parser("set", help="change one setting on the mouse and in the mouse config")
    s.add_argument("name")
    s.add_argument("value")
    sub.add_parser("on-plug", help="plug-in hook: restart voxtype, auto-apply after a reset or wipe")
    args = p.parse_args(argv)

    app = App(args.config, transport_factory or HidTransport.open, run, render or _default_render, sleep)
    handler = getattr(app, "cmd_" + args.command.replace("-", "_"))
    try:
        return handler(args)
    except (MouseError, ConfigError, KeycodeError) as e:
        print(f"ploopy: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
