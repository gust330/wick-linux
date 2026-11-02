"""Top bar indicator and floating panel matching macOS Wick.

Uses a native StatusNotifierItem over D-Bus (no AppIndicator3 dependency).
Left-click opens/closes the Wick panel right below the GNOME top bar.
Right-click opens a context menu.  Panel is positioned via Xwayland
override_redirect to bypass Mutter move restrictions on Wayland.
"""

from __future__ import annotations
from datetime import datetime, timezone
import glob
import math
import os
from pathlib import Path
import sys

# ---------------------------------------------------------------------------
# Environment setup — MUST happen before GTK/GDK is imported.
# Force GDK to use the Xwayland X11 backend so that window.move() works
# with override_redirect.
# ---------------------------------------------------------------------------
os.environ["GDK_BACKEND"] = "x11"

# Point XAUTHORITY at Mutter's Xwayland cookie
_xauth_matches = glob.glob("/run/user/1000/.mutter-Xwaylandauth.*")
if _xauth_matches:
    os.environ["XAUTHORITY"] = _xauth_matches[0]

if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"

if "XDG_RUNTIME_DIR" not in os.environ:
    os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"

# ---------------------------------------------------------------------------
# Now safe to import GTK / GDK
# ---------------------------------------------------------------------------
import gi
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkX11, GLib, Gtk

import dbus
import dbus.service
import dbus.mainloop.glib

from wick import agents, battery, core, durations, power, thermal
from wick.session import EndReason, Session, SessionStore, parse_iso

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
IDLE_ICON = str(ASSETS_DIR / "wick-idle.svg")
AWAKE_ICON = str(ASSETS_DIR / "wick-awake.svg")

# StatusNotifierItem icon helpers — stripped base names for the theme path
_ICON_IDLE = "wick-idle"
_ICON_AWAKE = "wick-awake"


def get_css() -> bytes:
    return b"""
    /* macOS Wick Night Instrument Theme */
    window.wick-window {
        background-color: transparent;
    }

    .wick-panel {
        background-color: #141211;
        border-radius: 24px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        box-shadow: 0 16px 36px rgba(0, 0, 0, 0.65);
        padding: 18px;
    }

    .wick-panel-awake {
        background-color: #141211;
        border-radius: 24px;
        border: 1px solid rgba(255, 138, 61, 0.35);
        box-shadow: 0 16px 36px rgba(0, 0, 0, 0.65), 0 0 24px rgba(255, 138, 61, 0.15);
        padding: 18px;
    }

    .wick-dot-idle {
        background-color: rgba(245, 242, 238, 0.35);
        border-radius: 9999px;
        min-width: 6px;
        min-height: 6px;
    }

    .wick-dot-awake {
        background-color: #ff8a3d;
        border-radius: 9999px;
        min-width: 6px;
        min-height: 6px;
        box-shadow: 0 0 8px #ff8a3d;
    }

    .wick-status-title {
        color: rgba(245, 242, 238, 0.62);
        font-size: 13px;
        font-weight: 500;
    }

    .wick-clock {
        color: #f5f2ee;
        font-size: 54px;
        font-weight: 300;
        font-family: monospace;
        letter-spacing: -1.5px;
    }

    .wick-caption {
        color: rgba(245, 242, 238, 0.55);
        font-size: 12px;
    }

    .wick-btn-play {
        background-color: #f5f2ee;
        color: #141211;
        border-radius: 9999px;
        border: none;
        font-size: 22px;
        font-weight: 800;
        min-width: 58px;
        min-height: 58px;
    }
    .wick-btn-play:hover {
        background-color: #ffffff;
    }

    .wick-btn-stop {
        background-color: #ff8a3d;
        color: #141211;
        border-radius: 9999px;
        border: none;
        font-size: 22px;
        font-weight: 800;
        min-width: 58px;
        min-height: 58px;
        box-shadow: 0 0 18px rgba(255, 138, 61, 0.55);
    }
    .wick-btn-stop:hover {
        background-color: #ff9d5c;
    }

    .wick-preset {
        background-color: transparent;
        color: rgba(245, 242, 238, 0.65);
        border: none;
        border-radius: 9999px;
        padding: 5px 10px;
        font-size: 12.5px;
        font-weight: 600;
    }
    .wick-preset:hover {
        background-color: rgba(255, 255, 255, 0.08);
        color: #f5f2ee;
    }
    .wick-preset-active {
        background-color: rgba(255, 255, 255, 0.14);
        color: #f5f2ee;
    }

    .wick-card {
        background-color: rgba(0, 0, 0, 0.32);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 14px;
        padding: 10px 14px;
    }

    .wick-card-title {
        color: #f5f2ee;
        font-size: 13px;
        font-weight: 500;
    }

    .wick-card-sub {
        color: rgba(245, 242, 238, 0.55);
        font-size: 11.5px;
    }

    .wick-slider trough {
        background-color: rgba(255, 255, 255, 0.10);
        border-radius: 4px;
        min-height: 4px;
    }
    .wick-slider highlight {
        background-color: #ff8a3d;
        border-radius: 4px;
    }
    .wick-slider slider {
        background-color: #f5f2ee;
        border-radius: 9999px;
        min-width: 14px;
        min-height: 14px;
    }
    """


