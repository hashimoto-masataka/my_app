// swift-tools-version: 5.7

import PackageDescription

let package = Package(
    name: "CreditStatement",
    defaultLocalization: "ja",
    platforms: [
        .macOS(.v12)
    ],
    products: [
        .library(name: "CreditStatementCore", targets: ["CreditStatementCore"]),
        .executable(name: "CreditStatementApp", targets: ["CreditStatementApp"])
    ],
    targets: [
        .target(
            name: "CreditStatementCore"
        ),
        .executableTarget(
            name: "CreditStatementApp",
            dependencies: ["CreditStatementCore"]
        ),
        .testTarget(
            name: "CreditStatementCoreTests",
            dependencies: ["CreditStatementCore"],
            resources: [.copy("Fixtures")]
        )
    ]
)
