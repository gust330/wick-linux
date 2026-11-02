ARG BASE=fedora:42
FROM ${BASE}
RUN if command -v dnf >/dev/null; then \
      dnf -y -q install gnome-shell mesa-dri-drivers dbus-daemon python3 glib2 procps-ng shadow-utils systemd polkit xorg-x11-server-Xvfb >/dev/null; \
    else \
      apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends gnome-shell gnome-shell-common libgl1-mesa-dri dbus dbus-user-session python3 procps libglib2.0-bin dconf-gsettings-backend systemd systemd-sysv polkitd xvfb >/dev/null; \
    fi; useradd -m dev; true
# udevd in a privileged container would act on the devices of the machine it runs on.
RUN systemctl mask getty@tty1.service console-getty.service systemd-firstboot.service systemd-homed.service systemd-udevd.service systemd-udevd-kernel.socket systemd-udevd-control.socket systemd-udev-trigger.service systemd-udev-settle.service systemd-networkd.service systemd-resolved.service gdm.service >/dev/null 2>&1; true
CMD ["/sbin/init"]
