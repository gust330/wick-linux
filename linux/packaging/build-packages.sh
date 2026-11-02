#!/bin/bash
# Builds the wheel, the sdist and the RPM into linux/dist. Run on Fedora.
set -euo pipefail
cd "$(dirname "$0")/.."
dnf -y -q install rpm-build rpmdevtools python3-devel python3-pip python3-setuptools python3-wheel pyproject-rpm-macros tar gzip >/dev/null
version=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)

rm -rf dist
python3 -m pip -q install build
python3 -m build --outdir dist . >/dev/null

top=$(mktemp -d)
mkdir -p "$top/SOURCES" "$top/SPECS"
# RPM expects the source to unpack into wick-<version>, whatever pip called it.
staging=$(mktemp -d)
cp -r . "$staging/wick-$version"
rm -rf "$staging/wick-$version/dist" "$staging/wick-$version/build"
tar -czf "$top/SOURCES/wick-$version.tar.gz" -C "$staging" "wick-$version"
rpmbuild --define "_topdir $top" -bb packaging/wick.spec >/dev/null
find "$top/RPMS" -name '*.rpm' -exec cp {} dist/ \;
(cd dist && sha256sum ./* > SHA256SUMS)
ls -la dist
