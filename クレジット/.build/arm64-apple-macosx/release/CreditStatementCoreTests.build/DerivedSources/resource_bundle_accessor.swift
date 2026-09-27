import class Foundation.Bundle

extension Foundation.Bundle {
    static let module: Bundle = {
        let mainPath = Bundle.main.bundleURL.appendingPathComponent("CreditStatement_CreditStatementCoreTests.bundle").path
        let buildPath = "/Users/hashimotomasataka/Desktop/クレジット/.build/arm64-apple-macosx/release/CreditStatement_CreditStatementCoreTests.bundle"

        let preferredBundle = Bundle(path: mainPath)

        guard let bundle = preferredBundle ?? Bundle(path: buildPath) else {
            fatalError("could not load resource bundle: from \(mainPath) or \(buildPath)")
        }

        return bundle
    }()
}