class WickPanel(Gtk.Window):
    def __init__(self, indicator_owner: "WickApp", executable: str) -> None:
        super().__init__(type=Gtk.WindowType.POPUP)
        self.indicator_owner = indicator_owner
        self.executable = executable
        self.store = SessionStore()

        self.set_title("Wick")
        self.set_default_size(340, 480)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)

        # Enable true transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and self.is_composited():
            self.set_visual(visual)

        self.get_style_context().add_class("wick-window")

        self.selected_minutes = 120.0  # Default 2 hours
        self.is_forever = False
        self.stop_when_agents = True
        self.battery_floor = 20

        self.connect("key-press-event", self._on_key_press)
        self.connect("button-press-event", self._on_button_press)

        self._build_ui()
        self.update_state()

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self._dismiss()
            return True
        return False

    def _on_button_press(self, widget, event):
        """Hide if the click lands outside the panel's allocation."""
        alloc = self.get_allocation()
        if (event.x < 0 or event.y < 0 or
                event.x > alloc.width or event.y > alloc.height):
            self._dismiss()
            return True
        return False

    def _dismiss(self):
        """Un-grab and hide."""
        display = self.get_display()
        try:
            seat = display.get_default_seat()
            if seat:
                seat.ungrab()
        except Exception:
            try:
                Gdk.pointer_ungrab(Gdk.CURRENT_TIME)
                Gdk.keyboard_ungrab(Gdk.CURRENT_TIME)
            except Exception:
                pass
        self.hide()

    def show_at(self, x: int, y: int):
        """Show the panel at the given root coordinates and grab input."""
        self.update_state()
        self.realize()
        gdk_win = self.get_window()
        if gdk_win:
            try:
                gdk_win.set_override_redirect(True)
            except Exception:
                pass
        self.move(x, y)
        self.show_all()
        self.present()
        self.grab_focus()

        # Grab pointer+keyboard so clicks outside dismiss the panel
        gdk_win = self.get_window()
        if gdk_win:
            try:
                display = self.get_display()
                seat = display.get_default_seat()
                if seat:
                    seat.grab(
                        gdk_win,
                        Gdk.SeatCapabilities.ALL_POINTING | Gdk.SeatCapabilities.KEYBOARD,
                        True,   # owner_events — let our widgets receive their events
                        None,   # cursor
                        None,   # event
                        None, None,  # prepare_func, prepare_func_data
                    )
                else:
                    # Fallback to legacy grabs
                    Gdk.pointer_grab(
                        gdk_win, True,
                        Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK,
                        None, None, Gdk.CURRENT_TIME,
                    )
                    Gdk.keyboard_grab(gdk_win, True, Gdk.CURRENT_TIME)
            except Exception:
                pass

    def _build_ui(self):
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.main_box.get_style_context().add_class("wick-panel")
        self.add(self.main_box)

        # 1. Status row
        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status_dot = Gtk.Box()
        self.status_dot.set_valign(Gtk.Align.CENTER)
        self.status_dot.get_style_context().add_class("wick-dot-idle")

        self.status_label = Gtk.Label(label="Sleeps when the lid closes", xalign=0)
        self.status_label.set_hexpand(True)
        self.status_label.get_style_context().add_class("wick-status-title")

        close_btn = Gtk.Button(label="×")
        close_btn.get_style_context().add_class("wick-preset")
        close_btn.connect("clicked", lambda b: self._dismiss())

        status_row.pack_start(self.status_dot, False, False, 0)
        status_row.pack_start(self.status_label, True, True, 0)
        status_row.pack_end(close_btn, False, False, 0)
        self.main_box.pack_start(status_row, False, False, 0)

        # 2. Hero row (Clock + Main Play/Stop button)
        hero_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        clock_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        clock_box.set_hexpand(True)

        self.clock_label = Gtk.Label(label="2:00:00", xalign=0)
        self.clock_label.get_style_context().add_class("wick-clock")

        self.caption_label = Gtk.Label(label="until you stop it", xalign=0)
        self.caption_label.get_style_context().add_class("wick-caption")

        clock_box.pack_start(self.clock_label, False, False, 0)
        clock_box.pack_start(self.caption_label, False, False, 0)
        hero_row.pack_start(clock_box, True, True, 0)

        self.main_btn = Gtk.Button(label="▶")
        self.main_btn.set_valign(Gtk.Align.CENTER)
        self.main_btn.get_style_context().add_class("wick-btn-play")
        self.main_btn.connect("clicked", self._on_main_button_clicked)
        hero_row.pack_end(self.main_btn, False, False, 0)
        self.main_box.pack_start(hero_row, False, False, 0)

        # 3. Interactive Duration Slider
        slider_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.duration_adj = Gtk.Adjustment(value=120, lower=5, upper=480, step_increment=5, page_increment=30)
        self.slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.duration_adj)
        self.slider.set_draw_value(False)
        self.slider.get_style_context().add_class("wick-slider")
        self.slider.connect("value-changed", self._on_slider_changed)
        slider_box.pack_start(self.slider, False, False, 0)
        self.main_box.pack_start(slider_box, False, False, 0)

        # 4. Presets row
        presets_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        presets_row.set_halign(Gtk.Align.CENTER)
        self.preset_buttons = []
        preset_values = [("30m", 30), ("1h", 60), ("2h", 120), ("4h", 240), ("8h", 480), ("∞", 0)]
        for lbl, mins in preset_values:
            btn = Gtk.Button(label=lbl)
            btn.get_style_context().add_class("wick-preset")
            if mins == 120:
                btn.get_style_context().add_class("wick-preset-active")
            btn.connect("clicked", lambda b, m=mins: self._select_preset(m, b))
            presets_row.pack_start(btn, False, False, 0)
            self.preset_buttons.append((btn, mins))
        self.main_box.pack_start(presets_row, False, False, 0)

        # 5. Conditions card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("wick-card")

        # Agents row
        agent_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        agent_titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        agent_titles.set_hexpand(True)
        lbl_a1 = Gtk.Label(label="Stop when agents finish", xalign=0)
        lbl_a1.get_style_context().add_class("wick-card-title")
        self.lbl_agent_detail = Gtk.Label(label="No agents running", xalign=0)
        self.lbl_agent_detail.get_style_context().add_class("wick-card-sub")
        agent_titles.pack_start(lbl_a1, False, False, 0)
        agent_titles.pack_start(self.lbl_agent_detail, False, False, 0)

        self.agent_switch = Gtk.Switch()
        self.agent_switch.set_active(True)
        self.agent_switch.set_valign(Gtk.Align.CENTER)
        self.agent_switch.connect("notify::active", self._on_agent_switch_toggled)

        agent_box.pack_start(agent_titles, True, True, 0)
        agent_box.pack_end(self.agent_switch, False, False, 0)
        card.pack_start(agent_box, False, False, 0)

        # Divider
        divider = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        card.pack_start(divider, False, False, 2)

        # Battery / Thermal telemetry row
        bat_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bat_titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        bat_titles.set_hexpand(True)
        lbl_b1 = Gtk.Label(label="Battery & Thermal Guard", xalign=0)
        lbl_b1.get_style_context().add_class("wick-card-title")
        self.lbl_battery_detail = Gtk.Label(label="Battery: -- | Thermal: Normal", xalign=0)
        self.lbl_battery_detail.get_style_context().add_class("wick-card-sub")
        bat_titles.pack_start(lbl_b1, False, False, 0)
        bat_titles.pack_start(self.lbl_battery_detail, False, False, 0)

        self.floor_label = Gtk.Label(label="Floor: 20%")
        self.floor_label.get_style_context().add_class("wick-card-sub")

        bat_box.pack_start(bat_titles, True, True, 0)
        bat_box.pack_end(self.floor_label, False, False, 0)
        card.pack_start(bat_box, False, False, 0)

        self.main_box.pack_start(card, False, False, 0)

    def _select_preset(self, mins: float, btn: Gtk.Button):
        for b, _ in self.preset_buttons:
            b.get_style_context().remove_class("wick-preset-active")
        btn.get_style_context().add_class("wick-preset-active")

        if mins == 0:
            self.is_forever = True
            self.clock_label.set_text("∞")
            self.caption_label.set_text("until you stop it")
        else:
            self.is_forever = False
            self.selected_minutes = float(mins)
            self.duration_adj.set_value(mins)
            self.clock_label.set_text(durations.clock(mins * 60))
            self.caption_label.set_text(f"for {int(mins)}m")

    def _on_slider_changed(self, scale):
        val = round(self.duration_adj.get_value())
        self.is_forever = False
        self.selected_minutes = float(val)
        self.clock_label.set_text(durations.clock(val * 60))
        self.caption_label.set_text(f"for {val}m")

    def _on_agent_switch_toggled(self, switch, gparam):
        self.stop_when_agents = switch.get_active()

    def _on_main_button_clicked(self, btn):
        awake = power.sleep_disabled()
        if awake:
            core.Wick.stop(EndReason.STOPPED_BY_USER, store=self.store)
        else:
            ends_at_iso = None
            if not self.is_forever:
                now_dt = datetime.now(timezone.utc).timestamp() + (self.selected_minutes * 60.0)
                ends_at_iso = datetime.fromtimestamp(now_dt, timezone.utc).isoformat()

            session = Session(
                endsAt=ends_at_iso,
                untilAgentsFinish=self.stop_when_agents,
                batteryFloor=self.battery_floor,
            )
            core.Wick.start(session, executable=self.executable, store=self.store)

        self.update_state()
        self.indicator_owner.update_indicator()

    def update_state(self):
        core.Wick.reconcile(self.executable, store=self.store)
        awake = power.sleep_disabled()
        session = self.store.load()

        # Update telemetry
        bat = battery.Battery.current()
        if bat:
            st = "discharging" if bat.is_discharging else "plugged in"
            self.lbl_battery_detail.set_text(f"{bat.percent}%, {st} | Thermal: {'Critical' if thermal.is_overheating() else 'Normal'}")
        else:
            self.lbl_battery_detail.set_text(f"AC Power | Thermal: {'Critical' if thermal.is_overheating() else 'Normal'}")

        running_agents = agents.running()
        if running_agents:
            self.lbl_agent_detail.set_text(f"{', '.join(running_agents)} running")
        else:
            self.lbl_agent_detail.set_text("No agents running")

        ctx = self.main_box.get_style_context()
        dot_ctx = self.status_dot.get_style_context()
        btn_ctx = self.main_btn.get_style_context()

        if awake and session:
            ctx.remove_class("wick-panel")
            ctx.add_class("wick-panel-awake")
            dot_ctx.remove_class("wick-dot-idle")
            dot_ctx.add_class("wick-dot-awake")

            self.main_btn.set_label("■")
            btn_ctx.remove_class("wick-btn-play")
            btn_ctx.add_class("wick-btn-stop")

            now = datetime.now(timezone.utc)
            if session.endsAt:
                ends_dt = parse_iso(session.endsAt)
                if ends_dt:
                    rem = max(0.0, (ends_dt - now).total_seconds())
                    self.clock_label.set_text(durations.clock(rem))
                    self.caption_label.set_text(f"until {ends_dt.astimezone().strftime('%I:%M %p')}")
                    self.status_label.set_text(f"Awake with lid closed ({durations.compact(rem)} left)")
            else:
                self.clock_label.set_text("∞")
                self.caption_label.set_text("until you stop it")
                self.status_label.set_text("Awake with the lid closed")
        else:
            ctx.remove_class("wick-panel-awake")
            ctx.add_class("wick-panel")
            dot_ctx.remove_class("wick-dot-awake")
            dot_ctx.add_class("wick-dot-idle")

            self.main_btn.set_label("▶")
            btn_ctx.remove_class("wick-btn-stop")
            btn_ctx.add_class("wick-btn-play")

            self.status_label.set_text("Sleeps when the lid closes")
            if self.is_forever:
                self.clock_label.set_text("∞")
                self.caption_label.set_text("until you stop it")
            else:
                self.clock_label.set_text(durations.clock(self.selected_minutes * 60))
                self.caption_label.set_text(f"for {int(self.selected_minutes)}m")


