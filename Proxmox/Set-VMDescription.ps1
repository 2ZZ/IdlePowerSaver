param (
  [Parameter(Mandatory = $true, Position = 0)]
  [string]$thisVmId,

  [Parameter(Mandatory = $true, Position = 1)]
  [string]$idle
)

$ErrorActionPreference = 'Stop'

$baseDir = "C:\IdleDetect\Windows"
Set-Location $baseDir

$config = Get-Content 'config.json' | ConvertFrom-Json

$headers = @{
  "Authorization" = "Bearer $($config.authToken)"
}
$apiUrl = "https://$($config.proxmoxIpAddress):$($config.proxmoxPort)/api2/json/nodes/$($config.proxmoxNode)/qemu/$($config.thisVmId)/config"

function Log-Action {
  param (
    [string]$Message
  )

  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  $logMessage = $timestamp + ": " + $Message
  Add-Content -Path ".\activity.log" -Value $logMessage
}

function Set-VMDescription {
  param (
    [string]$thisVmId,
    [string]$idle
  )

  $body = @{
    description = '{"idle": ' + $idle + ', "updated": "' + $(Get-Date) + '"}'
  }

  $logMsg = "Setting VM ID $($config.thisVmId) idle status to $idle"
  Write-Host $logMsg
  Log-Action -Message $logMsg

  try {
    Invoke-RestMethod -Uri $apiUrl -Method Put -Body $body -ContentType "application/x-www-form-urlencoded" -Headers $headers -SkipCertificateCheck
  }
  catch {
    Write-Error $_.Exception.Response
    Write-Error $_.Exception.Message
  }
}

Set-VMDescription -vmId $config.thisVmId -idle $idle