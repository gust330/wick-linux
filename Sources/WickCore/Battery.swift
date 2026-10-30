import Foundation
import IOKit.ps

public struct Battery: Sendable, Equatable {
    public var percent: Int
    public var isDischarging: Bool

    public init(percent: Int, isDischarging: Bool) {
        self.percent = percent
        self.isDischarging = isDischarging
    }

    /// `nil` on Macs without a battery.
    public static func current() -> Battery? {
        let info = IOPSCopyPowerSourcesInfo().takeRetainedValue()
        let sources = IOPSCopyPowerSourcesList(info).takeRetainedValue() as [CFTypeRef]
        for source in sources {
            guard
                let description = IOPSGetPowerSourceDescription(info, source)?.takeUnretainedValue() as? [String: Any],
                description[kIOPSTypeKey] as? String == kIOPSInternalBatteryType,
                let current = description[kIOPSCurrentCapacityKey] as? Int,
                let capacity = description[kIOPSMaxCapacityKey] as? Int, capacity > 0
            else { continue }
            let state = description[kIOPSPowerSourceStateKey] as? String
            return Battery(percent: current * 100 / capacity, isDischarging: state == kIOPSBatteryPowerValue)
        }
        return nil
    }
}