# ---------------------------------------------------------------------------
# StatusNotifierItem D-Bus service
# ---------------------------------------------------------------------------

_SNI_IFACE = "org.kde.StatusNotifierItem"
_SNI_PATH = "/StatusNotifierItem"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_SNI_WATCHER_BUS = "org.kde.StatusNotifierWatcher"
_SNI_WATCHER_PATH = "/StatusNotifierWatcher"

_SNI_XML = f"""
<node>
  <interface name="{_SNI_IFACE}">
    <method name="Activate">
      <arg direction="in"  type="i" name="x"/>
      <arg direction="in"  type="i" name="y"/>
    </method>
    <method name="SecondaryActivate">
      <arg direction="in"  type="i" name="x"/>
      <arg direction="in"  type="i" name="y"/>
    </method>
    <method name="ContextMenu">
      <arg direction="in"  type="i" name="x"/>
      <arg direction="in"  type="i" name="y"/>
    </method>
    <method name="Scroll">
      <arg direction="in"  type="i" name="delta"/>
      <arg direction="in"  type="s" name="orientation"/>
    </method>
    <signal name="NewIcon"/>
    <signal name="NewTitle"/>
    <signal name="NewStatus">
      <arg type="s"/>
    </signal>
    <signal name="NewToolTip"/>
  </interface>
</node>
"""


