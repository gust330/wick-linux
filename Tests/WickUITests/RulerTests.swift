import AppKit
import Testing
@testable import WickUI

/// Drives the ruler with real NSEvents, so tracking, rubber-banding and snapping run as they do in the app.
@Suite struct `Ruler interaction` {
    final class Harness {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 340, height: 44), styleMask: .borderless, backing: .buffered, defer: false)
        let ruler = RulerNSView()
        var commits: [Double] = []
        var scrubs: [Double] = []
        var settles = 0

        init(minutes: Double = 120) {
            ruler.frame = window.contentLayoutRect
            window.contentView = ruler
            ruler.jump(to: minutes)
            ruler.onCommit = { [unowned self] in commits.append($0) }
            ruler.onScrub = { [unowned self] in scrubs.append($0) }
            ruler.onSettle = { [unowned self] in settles += 1 }
        }

        func event(_ type: NSEvent.EventType, x: CGFloat, time: TimeInterval) -> NSEvent {
            NSEvent.mouseEvent(
                with: type, location: NSPoint(x: x, y: 22), modifierFlags: [], timestamp: time,
                windowNumber: window.windowNumber, context: nil, eventNumber: 0, clickCount: 1, pressure: 1
            )!
        }

        /// Slow enough that momentum projection adds nothing.
        func drag(from start: CGFloat, to end: CGFloat) {
            ruler.mouseDown(with: event(.leftMouseDown, x: start, time: 100))
            ruler.mouseDragged(with: event(.leftMouseDragged, x: end, time: 110))
            ruler.mouseUp(with: event(.leftMouseUp, x: end, time: 120))
        }
    }

    @Test func `tracks the pointer one to one while dragging`() {
        let harness = Harness()
        harness.ruler.mouseDown(with: harness.event(.leftMouseDown, x: 170, time: 100))
        harness.ruler.mouseDragged(with: harness.event(.leftMouseDragged, x: 100, time: 100.1))
        // 70 points at 7 points per 5 minutes is 50 minutes, and dragging left raises the value.
        #expect(abs(harness.ruler.value - 170) < 0.001)
    }

    @Test func `shows the drag on the time display as it happens`() {
        let harness = Harness()
        harness.ruler.mouseDown(with: harness.event(.leftMouseDown, x: 170, time: 100))
        harness.ruler.mouseDragged(with: harness.event(.leftMouseDragged, x: 100, time: 100.1))
        #expect(harness.scrubs.last == 170)
    }

    @Test func `commits to a five minute step on release`() {
        let harness = Harness()
        harness.drag(from: 170, to: 97)
        let committed = harness.commits.last ?? 0
        #expect(committed.truncatingRemainder(dividingBy: 5) == 0)
        #expect(abs(committed - 170) <= 5)
    }

    @Test func `a flick lands further than the release point`() {
        let harness = Harness()
        harness.ruler.mouseDown(with: harness.event(.leftMouseDown, x: 200, time: 100))
        harness.ruler.mouseDragged(with: harness.event(.leftMouseDragged, x: 180, time: 100.02))
        harness.ruler.mouseDragged(with: harness.event(.leftMouseDragged, x: 160, time: 100.04))
        harness.ruler.mouseUp(with: harness.event(.leftMouseUp, x: 160, time: 100.05))
        // 40 points of drag is about 29 minutes. At 1000 pt/s the projection adds several hundred points more.
        #expect((harness.commits.last ?? 0) > 120 + 100)
    }

    @Test func `holding still before release adds no momentum`() {
        let harness = Harness()
        harness.ruler.mouseDown(with: harness.event(.leftMouseDown, x: 200, time: 100))
        harness.ruler.mouseDragged(with: harness.event(.leftMouseDragged, x: 180, time: 100.02))
        harness.ruler.mouseDragged(with: harness.event(.leftMouseDragged, x: 160, time: 100.04))
        harness.ruler.mouseUp(with: harness.event(.leftMouseUp, x: 160, time: 100.5))
        // 40 points of drag is about 29 minutes, and nothing more.
        #expect(abs((harness.commits.last ?? 0) - 150) <= 5)
    }

    @Test func `resists past the ends instead of stopping dead`() {
        let harness = Harness(minutes: 700)
        harness.ruler.mouseDown(with: harness.event(.leftMouseDown, x: 300, time: 100))
        harness.ruler.mouseDragged(with: harness.event(.leftMouseDragged, x: 0, time: 100.1))
        // 300 points raw would be 914 minutes.
        #expect(harness.ruler.value > 720)
        #expect(harness.ruler.value < 760)
    }

    @Test func `never commits outside the range`() {
        let high = Harness(minutes: 715)
        high.drag(from: 300, to: 10)
        #expect(high.commits.last == 720)

        let low = Harness(minutes: 10)
        low.drag(from: 10, to: 300)
        #expect(low.commits.last == 5)
    }

    @Test func `a click moves to the tick under the pointer`() {
        let harness = Harness()
        harness.ruler.mouseDown(with: harness.event(.leftMouseDown, x: 170 + 70, time: 100))
        harness.ruler.mouseUp(with: harness.event(.leftMouseUp, x: 170 + 70, time: 100.05))
        #expect(harness.commits.last == 170)
    }

    @Test func `a countdown tick cannot fight a drag`() {
        let harness = Harness()
        harness.ruler.mouseDown(with: harness.event(.leftMouseDown, x: 170, time: 100))
        harness.ruler.mouseDragged(with: harness.event(.leftMouseDragged, x: 100, time: 100.1))
        harness.ruler.show(119)
        #expect(abs(harness.ruler.value - 170) < 0.001)
    }

    @Test func `arrow keys step without animating`() {
        let harness = Harness()
        harness.ruler.keyDown(with: NSEvent.keyEvent(
            with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0, windowNumber: 0, context: nil,
            characters: String(UnicodeScalar(NSEvent.SpecialKey.rightArrow.rawValue)!),
            charactersIgnoringModifiers: String(UnicodeScalar(NSEvent.SpecialKey.rightArrow.rawValue)!),
            isARepeat: false, keyCode: 124
        )!)
        #expect(harness.ruler.value == 125)
        #expect(harness.commits.last == 125)
    }

    @Test func `countdown updates apply directly`() {
        let harness = Harness()
        harness.ruler.show(119.98)
        #expect(harness.ruler.value == 119.98)
    }
}
