#!/bin/bash
# Starts the preview and prints where to open it. Needs Docker. Stop it with: docker rm -f wick-preview
set -e
cd "$(dirname "$0")"
context=$(mktemp -d)
trap 'rm -rf "$context"' EXIT
cp Dockerfile start-desktop.sh wick-preview.service "$context/"
mkdir "$context/wick"
cp -r ../src ../pyproject.toml ../README.md "$context/wick/"
cp ../../site/public/coal.webp "$context/"
docker build -q -t wick-preview "$context" >/dev/null
docker rm -f wick-preview >/dev/null 2>&1 || true
docker run -d --name wick-preview --privileged --cgroupns=private --tmpfs /run --tmpfs /tmp -p 127.0.0.1:6080:6080 wick-preview >/dev/null
echo "Open http://localhost:6080/vnc.html?autoconnect=1&resize=scale"
