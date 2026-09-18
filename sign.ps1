# Sign the installer with the self-signed LitManager certificate.
# Note: self-signed certs are NOT trusted by Windows SmartScreen - the warning
# still appears but shows publisher "LitManager". To fully remove the warning,
# a CA-issued code signing certificate is required.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File sign.ps1
$ErrorActionPreference = "Stop"

$pfxPath = Join-Path $PSScriptRoot "cert.pfx"
$exePath = Join-Path $PSScriptRoot "dist\LitManager-Setup.exe"

if (-not (Test-Path $pfxPath)) {
    Write-Host "cert.pfx not found. Generate it first." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $exePath)) {
    Write-Host "dist\LitManager-Setup.exe not found. Run build_exe.bat first." -ForegroundColor Red
    exit 1
}

$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2
$cert.Import($pfxPath, "litmanager", [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable)
# 时间戳服务器国内常不可达（自签名场景价值有限），不做时间戳
Set-AuthenticodeSignature -FilePath $exePath -Certificate $cert -HashAlgorithm SHA256
Write-Host "Signed: $exePath"
