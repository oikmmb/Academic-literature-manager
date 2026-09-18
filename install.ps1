# LitManager installer (no admin required, installs to LOCALAPPDATA)
# Run:  setup.bat   (or: powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1)
$ErrorActionPreference = "Stop"

$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$dist = Join-Path $src "dist\LitManager"
$exe = Join-Path $dist "LitManager.exe"

if (-not (Test-Path $exe)) {
    Write-Host "[ERROR] $exe not found. Run build_exe.bat first." -ForegroundColor Red
    exit 1
}

$target = Join-Path $env:LOCALAPPDATA "Programs\LitManager"
# PS5.1 parses this file as ANSI; build the Chinese dir name from code points to stay pure ASCII.
# 0x8BBA 0x6587 = "lun wen" (papers)
$paperDir = [string]::Concat([char]0x8BBA, [char]0x6587)
if (Test-Path "F:\") {
    $userData = "F:\$paperDir\data"     # data on F: drive to keep C: small
} else {
    $userData = Join-Path $env:USERPROFILE ".lit-manager\data"
}

Write-Host "[1/4] Installing to $target ..."
if (Test-Path $target) { Remove-Item -Recurse -Force $target }
Copy-Item $dist $target -Recurse

Write-Host "[2/4] Migrating existing data to $userData ..."
$oldData = Join-Path $env:USERPROFILE ".lit-manager\data"
$devDb = Join-Path $src "data\lit.db"
if (-not (Test-Path (Join-Path $userData "lit.db"))) {
    New-Item -ItemType Directory -Force -Path $userData | Out-Null
    if (Test-Path $oldData) {
        Copy-Item "$oldData\*" $userData -Recurse -Force
        Write-Host "  Migrated from $oldData"
    } elseif (Test-Path $devDb) {
        Copy-Item $devDb (Join-Path $userData "lit.db")
        if (Test-Path (Join-Path $src "data\pdfs")) {
            Copy-Item (Join-Path $src "data\pdfs") $userData -Recurse -Force
        }
        Write-Host "  Migrated from dev data dir"
    }
} else {
    Write-Host "  Data dir ready: $userData"
}

Write-Host "[3/4] Creating shortcuts ..."
$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$lnkDesktop = $ws.CreateShortcut((Join-Path $desktop "LitManager.lnk"))
$lnkDesktop.TargetPath = Join-Path $target "LitManager.exe"
$lnkDesktop.WorkingDirectory = $target
$lnkDesktop.Description = "LitManager - academic literature manager"
$lnkDesktop.Save()

$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$lnkMenu = $ws.CreateShortcut((Join-Path $startMenu "LitManager.lnk"))
$lnkMenu.TargetPath = Join-Path $target "LitManager.exe"
$lnkMenu.WorkingDirectory = $target
$lnkMenu.Save()

Write-Host "[4/4] Writing uninstaller ..."
$uninstall = @'
$ErrorActionPreference = "SilentlyContinue"
$target = Join-Path $env:LOCALAPPDATA "Programs\LitManager"
$desktop = [Environment]::GetFolderPath("Desktop")
Remove-Item (Join-Path $desktop "LitManager.lnk")
Remove-Item (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\LitManager.lnk")
Remove-Item -Recurse -Force $target
$paperDir = [string]::Concat([char]0x8BBA, [char]0x6587)
if (Test-Path "F:\") { $userData = "F:\$paperDir\data" } else { $userData = Join-Path $env:USERPROFILE ".lit-manager\data" }
if (Test-Path $userData) {
    $answer = Read-Host "Also delete user data (literature, highlights, notes)? [y/N]"
    if ($answer -eq "y") { Remove-Item -Recurse -Force $userData }
    else { Write-Host "User data kept at $userData" }
}
Write-Host "LitManager uninstalled."
'@
$uninstall | Out-File -FilePath (Join-Path $target "uninstall.ps1") -Encoding ASCII

Write-Host ""
Write-Host "Done. Launch LitManager from the desktop shortcut."
Write-Host "User data (literature + annotations) persists at: $userData"