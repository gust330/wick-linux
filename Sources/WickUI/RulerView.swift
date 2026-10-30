import AppKit
import SwiftUI

/// The duration control, and the wick itself: ticks left of the needle are the time still to burn.
struct RulerView: NSViewRepresentable {
    var minutes: Double
    var isBurning: Bool
    var isOpenEnded: Bool
    var onScrub: (Double) -> Void
    var onCommit: (Double) -> Void
    var onSettle: () -> Void

    func makeNSView(context: Context) -> RulerNSView {
        let view = RulerNSView()
        view.jump(to: minutes)
        return view
    }

    func updateNSView(_ view: RulerNSView, context: Context) {
        view.onScrub = onScrub
        view.onCommit = onCommit
        view.onSettle = onSettle
        view.isBurning = isBurning
        view.isOpenEnded = isOpenEnded
        view.show(minutes)
    }
}

final class RulerNSView: NSView {
    var onScrub: ((Double) -> Void)?
    var onCommit: ((Double) -> Void)?
    var onSettle: (() -> Void)?

    var isBurning = false { didSet { if isBurning != oldValue { needsDisplay = true } } }
    var isOpenEnded = false { didSet { if isOpenEnded != oldValue { needsDisplay = true } } }

    private static let step = 5.0
    private static let spacing: CGFloat = 7
    private static let bounds = WickModel.minimumMinutes...WickModel.maximumMinutes
    private static let pointsPerMinute = Double(spacing) / step
    /// Apple's scroll-deceleration projection, from Designing Fluid Interfaces.
    private static let deceleration = 0.998
    private static let springResponse = 0.32

    private(set) var value = 120.0
    private var velocity = 0.0
    private(set) var target = 120.0
    private var link: CADisplayLink?
    private var lastFrame: CFTimeInterval = 0
    private var lastScrubbed = 120.0

    private var isTracking = false
    private var ownsMotion = false
    private var trackingStartX: CGFloat = 0
    private var trackingStartValue = 0.0
    private var didDrag = false
    private var samples: [(time: TimeInterval, x: CGFloat)] = []
    private let edgeFade = CAGradientLayer()
    private let haptics = NSHapticFeedbackManager.defaultPerformer

    private var reducesMotion: Bool { NSWorkspace.shared.accessibilityDisplayShouldReduceMotion }

    init() {
        super.init(frame: .zero)
        wantsLayer = true
        layerContentsRedrawPolicy = .onSetNeedsDisplay
        edgeFade.startPoint = CGPoint(x: 0, y: 0.5)
        edgeFade.endPoint = CGPoint(x: 1, y: 0.5)
        edgeFade.colors = [NSColor.clear, .black, .black, .clear].map(\.cgColor)
        edgeFade.locations = [0, 0.14, 0.86, 1]
        layer?.mask = edgeFade
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func layout() {
        super.layout()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        edgeFade.frame = layer?.bounds ?? .zero
        CATransaction.commit()
    }

    override func resetCursorRects() {
        addCursorRect(bounds, cursor: .resizeLeftRight)
    }

    // MARK: External updates

    func jump(to minutes: Double) {
        value = minutes
        target = minutes
        velocity = 0
        needsDisplay = true
    }

    /// Model-driven changes. Ignored while the user owns the motion, so a countdown tick can't fight a drag.
    func show(_ minutes: Double) {
        guard !ownsMotion, abs(minutes - target) > 0.0001 else { return }
        if abs(minutes - value) < 1 || reducesMotion {
            stopLink()
            jump(to: minutes)
        } else {
            target = minutes
            startLink()
        }
    }

    // MARK: Drawing

    override func draw(_ dirtyRect: NSRect) {
        guard let context = NSGraphicsContext.current?.cgContext else { return }
        let width = bounds.width
        let height = bounds.height
        let center = width / 2
        let midY = height / 2
        let scale = window?.backingScaleFactor ?? 2
        let hairline = 1 / scale

        let litColor = isBurning
            ? NSColor(srgbRed: 1, green: 0.76, blue: 0.48, alpha: 1)
            : NSColor(srgbRed: 0.96, green: 0.95, blue: 0.93, alpha: 0.72)
        let unlitColor = NSColor(srgbRed: 0.96, green: 0.95, blue: 0.93, alpha: 0.2)

        // Open-ended sessions have no length, so every tick stays unlit.
        let firstTick = max(0, Int(((value - Double(center) / Self.pointsPerMinute) / Self.step).rounded(.down)))
        let lastTick = min(
            Int(Self.bounds.upperBound / Self.step),
            Int(((value + Double(center) / Self.pointsPerMinute) / Self.step).rounded(.up))
        )
        guard firstTick <= lastTick else { return }

        for tick in firstTick...lastTick {
            let minute = Double(tick) * Self.step
            let x = center + CGFloat((minute - value) * Self.pointsPerMinute)
            let isHour = tick % 12 == 0
            let isHalf = tick % 6 == 0
            let tickHeight: CGFloat = isHour ? 26 : (isHalf ? 18 : 12)
            let isLit = !isOpenEnded && minute <= value + 0.001
            context.setFillColor((isLit ? litColor : unlitColor).cgColor)
            let tickWidth: CGFloat = isHour ? 1.5 : max(1, hairline * 2)
            let snappedX = (x * scale).rounded() / scale
            context.fill(CGRect(x: snappedX - tickWidth / 2, y: midY - tickHeight / 2, width: tickWidth, height: tickHeight))
        }

        drawNeedle(in: context, x: center, midY: midY)
    }

    private func drawNeedle(in context: CGContext, x: CGFloat, midY: CGFloat) {
        let rect = CGRect(x: x - 1, y: midY - 18, width: 2, height: 36)
        let needle = CGPath(roundedRect: rect, cornerWidth: 1, cornerHeight: 1, transform: nil)
        context.saveGState()
        if isBurning {
            context.setShadow(
                offset: .zero,
                blur: 10,
                color: NSColor(srgbRed: 1, green: 0.54, blue: 0.24, alpha: 0.95).cgColor
            )
            context.setFillColor(NSColor(srgbRed: 1, green: 0.54, blue: 0.24, alpha: 1).cgColor)
        } else {
            context.setFillColor(NSColor(srgbRed: 0.96, green: 0.95, blue: 0.93, alpha: 1).cgColor)
        }
        context.addPath(needle)
        context.fillPath()
        context.restoreGState()
    }

    // MARK: Mouse

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        stopLink()
        isTracking = true
        ownsMotion = true
        didDrag = false
        velocity = 0
        let x = convert(event.locationInWindow, from: nil).x
        trackingStartX = x
        trackingStartValue = value
        samples = [(event.timestamp, x)]
    }

