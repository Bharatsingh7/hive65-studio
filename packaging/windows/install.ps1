# Install the built app to %LOCALAPPDATA%\Programs\hive65 and start Hive65 Studio at login.
# Usage: powershell -ExecutionPolicy Bypass -File packaging\windows\install.ps1 [-Uninstall]
param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$dest = Join-Path $env:LOCALAPPDATA 'Programs\hive65'
$startup = [Environment]::GetFolderPath('Startup')
$programs = [Environment]::GetFolderPath('Programs')
$links = @((Join-Path $startup 'Hive65 Studio.lnk'), (Join-Path $programs 'Hive65 Studio.lnk'))
$old = Join-Path $startup 'Kreo Hive 65 (hive65).lnk'

Get-Process hive65-studio, hive65-tray -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
Remove-Item $old -ErrorAction SilentlyContinue

if ($Uninstall) {
    $links | ForEach-Object { Remove-Item $_ -ErrorAction SilentlyContinue }
    Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'hive65 removed.'
    return
}

$dist = Join-Path $env:LOCALAPPDATA 'hive65-build\dist'   # where build.ps1 puts its output
New-Item -ItemType Directory -Force $dest | Out-Null
Remove-Item (Join-Path $dest 'hive65-tray.exe') -ErrorAction SilentlyContinue
Remove-Item (Join-Path $dest 'studio') -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item "$dist\hive65.exe" $dest -Force
Copy-Item "$dist\hive65-studio" (Join-Path $dest 'studio') -Recurse -Force
$exe = Join-Path $dest 'studio\hive65-studio.exe'

$shell = New-Object -ComObject WScript.Shell
foreach ($l in $links) {
    $s = $shell.CreateShortcut($l)
    $s.TargetPath = $exe
    $s.WorkingDirectory = Split-Path $exe
    if ($l -like "$startup*") { $s.Arguments = '--minimized' }
    $s.Save()
}

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notlike "*$dest*") {
    [Environment]::SetEnvironmentVariable('Path', "$userPath;$dest", 'User')
}
if (Get-Process OemDrv -ErrorAction SilentlyContinue) {
    Write-Host 'Note: the Kreo app (OemDrv.exe) is running. Close it and turn off its autostart.' -ForegroundColor Yellow
}
Start-Process $exe
Write-Host "Installed to $dest. Hive65 Studio is in the Start menu and starts at login." -ForegroundColor Green
