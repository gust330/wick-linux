"""Regression tests for GNOME's unordered DBusMenu click calls."""

import ast
from pathlib import Path
import time
import types
import unittest


class _Object:
    def __init__(self, *args, **kwargs):
        pass


def _method(*args, **kwargs):
    return lambda function: function


class _App:
    def __init__(self):
        self.pointer_toggles = 0
        self.menu_toggles = 0

    def toggle_panel_at_pointer(self):
        self.pointer_toggles += 1

    def toggle_panel(self):
        self.menu_toggles += 1


def _load_dbus_menu():
    source = Path(__file__).parents[1] / "src/wick/tray.py"
    tree = ast.parse(source.read_text())
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "DBusMenu")
    module = ast.Module(body=[node], type_ignores=[])
    dbus = types.SimpleNamespace(
        service=types.SimpleNamespace(Object=_Object, method=_method, BusName=object),
        Boolean=bool,
        String=str,
        UInt32=int,
        Int32=int,
        Array=lambda values=(), **kwargs: list(values),
        Dictionary=lambda values=(), **kwargs: dict(values),
        Struct=lambda values=(), **kwargs: tuple(values),
        exceptions=types.SimpleNamespace(DBusException=Exception),
    )
    glib = types.SimpleNamespace(idle_add=lambda callback: callback())
    namespace = {
        "dbus": dbus,
        "GLib": glib,
        "time": time,
        "_DBUSMENU_IFACE": "com.canonical.dbusmenu",
        "_DBUSMENU_PATH": "/MenuBar",
        "_DBUSMENU_PROPS_IFACE": "org.freedesktop.DBus.Properties",
        "WickApp": _App,
    }
    exec(compile(module, str(source), "exec"), namespace)
    return namespace["DBusMenu"]


class DBusMenuActivationTests(unittest.TestCase):
    def make_menu(self):
        app = _App()
        menu = _load_dbus_menu()(object(), app)
        menu._activation_ready_at = 0
        return menu, app

    def test_about_to_show_then_opened_toggles_only_once(self):
        menu, app = self.make_menu()
        menu.AboutToShow(0)
        menu.Event(0, "opened", None, 0)
        self.assertEqual(app.pointer_toggles, 1)

    def test_opened_then_about_to_show_toggles_only_once(self):
        menu, app = self.make_menu()
        menu.Event(0, "opened", None, 0)
        menu.AboutToShow(0)
        self.assertEqual(app.pointer_toggles, 1)

    def test_discovery_call_during_startup_is_ignored(self):
        menu, app = self.make_menu()
        menu._activation_ready_at = time.monotonic() + 1.5
        menu.AboutToShow(0)
        self.assertEqual(app.pointer_toggles, 0)

    def test_opened_during_startup_is_ignored(self):
        menu, app = self.make_menu()
        menu._activation_ready_at = time.monotonic() + 1.5
        menu.Event(0, "opened", None, 0)
        self.assertEqual(app.pointer_toggles, 0)

    def test_later_click_toggles_again(self):
        menu, app = self.make_menu()
        menu.Event(0, "opened", None, 0)
        menu._last_activation_at -= 0.25
        menu.AboutToShow(0)
        self.assertEqual(app.pointer_toggles, 2)


if __name__ == "__main__":
    unittest.main()