class StatusNotifierItem(dbus.service.Object):
    """Minimal StatusNotifierItem exposing icon, Activate and ContextMenu."""

    def __init__(self, bus: dbus.Bus, bus_name: str, app: "WickApp"):
        self._app = app
        self._bus_name_str = bus_name
        self._icon_name = _ICON_IDLE
        self._title = "Wick"
        self._status = "Active"
        self._tooltip_title = "Wick: sleeps when lid closes"
        self._icon_theme_path = str(ASSETS_DIR)
        self._object_path = _SNI_PATH

        # Claim a well-known name for this item
        self._dbus_name = dbus.service.BusName(bus_name, bus)
        super().__init__(self._dbus_name, self._object_path)

    # ---- D-Bus methods (org.kde.StatusNotifierItem) ----

    @dbus.service.method(_SNI_IFACE, in_signature="ii")
    def Activate(self, x: int, y: int):
        """Left-click: toggle the panel right below the top bar."""
        GLib.idle_add(self._app.toggle_panel, int(x), int(y))

    @dbus.service.method(_SNI_IFACE, in_signature="ii")
    def SecondaryActivate(self, x: int, y: int):
        """Middle-click or secondary action: show context menu."""
        GLib.idle_add(self._app.show_context_menu, int(x), int(y))

    @dbus.service.method(_SNI_IFACE, in_signature="ii")
    def ContextMenu(self, x: int, y: int):
        """Right-click: show context menu."""
        GLib.idle_add(self._app.show_context_menu, int(x), int(y))

    @dbus.service.method(_SNI_IFACE, in_signature="is")
    def Scroll(self, delta: int, orientation: str):
        pass  # ignored

    # ---- Signals ----

    @dbus.service.signal(_SNI_IFACE)
    def NewIcon(self):
        pass

    @dbus.service.signal(_SNI_IFACE)
    def NewTitle(self):
        pass

    @dbus.service.signal(_SNI_IFACE, signature="s")
    def NewStatus(self, status: str):
        pass

    @dbus.service.signal(_SNI_IFACE)
    def NewToolTip(self):
        pass

    # ---- org.freedesktop.DBus.Properties ----

    @dbus.service.method(_PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface: str, prop: str):
        if interface != _SNI_IFACE:
            raise dbus.exceptions.DBusException(
                f"No such interface: {interface}",
                name="org.freedesktop.DBus.Error.UnknownInterface",
            )
        return self._get_prop(prop)

    @dbus.service.method(_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface: str):
        if interface != _SNI_IFACE:
            return dbus.Dictionary({}, signature="sv")
        props = {}
        for name in (
            "Category", "Id", "Title", "Status", "IconName",
            "IconThemePath", "ToolTip", "ItemIsMenu",
            "Menu",
        ):
            try:
                props[name] = self._get_prop(name)
            except Exception:
                pass
        return dbus.Dictionary(props, signature="sv")

    @dbus.service.method(_PROPS_IFACE, in_signature="ssv")
    def Set(self, interface: str, prop: str, value):
        pass  # read-only

    def _get_prop(self, name: str):
        _map = {
            "Category": dbus.String("ApplicationStatus"),
            "Id": dbus.String("wick-app"),
            "Title": dbus.String(self._title),
            "Status": dbus.String(self._status),
            "IconName": dbus.String(self._icon_name),
            "OverlayIconName": dbus.String(""),
            "AttentionIconName": dbus.String(""),
            "IconThemePath": dbus.String(self._icon_theme_path),
            "ItemIsMenu": dbus.Boolean(False),
            "Menu": dbus.ObjectPath("/NO_DBUSMENU"),
            "ToolTip": dbus.Struct(
                (dbus.String(self._icon_name),
                 dbus.Array([], signature="(iiay)"),
                 dbus.String(self._tooltip_title),
                 dbus.String("")),
                signature=None,
            ),
        }
        if name not in _map:
            raise dbus.exceptions.DBusException(
                f"No such property: {name}",
                name="org.freedesktop.DBus.Error.UnknownProperty",
            )
        return _map[name]

    # ---- Public helpers for the WickApp ----

    def set_icon(self, icon_name: str, tooltip: str):
        changed = self._icon_name != icon_name
        self._icon_name = icon_name
        self._tooltip_title = tooltip
        if changed:
            self.NewIcon()
            self.NewToolTip()

    def set_title(self, title: str):
        if title != self._title:
            self._title = title
            self.NewTitle()


