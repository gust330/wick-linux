cask "wick" do
  version "0.1.0"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"

  url "https://github.com/s1lvazxy/wick/releases/download/v#{version}/Wick-#{version}.zip"
  name "Wick"
  desc "Keeps the computer awake with the lid closed"
  homepage "https://github.com/s1lvazxy/wick"

  depends_on macos: :sonoma

  app "Wick.app"
  binary "#{appdir}/Wick.app/Contents/Helpers/wick"

  # Remove this block once releases are signed with a Developer ID and notarised.
  # Without one, Gatekeeper refuses to open the app at all.
  postflight_steps do
    run "/usr/bin/xattr", args: ["-dr", "com.apple.quarantine", "{{appdir}}/Wick.app"]
  end

  # These also run on `brew upgrade`, so the permission rule isn't removed here: an upgrade shouldn't
  # cost a password prompt. The rule stays until `wick uninstall` or `brew uninstall --zap`.
  uninstall launchctl: "io.github.s1lvazxy.wick.guard",
            quit:      "io.github.s1lvazxy.wick"

  zap delete: "/private/etc/sudoers.d/wick",
      trash:  [
        "~/Library/Application Support/Wick",
        "~/Library/LaunchAgents/io.github.s1lvazxy.wick.guard.plist",
        "~/Library/Preferences/io.github.s1lvazxy.wick.plist",
      ]
end
