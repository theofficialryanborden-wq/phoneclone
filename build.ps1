param(
    [switch]$OneFile = $true
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "Installing dependencies..."
python -m pip install -r requirements.txt -q

$Exe = Join-Path $Root "dist\PhoneClone.exe"
$running = @(Get-Process -Name "PhoneClone" -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    $ids = ($running | ForEach-Object { $_.Id }) -join ", "
    Write-Host "Stopping $($running.Count) running PhoneClone instance(s) (PIDs: $ids) so the build can replace dist\PhoneClone.exe..."
    foreach ($proc in $running) {
        try {
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
        } catch {
            Write-Warning "Could not stop PID $($proc.Id): $($_.Exception.Message)"
        }
    }
    Start-Sleep -Seconds 1
    $still = @(Get-Process -Name "PhoneClone" -ErrorAction SilentlyContinue)
    if ($still.Count -gt 0) {
        $left = ($still | ForEach-Object { $_.Id }) -join ", "
        Write-Error @"
PhoneClone is still running (PIDs: $left) and dist\PhoneClone.exe is locked.
Close PhoneClone from the taskbar or Task Manager, then run .\build.ps1 again.
"@
    }
}

Write-Host "Building PhoneClone.exe..."
if ($OneFile) {
    python -m PyInstaller phoneclone.spec --noconfirm --clean
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
