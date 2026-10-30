// swift-tools-version: 6.2
import PackageDescription

let appSettings: [SwiftSetting] = [
    .defaultIsolation(MainActor.self),
    .enableUpcomingFeature("NonisolatedNonsendingByDefault"),
    .enableUpcomingFeature("InferIsolatedConformances"),
]

let package = Package(
    name: "Wick",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "wick", targets: ["wick"]),
        .executable(name: "WickApp", targets: ["WickApp"]),
    ],
    targets: [
        .target(name: "WickCore"),
        .target(name: "WickUI", dependencies: ["WickCore"], swiftSettings: appSettings),
        .executableTarget(name: "wick", dependencies: ["WickCore"]),
        .executableTarget(name: "WickApp", dependencies: ["WickUI"], swiftSettings: appSettings),
        .executableTarget(name: "wick-snapshots", dependencies: ["WickUI"], swiftSettings: appSettings),
        .testTarget(name: "WickCoreTests", dependencies: ["WickCore"]),
        .testTarget(name: "WickUITests", dependencies: ["WickUI"], swiftSettings: appSettings),
    ]
)
