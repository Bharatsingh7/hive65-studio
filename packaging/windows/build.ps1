# Build standalone hive65.exe (CLI) and hive65-studio.exe (app + tray) with PyInstaller.
# Usage: powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
param([switch]$Portable)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$venv = Join-Path $env:USERPROFILE '.venvs\hive65'
if (-not (Test-Path "$venv\Scripts\python.exe")) { python -m venv $venv }
$py = "$venv\Scripts\python.exe"
& $py -m pip install -q --upgrade pip
& $py -m pip install -q -e "$root[all]" pyinstaller

# Build in a short path: PySide6's plugin folders exceed Windows' 260-char limit
# when the project lives deep in the file system.
$out = Join-Path $env:LOCALAPPDATA 'hive65-build'
$dist = Join-Path $out 'dist'
$data = "$root\hive65\data;hive65\data"
$common = @('--noconfirm', '--add-data', $data, '--workpath', (Join-Path $out 'work'),
            '--specpath', $out, '--paths', "$root",
            '--collect-submodules', 'hive65',
            '--collect-submodules', 'winrt', '--collect-submodules', 'pycaw',
            '--hidden-import', 'screen_brightness_control', '--hidden-import', 'soundcard',
            '--collect-data', 'qtawesome', '--hidden-import', 'pynput.keyboard._win32',
            '--distpath', $dist)
Push-Location $root
try {
    $icon = @('--icon', "$root\packaging\hive65.ico")
    & $py -m PyInstaller @common @icon --onefile --name hive65 "$root\packaging\windows\cli_entry.py"
    # The installed Studio is a folder build: starts much faster than a one-file exe.
    & $py -m PyInstaller @common @icon --onedir --windowed --name hive65-studio "$root\packaging\windows\studio_entry.py"
    if ($Portable) {
        # Single portable exe to share or run from anywhere (unpacks to %TEMP% on each start).
        & $py -m PyInstaller @common @icon --onefile --windowed --name Hive65-Studio-Portable "$root\packaging\windows\studio_entry.py"
    }
} finally { Pop-Location }
Write-Host "Built: $dist\hive65.exe and $dist\hive65-studio\hive65-studio.exe" -ForegroundColor Green
if ($Portable) { Write-Host "Portable: $dist\Hive65-Studio-Portable.exe" -ForegroundColor Green }
