param (
  [Parameter(Mandatory = $true, Position = 0)]
  [string]$parentPid,

  [Parameter(Mandatory = $true, Position = 1)]
  [string]$thisVmId,

  [Parameter(Mandatory = $true, Position = 2)]
  [string]$idle
)

$ErrorActionPreference = 'Stop'

$config = Get-Content 'config.json' | ConvertFrom-Json

Write-Host "Waiting for PID $parentPid to exit before updating idle status"
$process = Get-Process -Id $parentPid
$process.WaitForExit()

Start-Process -FilePath $config.psExe -ArgumentList "-File", "./Set-VMDescription.ps1", $thisVmId, $idle