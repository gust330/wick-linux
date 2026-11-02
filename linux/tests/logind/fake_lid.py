#!/usr/bin/env python3
"""A virtual laptop lid. Creates a real kernel input device with a lid switch, which logind treats like the real thing.

Usage: fake_lid.py <control file> <device name>
Then write "close" or "open" to the control file. Linux only, and needs /dev/uinput.
"""

import fcntl
import os
from pathlib import Path
import struct
import sys
import time

EV_SYN, EV_SW = 0, 5
SW_LID = 0
UI_SET_EVBIT = 0x40045564
UI_SET_SWBIT = 0x4004556D
UI_DEV_SETUP = 0x405C5503
UI_DEV_CREATE = 0x5501
BUS_VIRTUAL = 6


def send(device, kind, code, value):
    os.write(device, struct.pack("llHHi", 0, 0, kind, code, value))


def set_lid(device, closed):
    send(device, EV_SW, SW_LID, 1 if closed else 0)
    send(device, EV_SYN, 0, 0)


def main():
    control = Path(sys.argv[1])
    device = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(device, UI_SET_EVBIT, EV_SW)
    fcntl.ioctl(device, UI_SET_SWBIT, SW_LID)
    identity = struct.pack("HHHH", BUS_VIRTUAL, 0x1234, 0x5678, 1)
    fcntl.ioctl(device, UI_DEV_SETUP, identity + sys.argv[2].encode()[:79].ljust(80, b"\0") + struct.pack("I", 0))
    fcntl.ioctl(device, UI_DEV_CREATE)
    print("lid device created", flush=True)

    control.write_text("open", encoding="utf-8")
    last = "open"
    while True:
        wanted = control.read_text(encoding="utf-8").strip()
        if wanted == "quit":
            return
        if wanted != last and wanted in ("open", "close"):
            set_lid(device, wanted == "close")
            last = wanted
        time.sleep(0.05)


if __name__ == "__main__":
    main()
