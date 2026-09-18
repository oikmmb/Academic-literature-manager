# Sign ALL binaries (exe/dll/pyd) under dist\LitManager\_internal with the code signing cert.
# Needed for Smart App Control / WDAC machines, which block unsigned DLL loading.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File sign_all.ps1 [pfxPath] [password]
param(
    [string]$PfxPath = "",
    [string]$Password = ""
)
$ErrorActionPreference = "Stop"

if (-not $PfxPath) { $PfxPath = Join-Path $PSScriptRoot "cert.pfx" }
if (-not $Password) { $Password = "litmanager" }
$root = Join-Path $PSScriptRoot "dist\LitManager\_internal"

if (-not (Test-Path $PfxPath)) { Write-Host "cert.pfx not found" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $root)) { Write-Host "dist\LitManager\_internal not found. Run build_exe.bat first." -ForegroundColor Red; exit 1 }

$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2
$cert.Import($PfxPath, $Password, [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable)

$files = Get-ChildItem -Path $root -Recurse -Include *.exe, *.dll, *.pyd
Write-Host "Signing $($files.Count) binaries..."
foreach ($f in $files) {
    Set-AuthenticodeSignature -FilePath $f.FullName -Certificate $cert -HashAlgorithm SHA256 | Out-Null
}
Write-Host "Done. Also run sign.ps1 to sign the installer itself."
