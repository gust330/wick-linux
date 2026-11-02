#!/bin/bash
# Checks the extension loads in real GNOME Shell releases. Needs Docker.
# Usage: run.sh [ubuntu:24.04 (GNOME 46) | fedora:42 (48) | fedora:latest (50) ...]
set -u
cd "$(dirname "$0")/../.."
status=0
for base in ${*:-ubuntu:24.04 fedora:42 fedora:latest}; do
    tag="wick-gnome:$(echo "$base" | tr ':/' '--')"
    name="wick-gnome-$$"
    docker build -q --build-arg "BASE=$base" -t "$tag" tests/gnome >/dev/null || exit 1
    docker run -d --rm --name "$name" --privileged --cgroupns=private --tmpfs /run --tmpfs /tmp -v "$PWD:/src:ro" "$tag" >/dev/null || exit 1
    for _ in $(seq 1 60); do
        docker exec "$name" systemctl is-system-running 2>/dev/null | grep -qE 'running|degraded' && break
        sleep 0.5
    done
    output=$(docker exec "$name" timeout 150 su dev -s /bin/bash -c 'bash /src/tests/gnome/inside.sh' 2>&1)
    code=$?
    printf '%s\n' "$output" | grep -E '^GNOME Shell|wick|no answer|Error|error' | grep -vE 'dbus-daemon|^$' | head -12 | cut -c1-230
    echo "exit $code"
    [ "$code" = 0 ] || status=1
    docker rm -f "$name" >/dev/null
done
exit "$status"
