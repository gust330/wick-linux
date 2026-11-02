#!/bin/bash
# Loads the extension in a real GNOME Shell and asks the Shell what it thinks of it. X11 where GNOME still has it,
# and a headless Wayland session where it doesn't.
set -u
export HOME=/home/dev XDG_RUNTIME_DIR=/tmp/run-dev LIBGL_ALWAYS_SOFTWARE=1 XDG_CURRENT_DESKTOP=GNOME PATH=/home/dev/bin:$PATH
mkdir -p "$XDG_RUNTIME_DIR" /home/dev/bin; chmod 700 "$XDG_RUNTIME_DIR"
rm -rf /home/dev/wick-src; cp -r /src /home/dev/wick-src
ln -sf /home/dev/wick-src/wick-dev /home/dev/bin/wick
wick setup >/tmp/setup.log 2>&1
cat > /tmp/session.sh <<'SESSION'
gsettings set org.gnome.shell disable-user-extensions false
gsettings set org.gnome.shell enabled-extensions "['wick@s1lvazxy.github.io']"
if gnome-shell --help 2>&1 | grep -q -- '--x11'; then
    Xvfb :9 -screen 0 1280x800x24 +extension GLX >/dev/null 2>&1 &
    sleep 1
    DISPLAY=:9 XDG_SESSION_TYPE=x11 gnome-shell --x11 --replace --unsafe-mode >/tmp/shell.log 2>&1 &
else
    XDG_SESSION_TYPE=wayland gnome-shell --headless --wayland --virtual-monitor 1280x800 --unsafe-mode >/tmp/shell.log 2>&1 &
fi
shell=$!
ask() { gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell --method org.gnome.Shell.Extensions.GetExtensionInfo wick@s1lvazxy.github.io 2>&1; }
for _ in $(seq 1 45); do ask | grep -q "'state'" && break; sleep 1; done
# Long enough for it to poll `wick status --json` and paint a few times.
sleep 12
version=$(gnome-shell --version)
info=$(ask)
state=$(printf '%s' "$info" | sed -n "s/.*'state': <\([0-9.]*\)>.*/\1/p")
error=$(printf '%s' "$info" | sed -n "s/.*'error': <'\([^']*\)'>.*/\1/p")
complaints=$(grep -iE "wick" /tmp/shell.log | head -5 | cut -c1-220)
echo "$version: state=${state:-none} error=[$error]"
[ -n "$complaints" ] && echo "$complaints"
[ -n "$state" ] || { echo "no answer from the Shell: $(printf '%s' "$info" | cut -c1-200)"; tail -n 5 /tmp/shell.log | cut -c1-200; }
kill "$shell" 2>/dev/null
# State 1 is ACTIVE.
[ -z "$complaints" ] && { [ "$state" = "1" ] || [ "$state" = "1.0" ]; }
SESSION
exec dbus-run-session -- bash /tmp/session.sh