    override func mouseDragged(with event: NSEvent) {
        let x = convert(event.locationInWindow, from: nil).x
        if !didDrag, abs(x - trackingStartX) < 2 { return }
        didDrag = true
        samples.append((event.timestamp, x))
        samples.removeAll { event.timestamp - $0.time > 0.1 }

        let dragged = trackingStartValue - Double(x - trackingStartX) / Self.pointsPerMinute
        setValue(rubberBanded(dragged))
    }

    override func mouseUp(with event: NSEvent) {
        isTracking = false
        guard didDrag else {
            let x = convert(event.locationInWindow, from: nil).x
            let clicked = value + Double(x - bounds.midX) / Self.pointsPerMinute
            settle(toward: clicked, releaseVelocity: 0)
            return
        }
        // Only recent movement counts: holding still before letting go must not throw the ruler.
        samples.removeAll { event.timestamp - $0.time > 0.1 }
        let pointsPerSecond: Double
        if let first = samples.first, let last = samples.last, last.time > first.time {
            pointsPerSecond = Double(last.x - first.x) / (last.time - first.time)
        } else {
            pointsPerSecond = 0
        }
        // Moving the ruler right lowers the value.
        let releaseVelocity = -pointsPerSecond / Self.pointsPerMinute
        let projected = value + (releaseVelocity / 1000) * Self.deceleration / (1 - Self.deceleration)
        settle(toward: projected, releaseVelocity: releaseVelocity)
    }

    // MARK: Trackpad and wheel

    override func scrollWheel(with event: NSEvent) {
        if !event.hasPreciseScrollingDeltas {
            let notches = event.scrollingDeltaY != 0 ? event.scrollingDeltaY : event.scrollingDeltaX
            guard notches != 0 else { return }
            ownsMotion = true
            settle(toward: target + (notches > 0 ? Self.step : -Self.step), releaseVelocity: 0)
            return
        }

        // The system's own momentum phase is ignored: projection below owns that part of the motion.
        guard event.momentumPhase == [] else { return }
        let delta = abs(event.scrollingDeltaX) >= abs(event.scrollingDeltaY) ? event.scrollingDeltaX : event.scrollingDeltaY

        switch event.phase {
        case .began, .mayBegin:
            stopLink()
            ownsMotion = true
            isTracking = true
            velocity = 0
            samples = []
        case .changed:
            let dragged = value - Double(delta) / Self.pointsPerMinute
            setValue(rubberBanded(dragged))
            samples.append((event.timestamp, delta))
            samples.removeAll { event.timestamp - $0.time > 0.1 }
        case .ended, .cancelled:
            isTracking = false
            samples.removeAll { event.timestamp - $0.time > 0.1 }
            let elapsed = (samples.last?.time ?? 0) - (samples.first?.time ?? 0)
            let travelled = samples.reduce(0) { $0 + Double($1.x) }
            let pointsPerSecond = elapsed > 0 ? travelled / elapsed : 0
            let releaseVelocity = -pointsPerSecond / Self.pointsPerMinute
            let projected = value + (releaseVelocity / 1000) * Self.deceleration / (1 - Self.deceleration)
            settle(toward: projected, releaseVelocity: releaseVelocity)
        default:
            break
        }
    }

