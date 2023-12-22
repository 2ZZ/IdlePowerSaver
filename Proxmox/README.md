# Idle Power Saver

> [!WARNING]
> Abandoned experiment using Windows "run task on idle" task scheduler option

Automation to cap host CPU while all Windows guests are idle in order to reduce power consumption.

### Proxmox setup

```
pveum user add powersaver@pam
pveum role add powersaver -privs "VM.Config.Options"
pveum acl modify /vms/102 -user powersaver@pam -role powersaver
pveum acl modify /vms/106 -user powersaver@pam -role powersaver
pveum user token add powersaver@pam default -privsep 0
```

### Guest setup

- Clone to C:\IdlePowerSaver
- Execute Install.ps1 with elevated permissions

### Host logic

- TODO

### Guest logic

```
On idle:
- Update VM config
- Spawn child
When idle ends:
- Parent is killed
- Child detects & removes idle flag
```
