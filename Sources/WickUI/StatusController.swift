import AppKit
import SwiftUI
import WickCore

/// Owns the menu bar item and the panel that drops from it.
public final class StatusController: NSObject, NSWindowDelegate {
    private let model: WickModel
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    private let presentation = PanelPresentation()
    private lazy var panel = makePanel()
    private var clickMonitor: Any?
    private var orderOutTask: Task<Void, Never>?
    private var titleTimer: Timer?

    public init(model: WickModel) {
        self.model = model
        super.init()
        if let button = statusItem.button {
            button.target = self
            button.action = #selector(togglePanel)
            button.imagePosition = .imageLeading
        }
        model.statusDidChange = { [weak self] in self?.updateStatusItem() }
        updateStatusItem()
        // The title only changes minute to minute, so a once-a-minute-ish tick is plenty.
        let timer = Timer(timeInterval: 15, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.updateStatusItem() }
        }
        RunLoop.main.add(timer, forMode: .common)
        titleTimer = timer
    }

    private func updateStatusItem() {
        guard let button = statusItem.button else { return }
        button.image = WickGlyph.statusImage(isAwake: model.isAwake)

        var title = ""
        if model.showsTimeInMenuBar, let remaining = model.remaining(at: .now) {
            title = Durations.compact(remaining)
        }
        button.attributedTitle = NSAttributedString(
            string: title,
            attributes: [.font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .medium)]
        )
        button.toolTip = model.isAwake ? "Wick: awake with the lid closed" : "Wick"
    }

    // MARK: Panel

    // Room for the panel's shadow, which the window would otherwise clip.
    private static let windowSize = NSSize(width: Theme.panelWidth + 192, height: 680)
    private static let gapBelowMenuBar: CGFloat = 4

    private func makePanel() -> WickPanel {
        let panel = WickPanel(
            contentRect: NSRect(origin: .zero, size: Self.windowSize),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: true
        )
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.level = .popUpMenu
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient]
        panel.isMovable = false
        panel.appearance = NSAppearance(named: .darkAqua)
        panel.delegate = self
        panel.onCancel = { [weak self] in self?.closePanel() }

        let root = PanelRoot(model: model, presentation: presentation) { [weak self] in
            self?.closePanel()
        }
        panel.contentView = NSHostingView(rootView: root)
        return panel
    }

    @objc private func togglePanel() {
        presentation.isShown ? closePanel() : openPanel()
    }

    /// The real panel window, opened, for snapshots.
    public func openForSnapshot() -> NSWindow {
        openPanel()
        return panel
    }

    private func openPanel() {
        guard let button = statusItem.button, let buttonWindow = button.window else { return }
        orderOutTask?.cancel()

        let anchor = buttonWindow.convertToScreen(button.convert(button.bounds, to: nil))
        let screen = buttonWindow.screen ?? NSScreen.main
        var origin = NSPoint(
            x: anchor.midX - Self.windowSize.width / 2,
            y: anchor.minY - Self.gapBelowMenuBar - Self.windowSize.height
        )
        if let visible = screen?.visibleFrame {
            let inset = Theme.panelWidth / 2 + 8 - Self.windowSize.width / 2
            origin.x = origin.x.clamped(to: (visible.minX + inset)...(visible.maxX - inset - Self.windowSize.width))
        }
        panel.setFrame(NSRect(origin: origin, size: Self.windowSize), display: false)
        panel.makeKeyAndOrderFront(nil)
        statusItem.button?.highlight(true)

        presentation.isShown = true
        model.panelVisibilityChanged(true)

        clickMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
            MainActor.assumeIsolated { self?.closePanel() }
        }
    }

    private func closePanel() {
        guard presentation.isShown else { return }
        // The password dialog takes key focus. Staying open keeps the panel's context behind it.
        guard !model.isBusy else { return }
        presentation.isShown = false
        statusItem.button?.highlight(false)
        model.panelVisibilityChanged(false)

        if let clickMonitor { NSEvent.removeMonitor(clickMonitor) }
        clickMonitor = nil

        orderOutTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(140))
            guard !Task.isCancelled else { return }
            self?.panel.orderOut(nil)
        }
    }

    public func windowDidResignKey(_ notification: Notification) {
        closePanel()
    }
}

@Observable
final class PanelPresentation {
    var isShown = false
}

private struct PanelRoot: View {
    let model: WickModel
    let presentation: PanelPresentation
    let onDismiss: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reducesMotion

    var body: some View {
        ZStack(alignment: .top) {
            Color.clear
                .contentShape(.rect)
                .onTapGesture(perform: onDismiss)

            PanelView(model: model)
                .shadow(color: .black.opacity(0.45), radius: 28, y: 14)
                .shadow(color: .black.opacity(0.25), radius: 3, y: 1)
                // Grows out of the menu bar item it belongs to.
                .scaleEffect(presentation.isShown || reducesMotion ? 1 : 0.97, anchor: .top)
                .opacity(presentation.isShown ? 1 : 0)
                .animation(.easeOut(duration: presentation.isShown ? 0.16 : 0.11), value: presentation.isShown)
        }
    }
}

final class WickPanel: NSPanel {
    var onCancel: (() -> Void)?

    override var canBecomeKey: Bool { true }

    override func cancelOperation(_ sender: Any?) {
        onCancel?()
    }
}
