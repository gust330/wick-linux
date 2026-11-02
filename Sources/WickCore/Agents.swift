import Darwin
import Foundation

/// Finds coding agents from their command line. Process names alone miss most of them: Claude Code's binary is
/// named after its version (`2.1.312`), and agents installed through npm or pip run as `node` or `python`.
public enum Agents {
    static let known: [String: String] = [
        "aider": "Aider",
        "amp": "Amp",
        "claude": "Claude Code",
        "codex": "Codex",
        "cursor-agent": "Cursor Agent",
        "droid": "Droid",
        "gemini": "Gemini CLI",
        "goose": "Goose",
        "hermes": "Hermes Agent",
        "hermes-agent": "Hermes Agent",
        "opencode": "OpenCode",
        "qwen": "Qwen Code",
    ]

    private static let interpreters: Set<String> = ["node", "bun", "deno", "python", "python3"]

    /// Display names of the agents running right now, sorted and without duplicates.
    public static func running() -> [String] {
        var names = Set<String>()
        for pid in allPIDs() {
            guard let processName = name(of: pid) else { continue }
            if let agent = match(processName: processName, arguments: arguments(of: pid)) { names.insert(agent) }
        }
        return names.sorted()
    }

    static func match(processName: String, arguments: [String]) -> String? {
        if let agent = known[processName] { return agent }
        guard let first = arguments.first else { return nil }
        let invokedAs = URL(filePath: first).lastPathComponent
        if let agent = known[invokedAs] { return agent }
        guard interpreters.contains(processName), arguments.count > 1 else { return nil }
        let script = URL(filePath: arguments[1]).lastPathComponent
        return known[script] ?? known[script.replacingOccurrences(of: ".js", with: "")]
    }

    private static func allPIDs() -> [pid_t] {
        let capacity = proc_listallpids(nil, 0)
        guard capacity > 0 else { return [] }
        var pids = [pid_t](repeating: 0, count: Int(capacity) + 32)
        let count = proc_listallpids(&pids, Int32(pids.count * MemoryLayout<pid_t>.size))
        return count > 0 ? Array(pids.prefix(Int(count))) : []
    }

    private static func name(of pid: pid_t) -> String? {
        var buffer = [CChar](repeating: 0, count: 256)
        guard proc_name(pid, &buffer, UInt32(buffer.count)) > 0 else { return nil }
        return String(decoding: buffer.prefix { $0 != 0 }.map(UInt8.init(bitPattern:)), as: UTF8.self)
    }

    /// Layout of KERN_PROCARGS2: an Int32 argc, the executable path, NUL padding, then argv.
    private static func arguments(of pid: pid_t) -> [String] {
        var query = [CTL_KERN, KERN_PROCARGS2, pid]
        var size = 0
        guard sysctl(&query, 3, nil, &size, nil, 0) == 0, size > 4 else { return [] }
        var bytes = [UInt8](repeating: 0, count: size)
        guard sysctl(&query, 3, &bytes, &size, nil, 0) == 0, size > 4 else { return [] }

        let argc = bytes.withUnsafeBytes { Int($0.loadUnaligned(as: Int32.self)) }
        var index = 4
        while index < size, bytes[index] != 0 { index += 1 }
        while index < size, bytes[index] == 0 { index += 1 }

        var arguments: [String] = []
        while index < size, arguments.count < argc {
            let start = index
            while index < size, bytes[index] != 0 { index += 1 }
            arguments.append(String(decoding: bytes[start..<index], as: UTF8.self))
            index += 1
        }
        return arguments
    }
}
