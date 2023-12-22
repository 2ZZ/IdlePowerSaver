# Idle Power Saver for Linux Desktop

Enables the "powersave" CPU frequency limiter when no USB input detected and average CPU utilization below a threshold for x minutes.

### Installation

1. Identify the hardware IDs of the USB input devices you want to disable idle when active

   1.1. Load the usbmon module and start monitoring USB events

   ```
   modprobe usbmon
   cat /sys/kernel/debug/usb/usbmon/0u
   ```

   1.2. Wiggle mouse / touch keys on keyboard, look at the IDs in the output, they'll look something like `5:002:1`

2. Download files

   ```
   cd /opt
   git clone https://github.com/2ZZ/IdlePowerSaver.git
   cd IdlePowerSaver
   chmod +x IdlePowerSaver.py
   ```

3. Customize settings

   3.1 Edit `IdlePowerSaver.py`

   3.2 Set `USB_INPUT_DEVICES` from step 1

   3.3 Adjust `MIN_IDLE_MINUTES`, `LOW_CPU_THRESHOLD`, `LOW_CPU_MINUTES` if neccessary.

4. Enable and start service

   ```
   ln -s /opt/IdlePowerSaver/IdlePowerSaver.service /etc/systemd/system/IdlePowerSaver.service
   systemctl daemon-reload
   systemctl enable IdlePowerSaver
   systemctl start IdlePowerSaver
   ```

5. Monitor behaviour
   ```
   journalctl -fu IdlePowerSaver
   ```
