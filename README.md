# Idle Power Saver for Proxmox

Monitors USB activity and automatically suspends running Proxmox VMs and the host system when idle. When no USB activity is detected for a configured duration, all running VMs are suspended before the host system enters suspend mode.

### Requirements

- Proxmox VE host system
- Python 3 with psutil module
- Root access for USB monitoring and system suspension

### Installation

1. Download files

   ```
   cd /opt
   git clone https://github.com/2ZZ/IdlePowerSaver.git
   cd IdlePowerSaver
   ```

2. Install Python dependencies

   ```
   apt-get update
   apt-get install python3-psutil
   ```

3. Customize settings

   Edit `IdlePowerSaver.py` to adjust configuration:

   - `USB_INPUT_DEVICES`: Set to `['0']` to monitor all USB buses (default)
   - `MIN_IDLE_MINUTES`: Minutes of USB inactivity before suspension (default: 15)
   - `ENABLE_CPU_MONITORING`: Enable/disable CPU monitoring (default: False)
   - `LOW_CPU_THRESHOLD`: CPU usage threshold if monitoring is enabled (default: 50%)
   - `LOG_LEVEL`: Logging verbosity (default: DEBUG)

4. Enable and start service

   ```
   ln -s /opt/IdlePowerSaver/IdlePowerSaver.service /etc/systemd/system/IdlePowerSaver.service
   systemctl daemon-reload
   systemctl enable IdlePowerSaver
   systemctl start IdlePowerSaver
   ```

5. Monitor behavior

   ```
   journalctl -fu IdlePowerSaver
   ```

### How It Works

1. The daemon loads the usbmon kernel module to monitor USB activity
2. USB activity is monitored via `/dev/usbmon0` using binary packet parsing
3. When USB has been idle for the configured duration and no backup is running:
   - All running VMs are suspended using `qm suspend`
   - Once all VMs are suspended, the host system enters suspend mode via `systemctl suspend`
