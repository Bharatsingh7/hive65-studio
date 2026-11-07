# Guided USB capture of the Kreo Hive 65 config protocol.
# Run from an ADMIN PowerShell:  powershell -ExecutionPolicy Bypass -File tools\capture.ps1
# Each step records one action in the Kreo app to captures\NN_name.pcap.
param(
    [string]$Hub = '\\.\USBPcap1',
    [string]$Device = '5',
    [int]$From = 0
)

$ErrorActionPreference = 'Stop'
$usbpcap = 'C:\Program Files\USBPcap\USBPcapCMD.exe'
$outDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'captures'
New-Item -ItemType Directory -Force $outDir | Out-Null

$steps = @(
    @('idle',          'Close the Kreo app if it is open. Do nothing else.'),
    @('app_start',     'Start "Kreo Hive 65" and wait until it shows the keyboard.'),
    @('modes_all',     'Lighting page: click EVERY lighting mode in order, first to last, waiting ~2 s after each click (press Apply after each one if the app has an Apply button).'),
    @('brightness',    'Pick a static/single-colour mode. Set brightness to MIN, then step up one notch at a time to MAX, ~2 s apart.'),
    @('speed',         'Pick a moving mode (e.g. breathing/wave). Set speed to MIN, then step up one notch at a time to MAX, ~2 s apart.'),
    @('colors',        'Static mode: set colour to pure RED, then GREEN, then BLUE, then WHITE, ~2 s apart.'),
    @('direction',     'Pick a mode with a direction option and toggle direction a couple of times, ~2 s apart.'),
    @('perkey_esc_red','Custom/per-key lighting: make all keys off/black except ESC = RED, then Apply.'),
    @('perkey_q_green','Custom/per-key lighting: keep ESC red and also set Q = GREEN, then Apply.'),
    @('et_audiobar',   'Start some music playing, then select the audio/music bar effect and let it run ~8 s.'),
    @('et_other',      'Select each other software effect (stream, flower, happy...) for ~4 s each.'),
    @('remap_caps_esc','Key settings: remap CAPS LOCK to ESC, then Apply.'),
    @('remap_restore', 'Restore CAPS LOCK to its default, then Apply.'),
    @('fn_layer',      'If there is an FN-layer page: change one FN combo (e.g. FN+F -> Mute), then Apply. Otherwise just press Enter.'),
    @('macro',         'Macro page: record a macro that types "ab", assign it to a key such as F (or Insert), then Apply.'),
    @('macro_restore', 'Remove the macro / set that key back to default, then Apply.'),
    @('app_close',     'Close the Kreo app.')
)

Get-Process USBPcapCMD -ErrorAction SilentlyContinue | Stop-Process -Force

for ($i = $From; $i -lt $steps.Count; $i++) {
    $name, $what = $steps[$i]
    $file = Join-Path $outDir ('{0:D2}_{1}.pcap' -f $i, $name)
    Write-Host ''
    Write-Host ("[{0}/{1}] {2}" -f $i, ($steps.Count - 1), $name) -ForegroundColor Cyan
    Write-Host "  $what"
    Read-Host '  Press Enter to START recording' | Out-Null
    $p = Start-Process $usbpcap -ArgumentList '-d', $Hub, '--devices', $Device, '-s', '65535', '-o', "`"$file`"" -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 700
    if ($p.HasExited) { Write-Host "  USBPcapCMD exited (code $($p.ExitCode)). Is this an admin shell?" -ForegroundColor Red; exit 1 }
    Write-Host '  Recording... do the action now.' -ForegroundColor Yellow
    Read-Host '  Press Enter to STOP' | Out-Null
    Start-Sleep -Milliseconds 500
    Stop-Process $p -Force -ErrorAction SilentlyContinue
    $len = (Get-Item $file -ErrorAction SilentlyContinue).Length
    Write-Host ("  saved {0} ({1} bytes)" -f (Split-Path $file -Leaf), $len) -ForegroundColor Green
}
Write-Host "`nAll done. Captures are in $outDir" -ForegroundColor Green
