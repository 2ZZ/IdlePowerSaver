
Get-ScheduledTask -TaskPath "\" -TaskName "IdlePowerSaver" | Unregister-ScheduledTask -Confirm:$false

Register-ScheduledTask -Action (
  New-ScheduledTaskAction `
    -Execute "Powershell.exe" `
    -Argument "-File C:\IdlePowerSaver\Proxmox\IdlePowerSaver.ps1"
) -Trigger (
  New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Hours 1)
)-Principal (
  New-ScheduledTaskPrincipal `
    -UserId "SYSTEM"
) -Settings (
  New-ScheduledTaskSettingsSet `
    -RunOnlyIfIdle `
    -IdleDuration (New-TimeSpan -Minutes 5) `
    -IdleWaitTimeout (New-TimeSpan -Minutes 60) `
    -Hidden `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -minutes 60)
) -TaskName "IdlePowerSaver" -Description "IdlePowerSaver"