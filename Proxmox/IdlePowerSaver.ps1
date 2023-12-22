$ErrorActionPreference = 'Stop'

$baseDir = "C:\IdlePowerSaver\Windows"
Set-Location $baseDir

$config = Get-Content 'config.json' | ConvertFrom-Json

Start-Process -FilePath $config.psExe -ArgumentList "-File", "./Set-VMDescription.ps1", $config.thisVmId, "true" -NoNewWindow -Wait

Write-Host "Spawning after idle script"
Start-Process -FilePath $config.psExe -ArgumentList "-File", "./RunAfterIdle.ps1", $PID, $config.thisVmId, "false"

Write-Host "Waiting until killed"
Read-Host