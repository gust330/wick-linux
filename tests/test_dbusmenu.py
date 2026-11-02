"""Regression tests for the tray companion's DBusMenu contract."""

import ast
from pathlib import Path
import types
import unittest


class _Object:
    def __init__(self, *args, **kwargs):
        pass


def _method(*args, **kwargs):
    return lambda function: function


class _App:
    def __init__(self):
        self.panel_toggles = []
        self.quick_starts = []
        self.stop_calls = 0

    def toggle_panel(self, *coords):
        self.panel_toggles.append(coords)

    def toggle_panel_at_pointer(self):
        self.panel_toggles.append(("pointer",))

    def _quick_start(self, minutes, agents_only=False):
        self.quick_starts.append((minutes, agents_only))

    def _stop_session(self):
        self.stop_calls += 1


def _namespace():
    dbus = types.SimpleNamespace(
        service=types.SimpleNamespace(
            Object=_Object,
            method=_method,
            signal=_method,
            BusName=lambda name, bus: object(),
        ),
        Boolean=bool,
        String=str,
        UInt32=int,
        Int32=int,
        ObjectPath=str,
        Array=lambda values=(), **kwargs: list(values),
        Dictionary=lambda values=(), **kwargs: dict(values),
        Struct=lambda values=(), **kwargs: tuple(values),
        exceptions=types.SimpleNamespace(DBusException=Exception),
    )
    return {
        "dbus": dbus,
        "GLib": types.SimpleNamespace(idle_add=lambda callback, *args: callback(*args)),
        "Gtk": types.SimpleNamespace(main_quit=lambda: None),
        "_DBUSMENU_IFACE": "com.canonical.dbusmenu",
        "_DBUSMENU_PATH": "/MenuBar",
        "_DBUSMENU_PROPS_IFACE": "org.freedesktop.DBus.Properties",
        "_SNI_IFACE": "org.kde.StatusNotifierItem",
        "_SNI_PATH": "/StatusNotifierItem",
        "_PROPS_IFACE": "org.freedesktop.DBus.Properties",
        "ASSETS_DIR": Path("."),
        "_ICON_IDLE": "wick-idle",
        "_icon_pixmap": lambda name: [],
        "_is_right_click": lambda: False,
        "WickApp": _App,
    }


def _load_class(name):
    source = Path(__file__).parents[1] / "src/wick/tray.py"
    tree = ast.parse(source.read_text())
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == name)
    namespace = _namespace()
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    return namespace[name]


class DBusMenuTests(unittest.TestCase):
    def make_menu(self):
        app = _App()
        return _load_class("DBusMenu")(object(), app), app

    def test_about_to_show_returns_false_without_side_effects(self):
        menu, app = self.make_menu()
        self.assertFalse(menu.AboutToShow(0))
        self.assertEqual(app.panel_toggles, [])

    def test_root_open_event_never_opens_panel(self):
        menu, app = self.make_menu()
        menu.Event(0, "opened", None, 0)
        self.assertEqual(app.panel_toggles, [])

    def test_layout_exposes_complete_visible_context_menu(self):
        menu, _app = self.make_menu()
        _revision, root = menu.GetLayout(0, -1, [])
        children = root[2]
        self.assertEqual([child[0] for child in children], list(range(1, 11)))
        self.assertEqual(
            [child[1].get("label") for child in children],
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
        self.assertEqual(app.panel_toggles, [()])
        self.assertEqual(
            app.quick_starts,
            [(30, False), (60, False), (120, False), (120, True)],
        )
        self.assertEqual(app.stop_calls, 1)

    def test_about_to_show_group_returns_empty(self):
        menu, app = self.make_menu()
        updates, errors = menu.AboutToShowGroup([0, 1])
        self.assertEqual((updates, errors), ([], []))
        self.assertEqual(app.panel_toggles, [])

    def test_event_group_dispatches_clicked_items_only(self):
        menu, app = self.make_menu()
        menu.EventGroup([(0, "opened", None, 0), (3, "clicked", None, 0)])
        self.assertEqual(app.panel_toggles, [])
        self.assertEqual(app.quick_starts, [(30, False)])


class StatusNotifierItemTests(unittest.TestCase):
    def test_activate_toggles_panel_at_supplied_coordinates(self):
        app = _App()
        item = _load_class("StatusNotifierItem")(object(), "org.example.Wick", app)
        item.Activate(123, 45)
        self.assertEqual(app.panel_toggles, [(123, 45)])


class NoSyntheticInputTests(unittest.TestCase):
    def test_tray_has_no_xtest_or_synthetic_key_events(self):
        source = (Path(__file__).parents[1] / "src/wick/tray.py").read_text()
        for forbidden in ("libXtst", "XTestFakeKeyEvent", "_dismiss_shell_menu"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
