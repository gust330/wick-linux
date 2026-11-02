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
        self.quick_starts = []
        self.stop_calls = 0

    def toggle_panel_at_pointer(self):
        self.pointer_toggles += 1

    def toggle_panel(self):
        self.menu_toggles += 1

    def _quick_start(self, minutes, agents_only=False):
        self.quick_starts.append((minutes, agents_only))

    def _stop_session(self):
        self.stop_calls += 1


class _PointerState:
    mask = 0


class _RootWindow:
    def get_device_position(self, pointer):
        return None, 0, 0, _PointerState.mask


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
    glib = types.SimpleNamespace(idle_add=lambda callback, *args: callback(*args))
    gtk = types.SimpleNamespace(main_quit=lambda: None)
    gdk = types.SimpleNamespace(
        Display=types.SimpleNamespace(
            get_default=lambda: types.SimpleNamespace(
                get_default_seat=lambda: types.SimpleNamespace(get_pointer=lambda: object())
            )
        ),
        get_default_root_window=lambda: _RootWindow(),
        ModifierType=types.SimpleNamespace(BUTTON3_MASK=4),
    )
    namespace = {
        "dbus": dbus,
        "GLib": glib,
        "Gtk": gtk,
        "Gdk": gdk,
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

    def test_right_click_returns_full_menu_without_opening_panel(self):
        menu, app = self.make_menu()
        _PointerState.mask = 4
        try:
            menu.AboutToShow(0)
            _revision, root = menu.GetLayout(0, -1, [])
        finally:
            _PointerState.mask = 0
        self.assertEqual(app.pointer_toggles, 0)
        self.assertEqual(len(root[2]), 10)

    def test_left_click_opens_panel_and_returns_empty_menu(self):
        menu, app = self.make_menu()
        menu.AboutToShow(0)
        _revision, root = menu.GetLayout(0, -1, [])
        self.assertEqual(app.pointer_toggles, 1)
        self.assertEqual(root[2], [])

    def test_layout_exposes_complete_visible_context_menu(self):
        menu, _app = self.make_menu()
        _PointerState.mask = 4
        try:
            _revision, root = menu.GetLayout(0, -1, [])
        finally:
            _PointerState.mask = 0
        children = root[2]
        labels = [child[1].get("label") for child in children]
        self.assertEqual(
            labels,
            [
                "Open Wick Panel", None,
                "Stay Awake: 30m", "Stay Awake: 1h", "Stay Awake: 2h",
                "Stay Awake: While Agents Run (--agents)", None,
                "Stop Sleep Inhibition", None, "Quit Wick",
            ],
        )
        self.assertTrue(all(child[1].get("visible", True) for child in children))

    def test_clicked_items_dispatch_actions(self):
        menu, app = self.make_menu()
        for item_id in (1, 3, 4, 5, 6, 8):
            menu.Event(item_id, "clicked", None, 0)
        self.assertEqual(app.menu_toggles, 1)
        self.assertEqual(
            app.quick_starts,
            [(30, False), (60, False), (120, False), (120, True)],
        )
        self.assertEqual(app.stop_calls, 1)


if __name__ == "__main__":
    unittest.main()
