import AppKit
import WickUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let model = WickModel()
    private var statusController: StatusController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusController = StatusController(model: model)
        model.beginRefreshing()
    }

    func applicationWillTerminate(_ notification: Notification) {
        model.stopForQuit()
    }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.setActivationPolicy(.accessory)
application.run()
