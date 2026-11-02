# A real Fedora desktop in your browser, with real systemd-logind: docker build, then run.sh. See README.
FROM fedora:42
RUN dnf -y -q install systemd polkit dbus-daemon dbus-x11 python3 python3-pip python3-gobject gtk3 libayatana-appindicator-gtk3 \
    gnome-shell gnome-console mesa-dri-drivers mesa-libGL glib2 dconf adwaita-icon-theme abattis-cantarell-fonts abattis-cantarell-vf-fonts \
    google-noto-sans-fonts dejavu-sans-fonts xorg-x11-server-Xvfb x11vnc novnc python3-websockify xdotool ImageMagick procps-ng util-linux shadow-utils >/dev/null
RUN useradd -m dev; systemctl mask getty@tty1.service console-getty.service systemd-firstboot.service systemd-homed.service \
    systemd-udevd.service systemd-udevd-kernel.socket systemd-udevd-control.socket systemd-udev-trigger.service systemd-udev-settle.service \
    systemd-networkd.service systemd-resolved.service gdm.service accounts-daemon.service upower.service geoclue.service >/dev/null 2>&1; true
COPY wick/ /opt/wick-src/
RUN python3 -m venv /opt/wick && /opt/wick/bin/pip -q install /opt/wick-src && ln -s /opt/wick/bin/wick /usr/local/bin/wick
# A pretend battery, because a container has none, so the panel can show that row. Everything else is real.
RUN mkdir -p /opt/fake-sys/class/power_supply/BAT0 && cd /opt/fake-sys/class/power_supply/BAT0 && \
    echo Battery > type && echo 62 > capacity && echo Discharging > status
# logind only allows the lock from an active local session, and this desktop has no seat, so it's allowed by rule here.
RUN mkdir -p /etc/polkit-1/rules.d && printf '%s\n' \
    'polkit.addRule(function(action, subject) {' \
    '  if (action.id.indexOf("org.freedesktop.login1.inhibit-") === 0 && subject.user === "dev") return polkit.Result.YES;' \
    '});' > /etc/polkit-1/rules.d/49-wick.rules
COPY coal.webp /tmp/coal.webp
RUN mkdir -p /usr/share/backgrounds && magick /tmp/coal.webp /usr/share/backgrounds/wick-coal.png
COPY start-desktop.sh /usr/local/bin/start-desktop.sh
COPY wick-preview.service /etc/systemd/system/wick-preview.service
RUN systemctl enable wick-preview.service >/dev/null 2>&1; loginctl enable-linger dev 2>/dev/null; mkdir -p /var/lib/systemd/linger && touch /var/lib/systemd/linger/dev
EXPOSE 6080
CMD ["/sbin/init"]
