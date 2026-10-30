import AppKit
import SwiftUI

/// Wick is a night instrument: warm near-black, and one colour that means "burning".
/// Ember is reserved for the awake state, so seeing it anywhere is the status.
enum Theme {
    static let canvas = Color(hex: 0x141211)
    static let ember = Color(hex: 0xFF8A3D)
    static let emberHot = Color(hex: 0xFFC27A)
    static let emberDeep = Color(hex: 0xD9421A)
    static let paper = Color(hex: 0xF5F2EE)
    static let soot = Color(hex: 0x1A1412)

    static let textPrimary = paper
    static let textSecondary = paper.opacity(0.62)
    static let textTertiary = paper.opacity(0.40)
    static let hairline = Color.white.opacity(0.10)
    static let raised = Color.white.opacity(0.06)

    static let panelWidth: CGFloat = 340
    static let panelRadius: CGFloat = 24
    static let panelInset: CGFloat = 10
    /// Concentric with the panel: outer radius minus the inset between them.
    static let cardRadius: CGFloat = panelRadius - panelInset

    static let pressDuration: Double = 0.1
}

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double(hex >> 16 & 0xFF) / 255,
            green: Double(hex >> 8 & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}

/// The Wick mark: a laptop with its lid just ajar, seen from the side, and the ember still lit inside.
/// Drawn on a 24-unit grid. `brand/logo/mark-mono.svg` is the same geometry.
public enum WickGlyph {
    public static func statusImage(isAwake: Bool) -> NSImage {
        let image = NSImage(size: NSSize(width: 18, height: 18), flipped: true) { _ in
            NSGraphicsContext.current?.cgContext.scaleBy(x: 18.0 / 24.0, y: 18.0 / 24.0)
            NSColor.black.set()

            let fold = NSBezierPath()
            fold.move(to: NSPoint(x: 20.5, y: 16.3))
            fold.line(to: NSPoint(x: 4.87, y: 16.3))
            fold.appendArc(
                withCenter: NSPoint(x: 4.87, y: 15.3),
                radius: 1,
                startAngle: 90,
                endAngle: 235.2,
                clockwise: false
            )
            fold.line(to: NSPoint(x: 14, y: 7.7))
            fold.lineWidth = 2
            fold.lineCapStyle = .round
            fold.lineJoinStyle = .round
            fold.stroke()

            if isAwake {
                NSBezierPath(ovalIn: NSRect(x: 13.55, y: 9.65, width: 4.5, height: 4.5)).fill()
            } else {
                let ring = NSBezierPath(ovalIn: NSRect(x: 14.3, y: 10.4, width: 3, height: 3))
                ring.lineWidth = 1.5
                ring.stroke()
            }
            return true
        }
        image.isTemplate = true
        image.accessibilityDescription = isAwake ? "Wick, awake" : "Wick"
        return image
    }
}
