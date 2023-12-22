#!/usr/bin/env python3

import time
import logging
import threading
import subprocess
import psutil


USB_INPUT_DEVICES = ['5:002:1', '5:002:2', '5:003:1', '5:004:1']
USB_MONITOR_FILE = '/sys/kernel/debug/usb/usbmon/0u'
MIN_IDLE_MINUTES = 15
LOW_CPU_MINUTES = 5
LOW_CPU_THRESHOLD = 50
LOW_PERF_GOVERNOR = 'powersave'
HIGH_PERF_GOVERNOR = 'ondemand'

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')


class IdlePowerSaver:
    def __init__(self):
        self.last_seen_time = time.time()
        self.active_governor = str
        self.minimum_idle_time = 60 * MIN_IDLE_MINUTES
        self.cpu_idle_time_required = 5 * LOW_CPU_MINUTES
        self.cpu_check_interval = 60

    def load_usbmon_module(self):
        logging.info("Loading usbmon kernel module")
        subprocess.run(["modprobe", "usbmon"], check=True)

    def disable_powersave(self):
        if self.active_governor != HIGH_PERF_GOVERNOR:
            self.toggle_cpu_scaling_governor(HIGH_PERF_GOVERNOR)

    def enable_powersave(self):
        if self.active_governor != LOW_PERF_GOVERNOR:
            self.toggle_cpu_scaling_governor(LOW_PERF_GOVERNOR)

    def toggle_cpu_scaling_governor(self, governor_name):
        logging.info(f"Enabling {governor_name} scaling governor")
        command = f"echo {governor_name} | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
        subprocess.run(command, shell=True, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.active_governor = governor_name

    def monitor_usb(self):
        process = subprocess.Popen(
            ['cat', USB_MONITOR_FILE], stdout=subprocess.PIPE, text=True)
        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                if any(device in line for device in USB_INPUT_DEVICES):
                    self.last_seen_time = time.time()
        finally:
            process.kill()

    def check_cpu_usage(self):
        utilization_records = []
        end_time = time.time() + self.cpu_idle_time_required
        while time.time() < end_time:
            utilization = psutil.cpu_percent(interval=self.cpu_check_interval)
            utilization_records.append(utilization)
            if utilization > LOW_CPU_THRESHOLD:
                logging.info(f"High CPU usage detected: {utilization}%")
                return False
        return True

    def start_monitoring(self):
        self.load_usbmon_module()
        self.toggle_cpu_scaling_governor("ondemand")

        monitor_thread = threading.Thread(target=self.monitor_usb)
        monitor_thread.start()

        try:
            while True:
                if (time.time() - self.last_seen_time > self.minimum_idle_time and
                        self.check_cpu_usage()):
                    self.enable_powersave()
                else:
                    self.disable_powersave()
                time.sleep(1)
        finally:
            monitor_thread.join()


if __name__ == "__main__":
    idle_power_saver = IdlePowerSaver()
    idle_power_saver.start_monitoring()
