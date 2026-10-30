#!/bin/bash
# Builds dist/Wick.app and dist/Wick-<version>.zip. Universal, and needs Xcode 26 for the Liquid Glass icon.
# Signs ad hoc by default. Set WICK_SIGN_IDENTITY to a Developer ID to sign for notarisation.
set -euo pipefail
cd "$(dirname "$0")/.."

version=$(sed -n 's/^public let wickVersion = "\(.*\)"/\1/p' Sources/WickCore/Durations.swift)
identity="${WICK_SIGN_IDENTITY:--}"
bundle_id="io.github.s1lvazxy.wick"
app="dist/Wick.app"

swift build -c release --arch arm64 --arch x86_64 --product wick
swift build -c release --arch arm64 --arch x86_64 --product WickApp
bin=".build/apple/Products/Release"

rm -rf dist
mkdir -p "$app/Contents/MacOS" "$app/Contents/Helpers" "$app/Contents/Resources"
cp "$bin/WickApp" "$app/Contents/MacOS/Wick"
cp "$bin/wick" "$app/Contents/Helpers/wick"

xcrun actool "$PWD/brand/Wick.icon" \
    --compile "$app/Contents/Resources" \
    --app-icon Wick \
    --enable-on-demand-resources NO \
    --platform macosx \
    --target-device mac \
    --minimum-deployment-target 14.0 \
    --include-all-app-icons \
    --output-partial-info-plist /dev/null >/dev/null

cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Wick</string>
    <key>CFBundleDisplayName</key><string>Wick</string>
    <key>CFBundleExecutable</key><string>Wick</string>
    <key>CFBundleIdentifier</key><string>$bundle_id</string>
    <key>CFBundleIconFile</key><string>Wick</string>
    <key>CFBundleIconName</key><string>Wick</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$version</string>
    <key>CFBundleVersion</key><string>$version</string>
    <key>LSMinimumSystemVersion</key><string>14.0</string>
    <key>LSUIElement</key><true/>
    <key>LSMultipleInstancesProhibited</key><true/>
    <key>NSHumanReadableCopyright</key><string>MIT License</string>
</dict>
</plist>
PLIST

options=()
[ "$identity" != "-" ] && options=(--options runtime --timestamp)
codesign --force ${options[@]+"${options[@]}"} --sign "$identity" --identifier "$bundle_id.cli" "$app/Contents/Helpers/wick"
codesign --force ${options[@]+"${options[@]}"} --sign "$identity" "$app"
codesign --verify --strict "$app"

ditto -c -k --keepParent "$app" "dist/Wick-$version.zip"
(cd dist && shasum -a 256 "Wick-$version.zip" > "Wick-$version.zip.sha256")
du -sh "$app" "dist/Wick-$version.zip"