class WickApp:
    def __init__(self, executable: str) -> None:
        self.executable = executable
        self.store = SessionStore()

        # Load styling
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(get_css())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Create panel window
        self.panel = WickPanel(self, executable)

        # --- D-Bus: StatusNotifierItem ----
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self._session_bus = dbus.SessionBus()

        self._sni_bus_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._sni = StatusNotifierItem(self._session_bus, self._sni_bus_name, self)

        # Register with the StatusNotifierWatcher
        try:
            watcher = self._session_bus.get_object(_SNI_WATCHER_BUS, _SNI_WATCHER_PATH)
            watcher.RegisterStatusNotifierItem(
                self._sni_bus_name,
                dbus_interface="org.kde.StatusNotifierWatcher",
            )
        except dbus.exceptions.DBusException:
            # Watcher might not be running yet; GNOME shell extension may
            # pick up the well-known name automatically.
            pass

        # Build context menu (right-click)
        self._build_context_menu()

        self.update_indicator()

        # Periodic refresh every 1 second
        GLib.timeout_add_seconds(1, self._on_tick)

    def _build_context_menu(self):
        self.menu = Gtk.Menu()

        item_toggle = Gtk.MenuItem(label="Toggle Wick Panel")
        item_toggle.connect("activate", lambda m: self.toggle_panel())
        self.menu.append(item_toggle)

        self.menu.append(Gtk.SeparatorMenuItem())

        for label, mins in [("Stay Awake: 30m", 30), ("Stay Awake: 1h", 60),
                            ("Stay Awake: 2h", 120), ("Stay Awake: Until Stopped (∞)", 0)]:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda m, minutes=mins: self._quick_start(minutes))
            self.menu.append(item)

        item_agents = Gtk.MenuItem(label="Stay Awake: While Agents Run (--agents)")
        item_agents.connect("activate", lambda m: self._quick_start(120, agents_only=True))
        self.menu.append(item_agents)

        self.menu.append(Gtk.SeparatorMenuItem())

        self.item_stop = Gtk.MenuItem(label="Stop Sleep Inhibition")
        self.item_stop.connect("activate", lambda m: self._stop_session())
        self.menu.append(self.item_stop)

        self.menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Quit Wick Background App")
        item_quit.connect("activate", lambda m: Gtk.main_quit())
        self.menu.append(item_quit)

        self.menu.show_all()

    def show_context_menu(self, x: int = 0, y: int = 0):
        """Pop up the right-click context menu."""
        self.menu.popup(None, None, None, None, 0, Gtk.get_current_event_time())

    def toggle_panel(self, click_x: int = 0, click_y: int = 0):
        """Toggle panel visibility.  (x, y) are the pointer coords from D-Bus Activate."""
        if self.panel.get_visible():
            self.panel._dismiss()
            return

        self.panel.update_state()

        # Calculate position right below the 36px GNOME top bar
        display = Gdk.Display.get_default()
        screen = Gdk.Screen.get_default()
        monitor_nr = 0
        if screen:
            monitor_nr = screen.get_primary_monitor()
            if monitor_nr < 0:
                monitor_nr = 0

        panel_width = 340
        # Get monitor geometry
        try:
            monitor = display.get_monitor(monitor_nr)
            geom = monitor.get_geometry()
        except Exception:
            # Fallback: use screen dimensions
            geom = type("G", (), {"x": 0, "y": 0,
                                   "width": screen.get_width() if screen else 1920,
                                   "height": screen.get_height() if screen else 1080})()

        # Default: right-align with some margin, but center on pointer if available
        if click_x > 0:
            target_x = click_x - panel_width // 2
        else:
            target_x = geom.x + geom.width - panel_width - 16

        min_x = geom.x + 12
        max_x = geom.x + geom.width - panel_width - 12
        x = max(min_x, min(target_x, max_x))
        y = geom.y + 36 + 4  # 4px below the 36px top bar

        self.panel.show_at(x, y)

    def _quick_start(self, minutes: int, agents_only: bool = False):
        ends_at_iso = None
        if minutes > 0 and not agents_only:
            now_dt = datetime.now(timezone.utc).timestamp() + (minutes * 60.0)
            ends_at_iso = datetime.fromtimestamp(now_dt, timezone.utc).isoformat()

        session = Session(
            endsAt=ends_at_iso,
            untilAgentsFinish=agents_only or self.panel.stop_when_agents,
            batteryFloor=20,
        )
        core.Wick.start(session, executable=self.executable, store=self.store)
        self.update_indicator()
        if self.panel.get_visible():
            self.panel.update_state()

    def _stop_session(self):
        core.Wick.stop(EndReason.STOPPED_BY_USER, store=self.store)
        self.update_indicator()
        if self.panel.get_visible():
            self.panel.update_state()

    def _on_tick(self):
        self.update_indicator()
        if self.panel.get_visible():
            self.panel.update_state()
        return True

    def update_indicator(self):
        core.Wick.reconcile(self.executable, store=self.store)
        awake = power.sleep_disabled()
        session = self.store.load()

        if awake and session:
            self._sni.set_icon(_ICON_AWAKE, "Wick: awake with lid closed")
            self.item_stop.set_sensitive(True)

            if session.endsAt:
                ends_dt = parse_iso(session.endsAt)
                if ends_dt:
                    now = datetime.now(timezone.utc)
                    rem = max(0.0, (ends_dt - now).total_seconds())
                    compact_str = durations.compact(rem)
                    self._sni.set_title(f"Wick — {compact_str}")
            else:
                self._sni.set_title("Wick — ON")
        else:
            self._sni.set_icon(_ICON_IDLE, "Wick: sleeps when lid closes")
            self._sni.set_title("Wick")
            self.item_stop.set_sensitive(False)

    def run(self):
        Gtk.main()


def launch_app(executable: str) -> None:
    app = WickApp(executable)
    app.run()


if __name__ == "__main__":
    launch_app(sys.argv[0])
