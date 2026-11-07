# Unfiltered timed capture of every device on USBPcap1 and USBPcap2. Run elevated.
param(
    [int]$Seconds = 75,
    [string]$Name = 'full',
    [string[]]$Steps = @(
        '1) Open the Kreo Hive 65 app and wait for it to show the keyboard.',
        '2) Lighting: click ONE different mode, press Apply.',
        '3) Close the app.')
)
$usbpcap = 'C:\Program Files\USBPcap\USBPcapCMD.exe'
$outDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'captures'
$procs = foreach ($hub in 1, 2) {
    $file = Join-Path $outDir "2x_${Name}_hub$hub.pcap"
    Start-Process $usbpcap -ArgumentList '-d', "\\.\USBPcap$hub", '-A', '-s', '65535', '-o', "`"$file`"" -PassThru -WindowStyle Hidden
}
Write-Host "Capturing all USB traffic for $Seconds s." -ForegroundColor Yellow
$Steps | ForEach-Object { Write-Host $_ }
for ($s = $Seconds; $s -gt 0; $s--) { Write-Host -NoNewline "`r  $s s left  "; Start-Sleep 1 }
$procs | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "`nDone. You can close this window." -ForegroundColor Green
