#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_DIR="${SCRIPT_DIR:h}"
APP_DIR="${PROJECT_DIR}/dist/クレジット明細.app"
ZIP_PATH="${PROJECT_DIR}/dist/クレジット明細.zip"

cd "${PROJECT_DIR}"
swift build -c release
BIN_DIR="$(swift build -c release --show-bin-path)"

if [[ -d "${APP_DIR}" ]]; then
    rm -rf "${APP_DIR}"
fi
if [[ -f "${ZIP_PATH}" ]]; then
    rm -f "${ZIP_PATH}"
fi

mkdir -p "${APP_DIR}/Contents/MacOS"
mkdir -p "${APP_DIR}/Contents/Resources"
cp "${BIN_DIR}/CreditStatementApp" "${APP_DIR}/Contents/MacOS/CreditStatementApp"
cp "${PROJECT_DIR}/Resources/Info.plist" "${APP_DIR}/Contents/Info.plist"
cp "${PROJECT_DIR}/Resources/AppIcon.icns" "${APP_DIR}/Contents/Resources/AppIcon.icns"
chmod 755 "${APP_DIR}/Contents/MacOS/CreditStatementApp"

codesign --force --deep --sign - "${APP_DIR}"
ditto -c -k --sequesterRsrc --keepParent "${APP_DIR}" "${ZIP_PATH}"

echo "Built: ${APP_DIR}"
echo "Archive: ${ZIP_PATH}"