    // MARK: Keyboard

    override func keyDown(with event: NSEvent) {
        switch event.specialKey {
        case .leftArrow, .downArrow: nudge(by: -Self.step)
        case .rightArrow, .upArrow: nudge(by: Self.step)
        default: super.keyDown(with: event)
        }
    }

    /// Keyboard changes apply at once: animating them would only make repeat-key feel slow.
    private func nudge(by amount: Double) {
        let next = (target + amount).clamped(to: Self.bounds)
        stopLink()
        jump(to: next)
        onCommit?(next)
        onSettle?()
    }

    // MARK: Motion

    private func settle(toward destination: Double, releaseVelocity: Double) {
        let snapped = ((destination / Self.step).rounded() * Self.step).clamped(to: Self.bounds)
        target = snapped
        velocity = releaseVelocity
        onCommit?(snapped)
        if reducesMotion {
            jump(to: snapped)
            finishMotion()
        } else {
            startLink()
        }
    }

    private func setValue(_ next: Double) {
        let crossedHour = floor(value / 60) != floor(next / 60)
        value = next
        needsDisplay = true
        if crossedHour { haptics.perform(.alignment, performanceTime: .now) }
        let stepped = (next / Self.step).rounded() * Self.step
        let shown = stepped.clamped(to: Self.bounds)
        if shown != lastScrubbed {
            lastScrubbed = shown
            onScrub?(shown)
        }
    }

    /// Past either end the ruler slows progressively instead of stopping dead.
    private func rubberBanded(_ raw: Double) -> Double {
        let range = Self.bounds
        let overshoot: Double
        if raw < range.lowerBound {
            overshoot = raw - range.lowerBound
        } else if raw > range.upperBound {
            overshoot = raw - range.upperBound
        } else {
            return raw
        }
        let dimension = 60.0
        let constant = 0.55
        let resisted = (overshoot * dimension * constant) / (dimension + constant * abs(overshoot))
        return (overshoot < 0 ? range.lowerBound : range.upperBound) + resisted
    }

    private func startLink() {
        guard link == nil else { return }
        lastFrame = 0
        let link = displayLink(target: self, selector: #selector(frame(_:)))
        link.add(to: .main, forMode: .common)
        self.link = link
    }

    private func stopLink() {
        link?.invalidate()
        link = nil
    }

    /// A critically damped spring, integrated by hand so a press can read the real on-screen value
    /// and interrupt it. The value and velocity carry straight through every retarget.
    @objc private func frame(_ link: CADisplayLink) {
        let now = link.timestamp
        let elapsed = lastFrame == 0 ? 1.0 / 60 : min(now - lastFrame, 1.0 / 30)
        lastFrame = now

        let omega = 2 * Double.pi / Self.springResponse
        let acceleration = -omega * omega * (value - target) - 2 * omega * velocity
        velocity += acceleration * elapsed
        setValue(value + velocity * elapsed)

        if abs(value - target) < 0.02, abs(velocity) < 0.2 {
            stopLink()
            jump(to: target)
            finishMotion()
        }
    }

    private func finishMotion() {
        guard ownsMotion, !isTracking else { return }
        ownsMotion = false
        haptics.perform(.alignment, performanceTime: .now)
        onSettle?()
    }

    // MARK: Accessibility

    override func isAccessibilityElement() -> Bool { true }
    override func accessibilityRole() -> NSAccessibility.Role? { .slider }
    override func accessibilityLabel() -> String? { "Duration" }

    override func accessibilityValue() -> Any? {
        isOpenEnded ? "Until you stop it" : Durations_.spoken(minutes: target)
    }

    override func accessibilityPerformIncrement() -> Bool {
        nudge(by: Self.step)
        return true
    }

    override func accessibilityPerformDecrement() -> Bool {
        nudge(by: -Self.step)
        return true
    }
}

enum Durations_ {
    static func spoken(minutes: Double) -> String {
        Duration.seconds(minutes * 60).formatted(.units(allowed: [.hours, .minutes], width: .wide))
    }
}

extension Comparable {
    func clamped(to range: ClosedRange<Self>) -> Self {
        min(max(self, range.lowerBound), range.upperBound)
    }
}
