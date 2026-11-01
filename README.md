<p align="center">
  <img src="docs/hero.png" alt="Wick on Linux" width="860">
</p>

# Wick (Linux)

> **Close the lid. Keep working.**  
> A lightweight CLI and daemon that keeps your Linux laptop awake with the lid closed during coding agent sessions, builds, and downloads.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux%20%7C%20Fedora%20%7C%20systemd-orange.svg)](#)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](#)
[![Tests: E2E Passed](https://img.shields.io/badge/Tests-34%2F34%20Passing-brightgreen.svg)](#)

---

## Overview

On macOS, Wick wraps `pmset disablesleep` using a sudoers rule. On **Linux**, Wick is significantly safer, simpler, and requires **zero root or sudo permissions**:

- **Native `systemd-logind` inhibitor locks:** Acquires `handle-lid-switch:sleep:idle` block inhibitors over system D-Bus.
- **Kernel file-descriptor safety:** If the guard process terminates or is killed with `SIGKILL`, the Linux kernel automatically closes the file descriptor, and `systemd-logind` instantly restores normal sleep.
- **Coding agent awareness:** Actively scans `/proc` for running agents (`hermes`, `claude`, `aider`, `codex`, `opencode`, `cursor-agent`, `gemini`) and sleeps 90 seconds after they exit.
- **Battery floor protection:** Monitors `/sys/class/power_supply/BAT*` and restores sleep if discharging below 20% (or your configured floor).
- **Thermal runaway guard:** Monitors `/sys/class/thermal/` zones and trip points to prevent overheating inside closed bags or cramped spaces.

---

## Quick Install (Fedora / Linux)

### Option 1: Direct link / pipx

```sh
# Clone your fork
git clone https://github.com/gust330/wick-linux.git
cd wick-linux

# Symlink to ~/.local/bin or install via pipx
ln -sf $(pwd)/bin/wick ~/.local/bin/wick
```

### Option 2: Pip / Wheel

```sh
pip install .
```

### Option 3: Systemd User Service (Optional Autostart)

```sh
mkdir -p ~/.config/systemd/user
cp systemd/wick-guard.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable wick-guard.service
```

---

## CLI Usage

```sh
wick on 2h              # stay awake for 2 hours with the lid closed
wick on                 # stay awake until `wick off`
wick on --agents        # stay awake until active coding agents finish
wick on 8h --floor 30   # stop at 30% battery instead of default 20%
wick run hermes         # stay awake while one command runs
wick run ./build.sh     # stay awake for a build script
wick app                # start the top bar menu indicator & floating panel
wick off                # restore normal sleep immediately
wick status             # display active session countdown and triggers
wick status --json      # machine-readable telemetry
wick agents             # list detected active AI coding agents
wick doctor             # audit power, battery, thermal and logind status
```

---

## Top Bar & Visual UI (macOS Parity)

Wick on Linux provides the exact visual experience of the macOS menu bar app:

- **Top Bar Indicator (`wick app` or GNOME Shell Extension):**
  - **Idle State:** Shows the subtle unlit Wick candle mark in the system top panel.
  - **Awake State:** The candle mark turns into a glowing amber ember (`#FF8A3D`), accompanied by the live monospaced countdown clock in the top bar (e.g. `2h 05m`, `42m`, `<1m`, `∞`).
- **Floating Panel UI:**
  - Clicking the top bar item drops down a floating panel matching the original night instrument design.
  - **Hero Clock:** 54px light monospaced clock with dynamic relative time caption (*"until 11:30 PM"*, *"or agents finish"*).
  - **Circular Play/Stop Button:** 58px button with warm ember glow transition when engaged.
  - **Duration Slider & Presets:** Quick capsule buttons (`30m`, `1h`, `2h`, `4h`, `8h`, `∞`) and interactive slider.
  - **Conditions Card:** One-click toggle for coding agent awareness and live battery/thermal vitals.
- **GNOME Shell Extension:**
  - Included under `extensions/wick@gust330.github.io/` for native GNOME 45–50 top panel integration.

---

## Safety Guarantees

| Trigger | Behavior on Linux |
| --- | --- |
| **Time runs out** | Enforced by the background guard daemon. Holds open while commands under `wick run` execute. |
| **Battery floor** | Default 20% while on discharging battery. Configurable with `--floor <1-99>` or `--floor off`. |
| **Critical heat** | Ceases lid-wake inhibition if thermal zones report critical trip points or exceed 95°C. |
| **Agents finish** | Optional (`--agents`). Automatically shuts off 90s after the last detected coding agent finishes. |
| **Command exits** | With `wick run <cmd>`, inhibition is released the instant the command terminates. |
| **Crash / Reboot** | Kernel drops the lock immediately on exit/SIGKILL; next check reconciles state. |

---

## Linux Architecture

```
wick-linux/
├── bin/
│   └── wick                     # Main CLI executable
├── src/
│   └── wick/
│       ├── __init__.py
│       ├── cli.py               # CLI interface & argument parsing
│       ├── core.py              # Wick lifecycle orchestration
│       ├── power.py             # systemd-logind D-Bus inhibitor & fallback
│       ├── battery.py           # /sys/class/power_supply/BAT* reader
│       ├── thermal.py           # /sys/class/thermal/ zone monitoring
│       ├── agents.py            # /proc/[pid]/cmdline AI agent scanner
│       ├── durations.py         # 2h, 90m, 1h30m duration parser & clock
│       ├── session.py           # XDG state store, flock serialization
│       └── guard.py             # Background enforcement daemon
├── scripts/
│   ├── e2e_linux.sh             # Full 34-assertion end-to-end test suite
│   └── run_pty.py               # Pseudo-terminal harness for terminal tests
├── packaging/
│   └── wick.spec                # RPM specification for Fedora/RHEL
└── pyproject.toml               # Python packaging specification
```

---

## Verification & Tests

Wick includes an automated end-to-end test suite matching every original macOS specification against a simulated power harness:

```sh
./scripts/e2e_linux.sh
```

**Test Coverage:**
- Power toggles (`on`, `off`, `off --session-only`)
- Guard process concurrency mutex
- Timer expiration & clock formatting
- Crash safety (`SIGTERM` cleanup, `SIGKILL` orphan reconciliation)
- Terminal disconnect & SIGHUP survival
- External state alteration detection
- `wick run` exit code propagation & interactive PTY input/Ctrl-C forwarding
- Battery floor depletion safety triggers
- Critical thermal runaway triggers

---

## License

[MIT](LICENSE). Upstream macOS Wick by [s1lvazxy](https://github.com/s1lvazxy/wick). Linux port by [gust330](https://github.com/gust330).
