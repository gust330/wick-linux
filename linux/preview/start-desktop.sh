#!/bin/bash
# GNOME Shell on a virtual screen, shown through noVNC.
export DISPLAY=:1 XDG_SESSION_TYPE=x11 XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_DESKTOP=gnome GDK_BACKEND=x11 HOME=/home/dev
export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe NO_AT_BRIDGE=1 WICK_SYSFS_ROOT=/opt/fake-sys
export PATH=/usr/local/bin:/usr/bin:/bin
cd "$HOME"

Xvfb :1 -screen 0 1280x800x24 +extension GLX +render -noreset &
sleep 1
x11vnc -display :1 -forever -shared -nopw -quiet -rfbport 5900 -bg -o /tmp/x11vnc.log
websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/novnc.log 2>&1 &

exec dbus-run-session -- bash -c '
    gsettings set org.gnome.shell disable-user-extensions false
    gsettings set org.gnome.shell enabled-extensions "[\"wick@s1lvazxy.github.io\"]"
    gsettings set org.gnome.shell welcome-dialog-last-shown-version "999"
    gsettings set org.gnome.desktop.interface color-scheme prefer-dark
    gsettings set org.gnome.desktop.background picture-uri-dark file:///usr/share/backgrounds/wick-coal.png
    gsettings set org.gnome.desktop.background picture-uri file:///usr/share/backgrounds/wick-coal.png
    gsettings set org.gnome.desktop.interface clock-show-seconds false
    gsettings set org.gnome.desktop.session idle-delay 0
    gsettings set org.gnome.desktop.screensaver lock-enabled false
    wick setup > /tmp/wick-setup.log 2>&1
    gnome-shell --x11 --replace > /tmp/gnome-shell.log 2>&1 &
    shell=$!
    sleep 6
    # A pretend agent, so the panel has one to find.
    bash -c "exec -a claude sleep 86400" &
    # GNOME opens on the overview. Close it, to show the desktop.
    xdotool key --clearmodifiers Escape
    wait $shell
'
