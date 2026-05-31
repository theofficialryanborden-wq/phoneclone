param(
    [switch]$OneFile = $true
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "Installing dependencies..."
python -m pip install -r requirements.txt -q

Write-Host "Building PhoneClone.exe..."
if ($OneFile) {
    python -m PyInstaller phoneclone.spec --noconfirm --clean
    $Exe = Join-Path $Root "dist\PhoneClone.exe"
} else {
    python -m PyInstaller run.py `
        --name PhoneClone `
        --windowed `
        --paths src `
        --hidden-import phoneclone `
        --hidden-import phoneclone.main `
        --noconfirm `
        --clean
    $Exe = Join-Path $Root "dist\PhoneClone\PhoneClone.exe"
}

if (Test-Path $Exe) {
    Write-Host ""
    Write-Host "Build complete: $Exe" -ForegroundColor Green
} else {
    Write-Error "Build failed - executable not found."
}
