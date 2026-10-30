import Foundation

public enum AccessError: Error, Equatable {
    case cancelled
    case failed(String)
}

/// Installs the sudoers rule that lets Wick flip `disablesleep` without a password.
///
/// A rule rather than a privileged helper: it works without an Apple Developer ID, it is one
/// auditable line, and it cannot do anything except the two exact commands it names.
public enum Access {
    public static let rulePath = "/private/etc/sudoers.d/wick"

    public static func rule(user: String = NSUserName(), uid: uid_t = getuid()) -> String {
        """
        # Added by Wick. Remove with: wick uninstall
        \(sudoersUser(user, uid: uid)) ALL=(root) NOPASSWD: /usr/bin/pmset -a disablesleep 0, /usr/bin/pmset -a disablesleep 1

        """
    }

    /// Short names are nearly always safe to write verbatim. Anything else falls back to the numeric form,
    /// so nothing from the environment can inject sudoers syntax.
    static func sudoersUser(_ user: String, uid: uid_t) -> String {
        user.wholeMatch(of: /[A-Za-z_][A-Za-z0-9_.-]*/) != nil ? user : "#\(uid)"
    }

    /// Validates with visudo before installing: a broken file in sudoers.d can lock an admin out of sudo.
    static func installScript(rule: String) -> String {
        """
        set -eu
        tmp=$(/usr/bin/mktemp /tmp/wick-sudoers.XXXXXX)
        trap '/bin/rm -f "$tmp"' EXIT
        /bin/cat > "$tmp" <<'WICK_RULE'
        \(rule)WICK_RULE
        /usr/sbin/visudo -cqf "$tmp"
        /bin/mkdir -p /private/etc/sudoers.d
        /usr/bin/install -o root -g wheel -m 0440 "$tmp" \(rulePath)
        """
    }

    /// One script, so a cancelled password prompt changes nothing at all.
    static func removeScript(restoringSleep: Bool) -> String {
        let remove = "/bin/rm -f \(rulePath)"
        return restoringSleep ? "/usr/bin/pmset -a disablesleep 0; \(remove)" : remove
    }

    static func appleScript(running script: String, prompt: String) -> String {
        "do shell script \(quoted(script)) with prompt \(quoted(prompt)) with administrator privileges"
    }

    private static func quoted(_ text: String) -> String {
        let escaped = text
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        return "\"\(escaped)\""
    }

    public static func install() throws(AccessError) {
        try runAsAdmin(
            installScript(rule: rule()),
            prompt: "Wick needs your password once to control sleep with the lid closed."
        )
        guard Power.isAuthorized else {
            throw .failed("The rule was installed but sudo does not honour it. Check that /etc/sudoers includes sudoers.d.")
        }
    }

    /// Removes the rule and the background job. With a session running, that has to end it too, because
    /// without the rule nothing could turn sleep back on afterwards.
    public static func remove(store: SessionStore = SessionStore()) throws(AccessError) {
        let hadSession = store.load() != nil
        try runAsAdmin(
            removeScript(restoringSleep: hadSession),
            prompt: "Wick needs your password to remove its permission."
        )
        if hadSession { store.finish(.stoppedByUser) }
        GuardAgent.remove()
    }

    private static func runAsAdmin(_ script: String, prompt: String) throws(AccessError) {
        let result = Shell.run("/usr/bin/osascript", ["-e", appleScript(running: script, prompt: prompt)])
        guard result.status == 0 else {
            if result.output.contains("-128") { throw .cancelled }
            throw .failed(result.output.trimmingCharacters(in: .whitespacesAndNewlines))
        }
    }
}
