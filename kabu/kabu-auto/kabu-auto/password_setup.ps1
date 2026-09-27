# APIパスワードをユーザー環境変数 KABU_API_PASSWORD に保存する(Windows標準のPowerShellのみ使用)
$value = Read-Host "APIパスワードを入力してEnterを押してください"
if ([string]::IsNullOrEmpty($value)) {
    Write-Host "何も入力されなかったため、保存しませんでした。"
    exit 1
}
[Environment]::SetEnvironmentVariable("KABU_API_PASSWORD", $value, "User")
Write-Host "保存しました"
exit 0
