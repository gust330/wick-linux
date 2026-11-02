import Foundation

public enum PowerError: Error, Equatable {
    case notAuthorized
    case commandFailed(String)
    case atBatteryFloor(percent: Int, floor: Int)

    public var sentence: String {
        switch self {
        case .notAuthorized:
            "no permission yet. Run `wick setup` first."
        case .commandFailed(let detail):
            detail
        case .atBatteryFloor(let percent, let floor):
            "the battery is at \(percent)%, at or below the \(floor)% floor, so Wick would stop straight away. Plug in, or set a lower floor."
        }
    }
}

/// Reads and writes the one setting Wick exists for: `pmset disablesleep`.
public enum Power {
    private static let pmset = "/usr/bin/pmset"
    private static let sudo = "/usr/bin/sudo"

    /// Replaces the real setting with a file, so scripts/e2e.sh can drive every path without root.
    private static let simulatedSetting = ProcessInfo.processInfo.environment["WICK_SIMULATE_POWER_FILE"]

    public static func sleepDisabled() -> Bool? {
        if let simulatedSetting {
            return (try? String(contentsOfFile: simulatedSetting, encoding: .utf8))?.hasPrefix("1") ?? false
        }
        let result = Shell.run(pmset, ["-g"])
        guard result.status == 0 else { return nil }
        return parseSleepDisabled(result.output)
    }

    /// macOS omits the line on some machines until the setting has been changed once, so absence means "off".
    static func parseSleepDisabled(_ output: String) -> Bool {
        for line in output.split(separator: "\n") {
            let fields = line.split(whereSeparator: \.isWhitespace)
            if fields.first == "SleepDisabled", let value = fields.last { return value == "1" }
        }
        return false
    }

    public static func setSleepDisabled(_ disabled: Bool) throws(PowerError) {
        if let simulatedSetting {
            do {
                try (disabled ? "1" : "0").write(toFile: simulatedSetting, atomically: true, encoding: .utf8)
                return
            } catch {
                throw .commandFailed(error.localizedDescription)
            }
        }
        // -k ignores a cached password. The guard has no terminal and no ticket, so a change that only
        // works thanks to one would turn sleep off and then be unable to turn it back on.
        let result = Shell.run(sudo, ["-k", "-n", pmset, "-a", "disablesleep", disabled ? "1" : "0"])
        guard result.status == 0 else {
            if result.output.contains("password is required") { throw .notAuthorized }
            throw .commandFailed(result.output.trimmingCharacters(in: .whitespacesAndNewlines))
        }
    }

    /// Asks sudo whether the command would be allowed without a password, without running it.
    public static var isAuthorized: Bool {
        if simulatedSetting != nil { return true }
        return Shell.run(sudo, ["-k", "-n", "-l", pmset, "-a", "disablesleep", "1"]).status == 0
    }
}

enum Shell {
    struct Result {
        var status: Int32
        var output: String
    }

    static func run(_ path: String, _ arguments: [String]) -> Result {
        let process = Process()
        process.executableURL = URL(filePath: path)
        process.arguments = arguments
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        process.standardInput = FileHandle.nullDevice
        do {
            try process.run()
        } catch {
            return Result(status: -1, output: error.localizedDescription)
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return Result(status: process.terminationStatus, output: String(decoding: data, as: UTF8.self))
    }
}
