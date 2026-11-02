"""What `wick setup` adds to the desktop, and how to allow the lock without an active local session."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

ASSETS = Path(__file__).resolve().parent / "assets"
EXTENSION_UUID = "wick@s1lvazxy.github.io"
LAUNCHER = "io.github.s1lvazxy.wick.desktop"


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _polkit_reads_javascript() -> bool:
    """polkit only gained JavaScript rules in 0.106. Older releases, like Ubuntu 22.04's, silently ignore them."""
    tool = shutil.which("pkaction")
    if tool is None:
        return True
    try:
        output = subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=5).stdout
        minor = re.search(r"(\d+)\.(\d+)", output)
    except (OSError, subprocess.SubprocessError):
        return True
    return minor is None or (int(minor.group(1)), int(minor.group(2))) >= (0, 106)


def polkit_rule_command() -> str:
    """logind only allows the lid lock from an active local session. This is the supported way to widen that."""
    user = os.environ.get("USER") or "your-user"
    if _polkit_reads_javascript():
        return (
            "cat > /etc/polkit-1/rules.d/49-wick.rules <<'RULE'\n"
            "polkit.addRule(function(action, subject) {\n"
            '  if (action.id.indexOf("org.freedesktop.login1.inhibit-") === 0 && '
            f'subject.user === "{user}") return polkit.Result.YES;\n'
            "});\n"
            "RULE"
        )
    return (
        "cat > /etc/polkit-1/localauthority/50-local.d/49-wick.pkla <<'RULE'\n"
        "[Wick]\n"
        f"Identity=unix-user:{user}\n"
        "Action=org.freedesktop.login1.inhibit-*\n"
        "ResultAny=yes\n"
        "RULE"
    )


def tray_dependencies_hint() -> str:
    return (
        "The top bar app needs GTK 3 and an AppIndicator library.\n"
        "  Fedora:         sudo dnf install python3-gobject gtk3 libayatana-appindicator-gtk3\n"
        "  Debian, Ubuntu: sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1\n"
        "  Arch:           sudo pacman -S python-gobject gtk3 libayatana-appindicator\n"
        "On GNOME, the extension from `wick setup` doesn't need any of this."
    )


def install_launcher(executable: str) -> str:
    """With absolute paths: launchers run without ~/.local/bin on PATH, which is where pipx puts wick, and a desktop
    hides an entry whose program it can't find."""
    target = _data_home() / "applications" / LAUNCHER
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = (ASSETS / LAUNCHER).read_text(encoding="utf-8")
    entry = entry.replace("Exec=wick app", f'Exec="{executable}" app')
    entry = entry.replace("Icon=wick", f"Icon={ASSETS / 'wick-awake.svg'}")
    target.write_text(entry, encoding="utf-8")
    return f"App launcher: added at {target}."


def is_gnome() -> bool:
    return "gnome" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


def install_gnome_extension() -> str:
    if not is_gnome():
        return "GNOME extension: skipped, this isn't GNOME. Use `wick app` for the top bar icon."

    target = _data_home() / "gnome-shell" / "extensions" / EXTENSION_UUID
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(ASSETS / EXTENSION_UUID, target)

    enable = shutil.which("gnome-extensions")
    if enable:
        result = subprocess.run([enable, "enable", EXTENSION_UUID], capture_output=True, text=True)
        if result.returncode == 0:
            return "GNOME extension: added and enabled."
    # GNOME Shell only scans for new extensions when it starts.
    return f"GNOME extension: added. Log out and back in, then run: gnome-extensions enable {EXTENSION_UUID}"


def uninstall() -> str:
    removed = []
    launcher = _data_home() / "applications" / LAUNCHER
    if launcher.exists():
        launcher.unlink()
        removed.append("the app launcher")

    extension = _data_home() / "gnome-shell" / "extensions" / EXTENSION_UUID
    if extension.exists():
        tool = shutil.which("gnome-extensions")
        if tool:
            subprocess.run([tool, "disable", EXTENSION_UUID], capture_output=True)
        shutil.rmtree(extension)
        removed.append("the GNOME extension")

    done = f"Removed {' and '.join(removed)}." if removed else "Nothing to remove."
    return f"{done} Wick needs no system changes on Linux, so nothing else is left behind."
