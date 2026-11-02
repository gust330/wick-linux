#!/bin/bash
# Runs the real-logind tests in containers with systemd as PID 1. Needs Docker.
# Usage: run.sh [fedora:42 | ubuntu:24.04 | debian:13 ...]. With no arguments, Fedora only.
set -u
cd "$(dirname "$0")/../../.."
root=$PWD
status=0
for base in "${@:-fedora:42}"; do
    case "$base" in
        fedora*) file=Dockerfile.fedora ;;
        *) file=Dockerfile.debian ;;
    esac
    tag="wick-logind:$(echo "$base" | tr ':/' '--')"
    name="wick-logind-$$"
    echo "=== $base"
    docker build -q --build-arg "BASE=$base" -t "$tag" -f "linux/tests/logind/$file" linux/tests/logind >/dev/null || exit 1
    docker run -d --rm --name "$name" --privileged --cgroupns=private \
        --tmpfs /run --tmpfs /tmp -v "$root/linux:/src:ro" "$tag" >/dev/null || exit 1
    for _ in $(seq 1 60); do
        docker exec "$name" systemctl is-system-running 2>/dev/null | grep -qE 'running|degraded' && break
        sleep 0.5
    done
    # A watchdog, because a hang here should fail the run and not wait forever.
    docker exec "$name" perl -e 'alarm 1200; exec @ARGV' bash /src/tests/logind/inside.sh
    code=$?
    [ "$code" = 0 ] || status=1
    docker rm -f "$name" >/dev/null
done
exit "$status"
