"""Lightweight native GTK4 / Libadwaita desktop panel for Wick."""

from __future__ import annotations
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

# Ensure display environment variable under Wayland
if "WAYLAND_DISPLAY" not in os.environ and Path("/run/user/1000/wayland-0").exists():
    os.environ["WAYLAND_DISPLAY"] = "wayland-0"
if "XDG_RUNTIME_DIR" not in os.environ:
    os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"


def launch_gui(executable: str) -> None:
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gdk, GLib, Gtk
    except (ImportError, ValueError) as exc:
        print(f"wick: GUI dependencies not met ({exc}). Use 'wick on' and 'wick status' via CLI.", file=sys.stderr)
        sys.exit(1)

    from wick import agents, battery, core, durations, power, thermal
    from wick.session import EndReason, Session, SessionStore, parse_iso

    app = Adw.Application(application_id="io.github.gust330.wick")

    class WickWindow(Adw.ApplicationWindow):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.set_title("Wick")
            self.set_default_size(360, 480)
            self.set_resizable(False)

            self.store = SessionStore()
            self.selected_seconds = 7200.0  # Default 2h

            # Custom styling matching Wick's warm ember palette
            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(b"""
                window {
                    background-color: #0f1115;
                    color: #f5f2ee;
                }
                .hero-clock {
                    font-size: 42px;
                    font-weight: 800;
                    font-family: monospace;
                    color: #ff8a3d;
                }
                .status-sub {
                    font-size: 13px;
                    color: #a1a1aa;
                }
                .preset-btn {
                    border-radius: 9999px;
                    padding: 6px 14px;
                    font-weight: 600;
                }
                .action-btn-on {
                    background-color: #ff8a3d;
                    color: #0f1115;
                    font-weight: 700;
                    border-radius: 12px;
                    padding: 12px;
                }
                .action-btn-off {
                    background-color: #27272a;
                    color: #f5f2ee;
                    font-weight: 700;
                    border-radius: 12px;
                    padding: 12px;
                }
                .card-box {
                    background-color: #18181b;
                    border-radius: 12px;
                    padding: 12px;
                }
            """)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

            # Main container
            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            main_box.set_margin_top(20)
            main_box.set_margin_bottom(20)
            main_box.set_margin_start(20)
            main_box.set_margin_end(20)
            self.set_content(main_box)

            # Header / Status
            self.status_label = Gtk.Label(label="Sleeps when the lid closes")
            self.status_label.add_css_class("status-sub")
            main_box.append(self.status_label)

            # Hero Clock Display
            self.clock_label = Gtk.Label(label="2:00:00")
            self.clock_label.add_css_class("hero-clock")
            main_box.append(self.clock_label)

            # Presets row
            preset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            preset_box.set_halign(Gtk.Align.CENTER)
            presets = [("30m", 1800), ("1h", 3600), ("2h", 7200), ("4h", 14400), ("8h", 28800)]
            self.preset_buttons = []
            for label, secs in presets:
                btn = Gtk.Button(label=label)
                btn.add_css_class("preset-btn")
                btn.connect("clicked", lambda b, s=secs: self.select_duration(s))
                preset_box.append(btn)
                self.preset_buttons.append(btn)
            main_box.append(preset_box)

            # Options Card
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            card.add_css_class("card-box")

            # Agent toggle
            agent_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            agent_lbl = Gtk.Label(label="Stop when coding agents exit", xalign=0)
            agent_lbl.set_hexpand(True)
            self.agent_switch = Gtk.Switch()
            self.agent_switch.set_active(True)
            agent_row.append(agent_lbl)
            agent_row.append(self.agent_switch)
            card.append(agent_row)

            # Battery / Thermal telemetry
            self.telemetry_label = Gtk.Label(label="Battery: -- | Thermal: Normal", xalign=0)
            self.telemetry_label.add_css_class("status-sub")
            card.append(self.telemetry_label)

            main_box.append(card)

            # Action Button (Start / Stop)
            self.action_btn = Gtk.Button(label="Keep Awake")
            self.action_btn.add_css_class("action-btn-on")
            self.action_btn.connect("clicked", self.toggle_session)
            main_box.append(self.action_btn)

            # Timer tick every second
            GLib.timeout_add_seconds(1, self.tick)
            self.update_ui()

        def select_duration(self, seconds: float) -> None:
            self.selected_seconds = seconds
            self.clock_label.set_text(durations.clock(seconds))

        def toggle_session(self, btn) -> None:
            awake = power.sleep_disabled()
            if awake:
                core.Wick.stop(EndReason.STOPPED_BY_USER, store=self.store)
            else:
                now_dt = datetime.now(timezone.utc).timestamp() + self.selected_seconds
                ends_at = datetime.fromtimestamp(now_dt, timezone.utc).isoformat()
                session = Session(
                    endsAt=ends_at,
                    untilAgentsFinish=self.agent_switch.get_active(),
                    batteryFloor=20,
                )
                core.Wick.start(session, executable=executable, store=self.store)
            self.update_ui()

        def tick(self) -> bool:
            self.update_ui()
            return True

        def update_ui(self) -> None:
            core.Wick.reconcile(executable, store=self.store)
            awake = power.sleep_disabled()
            session = self.store.load()

            # Battery & thermal telemetry
            bat = battery.Battery.current()
            bat_str = f"{bat.percent}% ({'discharging' if bat.is_discharging else 'charging'})" if bat else "AC"
            therm_str = "Overheating!" if thermal.is_overheating() else "Normal"
            self.telemetry_label.set_text(f"Battery: {bat_str} | Thermal: {therm_str}")

            if awake and session:
                self.action_btn.set_label("Stop")
                self.action_btn.remove_css_class("action-btn-on")
                self.action_btn.add_css_class("action-btn-off")

                if session.endsAt:
                    ends_dt = parse_iso(session.endsAt)
                    if ends_dt:
                        now = datetime.now(timezone.utc)
                        rem = max(0.0, (ends_dt - now).total_seconds())
                        self.clock_label.set_text(durations.clock(rem))
                        self.status_label.set_text(f"Awake with lid closed ({durations.compact(rem)} left)")
                    else:
                        self.status_label.set_text("Awake with lid closed")
                else:
                    self.clock_label.set_text("∞")
                    self.status_label.set_text("Awake until stopped")
            else:
                self.action_btn.set_label("Keep Awake")
                self.action_btn.remove_css_class("action-btn-off")
                self.action_btn.add_css_class("action-btn-on")
                self.status_label.set_text("Sleeps when the lid closes")
                if not awake:
                    self.clock_label.set_text(durations.clock(self.selected_seconds))

    def on_activate(application):
        win = WickWindow(application=application)
        win.present()

    app.connect("activate", on_activate)
    app.run(None)
