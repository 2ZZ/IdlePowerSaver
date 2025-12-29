#!/usr/bin/env python3

import os
import time
import logging
import threading
import subprocess
import psutil
import json
import signal
import sys
import struct
from datetime import datetime, timedelta

USB_INPUT_DEVICES = ['0']  # '0' means monitor all USB buses
USB_MONITOR_FILE = '/dev/usbmon0'  # Using /dev interface due to kernel lockdown
MIN_IDLE_MINUTES = 15
LOW_CPU_MINUTES = 5
LOW_CPU_THRESHOLD = 50
LOG_LEVEL = logging.DEBUG
ENABLE_CPU_MONITORING = False  # Feature flag for CPU utilization monitoring

logging.basicConfig(level=LOG_LEVEL,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')


class IdlePowerSaver:
    def __init__(self):
        self.last_seen_time = time.time()
        self.last_usb_device = "None"
        self.active_governor = ""
        self.minimum_idle_time = 60 * MIN_IDLE_MINUTES
        self.cpu_idle_time_required = 60 * LOW_CPU_MINUTES
        self.cpu_check_interval = 60
        self.cpu_percentages = []
        self.shutdown_flag = threading.Event()
        self.last_usb_log_time = 0
        self.usb_log_interval = 60
        self.enable_cpu_monitoring = ENABLE_CPU_MONITORING
        self.usb_device_cache = {}  # Cache for USB device names: (bus, dev) -> name
        self.usb_cache_time = 0
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        logging.info(f"Received signal {signum}. Shutting down gracefully...")
        self.shutdown_flag.set()
        sys.exit(0)

    def _humanize_time(self, timestamp):
        """Convert timestamp to human-readable format with relative time"""
        dt = datetime.fromtimestamp(timestamp)
        now = datetime.now()
        diff = now - dt

        if diff.total_seconds() < 60:
            relative = f"{int(diff.total_seconds())}s ago"
        elif diff.total_seconds() < 3600:
            relative = f"{int(diff.total_seconds() / 60)}m ago"
        elif diff.total_seconds() < 86400:
            relative = f"{int(diff.total_seconds() / 3600)}h ago"
        else:
            relative = f"{int(diff.total_seconds() / 86400)}d ago"

        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')} ({relative})"

    def load_usbmon_module(self):
        logging.info("Loading usbmon kernel module")
        try:
            subprocess.run(["modprobe", "usbmon"], check=True)
            logging.info("usbmon module loaded successfully")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to load usbmon module: {e}")
            raise

    @staticmethod
    def get_running_vms():
        logging.info("Getting all running VMs...")
        try:
            result = subprocess.run(["qm", "list"], capture_output=True, text=True, timeout=30)
            logging.debug(f"qm list output:\n{result.stdout}")

            if result.returncode != 0:
                logging.error(f"Error running 'qm list': {result.stderr}")
                return []

            running_vms = []
            for line in result.stdout.split('\n')[1:]:  # Skip the header line
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 3:
                        vmid, _, status = parts[0], parts[1], parts[2]
                        if status.lower() == 'running':
                            running_vms.append(vmid)
                            logging.debug(f"Found running VM: {vmid}")

            logging.info(f"Found {len(running_vms)} running VMs: {running_vms}")
            return running_vms
        except subprocess.TimeoutExpired:
            logging.error("Timeout while getting VM list")
            return []
        except Exception as e:
            logging.error(f"Unexpected error while getting VM list: {e}")
            return []

    @staticmethod
    def suspend_vm(vmid):
        try:
            logging.info(f"Suspending VM {vmid}...")
            result = subprocess.run(["qm", "suspend", str(vmid)],
                                    capture_output=True, text=True, timeout=60, check=True)
            logging.info(f"VM {vmid} suspended successfully")
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout while suspending VM {vmid}")
            raise
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to suspend VM {vmid}: {e.stderr}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error while suspending VM {vmid}: {e}")
            raise

    @staticmethod
    def is_vm_suspended(vmid):
        try:
            result = subprocess.run(
                ["qm", "status", str(vmid)], capture_output=True, text=True, timeout=30)
            logging.debug(f"qm status output for VM {vmid}:\n{result.stdout}")

            if result.returncode != 0:
                logging.error(
                    f"Error running 'qm status' for VM {vmid}: {result.stderr}")
                return False

            status_lines = result.stdout.strip().split('\n')
            status = {}
            for line in status_lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    status[key.strip().lower()] = value.strip().lower()

            vm_status = status.get('qmpstatus') == 'suspended' or status.get('status') == 'stopped' or status.get('status') == 'paused'
            logging.debug(f"VM {vmid} suspended status: {vm_status} (qmpstatus: {status.get('qmpstatus')}, status: {status.get('status')})")
            return vm_status
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout while checking VM {vmid} status")
            return False
        except Exception as e:
            logging.error(f"Unexpected error while checking VM {vmid} status: {e}")
            return False

    def suspend_all_vms(self):
        logging.info("Starting VM suspension process...")
        running_vms = self.get_running_vms()
        if not running_vms:
            logging.info("No running VMs found to suspend")
            return

        failed_vms = []
        for vmid in running_vms:
            try:
                self.suspend_vm(vmid)
            except Exception as e:
                logging.error(f"Failed to suspend VM {vmid}: {e}")
                failed_vms.append(vmid)

        if failed_vms:
            logging.warning(f"Failed to suspend VMs: {failed_vms}")
        else:
            logging.info(f"Successfully initiated suspension for all {len(running_vms)} VMs")

    def are_all_vms_suspended(self):
        all_vms = self.get_running_vms()
        if not all_vms:
            logging.debug("No VMs running, considering all suspended")
            return True

        suspended_count = 0
        for vmid in all_vms:
            if self.is_vm_suspended(vmid):
                suspended_count += 1

        all_suspended = suspended_count == len(all_vms)
        logging.info(f"VM suspension status: {suspended_count}/{len(all_vms)} suspended. All suspended: {all_suspended}")
        return all_suspended

    def suspend_system(self):
        logging.info(f"Resetting last seen time and suspending system")
        suspend_time = time.time()
        self.last_seen_time = suspend_time
        self.last_usb_device = "System suspended"
        command = "systemctl suspend"
        try:
            subprocess.run(command, shell=True, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to suspend system: {e}")
            return

        resume_time = time.time()
        suspend_duration = resume_time - suspend_time
        resume_time_human = self._humanize_time(resume_time)
        logging.info(f"System resumed at {resume_time_human}. Was suspended for {suspend_duration:.1f} seconds")

        logging.info("Sleeping script for 10 minutes")
        time.sleep(600)

    def toggle_cpu_scaling_governor(self, governor_name):
        last_seen_human = self._humanize_time(self.last_seen_time)
        logging.info(
            f"Enabling {governor_name} scaling governor, last USB activity: {last_seen_human}, last device: {self.last_usb_device}")
        command = f"echo {governor_name} | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
        try:
            subprocess.run(command, shell=True, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.active_governor = governor_name
            logging.debug(f"Successfully set CPU governor to {governor_name}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to set CPU governor to {governor_name}: {e}")
            raise

    def get_usb_device_name(self, busnum, devnum):
        """
        Get human-readable name for a USB device.
        Returns formatted string like "Logitech USB Receiver" or "Bus 005 Device 003"

        Uses lsusb for device identification and caches results.
        """
        # Refresh cache every 60 seconds to catch new devices
        current_time = time.time()
        if current_time - self.usb_cache_time > 60:
            self.usb_device_cache.clear()
            self.usb_cache_time = current_time

        cache_key = (busnum, devnum)

        # Return cached result if available
        if cache_key in self.usb_device_cache:
            return self.usb_device_cache[cache_key]

        # Try to get device name from lsusb
        try:
            result = subprocess.run(
                ['lsusb', '-s', f'{busnum}:{devnum}'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0 and result.stdout:
                # lsusb output format: "Bus 005 Device 003: ID 046d:c52b Logitech, Inc. Unifying Receiver"
                parts = result.stdout.strip().split(':', 2)
                if len(parts) >= 3:
                    # Extract device name (everything after the ID)
                    device_info = parts[2].strip()
                    device_name = f"Bus {busnum:03d} Dev {devnum:03d}: {device_info}"
                    self.usb_device_cache[cache_key] = device_name
                    return device_name
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass

        # Fallback to generic name
        fallback = f"Bus {busnum:03d} Device {devnum:03d}"
        self.usb_device_cache[cache_key] = fallback
        return fallback

    def monitor_usb(self):
        """
        Monitor USB activity by reading binary usbmon data from /dev/usbmon0.
        Binary format reference: https://www.kernel.org/doc/Documentation/usb/usbmon.txt

        Packet structure (64 bytes):
        - URB ID (8 bytes)
        - type, xfer_type, epnum, devnum (4 bytes)
        - busnum (2 bytes)
        - flags (2 bytes)
        - timestamp (12 bytes)
        - status, lengths, etc. (remaining bytes)
        """
        logging.info(f"Starting USB monitoring on {USB_MONITOR_FILE}")

        # Binary packet header is 64 bytes
        USBMON_PACKET_SIZE = 64

        # Format string for struct.unpack (little-endian)
        # Q=u64, B=u8, H=u16, b=s8, q=s64, i=s32, I=u32
        # Format: id(Q) type(B) xfer(B) ep(B) dev(B) bus(H) flags(bb) ts_sec(q) ts_usec(i) status(i) len(I) len_cap(I) setup(8s) interval(i) start_frame(i) xfer_flags(I) ndesc(I)
        packet_format = '<QBBBBHbbqiiII8siiII'

        try:
            with open(USB_MONITOR_FILE, 'rb') as f:
                logging.info("Successfully opened USB monitor device")

                while not self.shutdown_flag.is_set():
                    # Read one packet (64 bytes)
                    packet_data = f.read(USBMON_PACKET_SIZE)

                    if len(packet_data) < USBMON_PACKET_SIZE:
                        if len(packet_data) == 0:
                            # No data available, wait a bit
                            time.sleep(0.01)
                            continue
                        else:
                            logging.warning(f"Incomplete packet received: {len(packet_data)} bytes")
                            continue

                    try:
                        # Unpack the binary data
                        unpacked = struct.unpack(packet_format, packet_data)

                        urb_id = unpacked[0]
                        event_type = chr(unpacked[1]) if unpacked[1] < 128 else '?'
                        xfer_type = unpacked[2]
                        epnum = unpacked[3]
                        devnum = unpacked[4]
                        busnum = unpacked[5]
                        flag_setup = unpacked[6]
                        flag_data = unpacked[7]
                        ts_sec = unpacked[8]
                        ts_usec = unpacked[9]
                        status = unpacked[10]
                        length = unpacked[11]
                        len_cap = unpacked[12]

                        # Validate bus and device numbers (sanity check)
                        # Valid USB bus numbers are typically 1-255, device numbers 1-127
                        if busnum > 255 or devnum > 127:
                            # Invalid packet, skip it
                            continue

                        # Filter by USB device if needed
                        # '0' in USB_INPUT_DEVICES means monitor all buses
                        should_monitor = '0' in USB_INPUT_DEVICES or str(busnum) in USB_INPUT_DEVICES

                        if should_monitor and busnum > 0 and devnum > 0:
                            current_time = time.time()
                            self.last_seen_time = current_time

                            # Get human-readable device name
                            self.last_usb_device = self.get_usb_device_name(busnum, devnum)

                            # Add transfer type information for debugging
                            xfer_types = {0: 'ISO', 1: 'Interrupt', 2: 'Control', 3: 'Bulk'}
                            xfer_name = xfer_types.get(xfer_type, 'Unknown')

                            # Only log USB activity every 60 seconds to reduce verbosity
                            if current_time - self.last_usb_log_time >= self.usb_log_interval:
                                logging.debug(
                                    f"USB activity: {self.last_usb_device} "
                                    f"({xfer_name}, EP:{epnum:02x})"
                                )
                                self.last_usb_log_time = current_time

                    except struct.error as e:
                        logging.warning(f"Failed to unpack USB packet: {e}")
                        continue

        except FileNotFoundError:
            logging.error(f"USB monitor file not found: {USB_MONITOR_FILE}")
            logging.error("Make sure the usbmon module is loaded: modprobe usbmon")
        except PermissionError:
            logging.error(f"Permission denied accessing {USB_MONITOR_FILE}")
            logging.error("This script must run as root to access USB monitoring")
        except Exception as e:
            logging.error(f"Error monitoring USB: {e}")
            import traceback
            logging.error(traceback.format_exc())
        finally:
            logging.info("USB monitoring stopped")

    def monitor_cpu(self):
        if not self.enable_cpu_monitoring:
            logging.info("CPU monitoring is disabled via feature flag")
            return

        logging.info("Starting CPU monitoring")
        log_counter = 0
        while not self.shutdown_flag.is_set():
            cpu_percent = psutil.cpu_percent(interval=1)
            self.cpu_percentages.append(cpu_percent)
            if len(self.cpu_percentages) > 300:
                self.cpu_percentages.pop(0)

            log_counter += 1
            # Log every 5 minutes (300 seconds) instead of when hitting 300 samples
            if log_counter % 300 == 0:
                avg_cpu = sum(self.cpu_percentages) / len(self.cpu_percentages)
                logging.debug(f"CPU monitoring: {len(self.cpu_percentages)} samples, average: {avg_cpu:.1f}%")
                log_counter = 0  # Reset counter to prevent overflow
        logging.info("CPU monitoring stopped")

    def check_usb_idle(self):
        idle_duration = time.time() - self.last_seen_time
        last_seen_human = self._humanize_time(self.last_seen_time)
        required_idle_human = str(timedelta(seconds=self.minimum_idle_time))

        if idle_duration > self.minimum_idle_time:
            logging.debug(
                f"USB is idle - last activity: {last_seen_human} (device: {self.last_usb_device}), required idle time: {required_idle_human}")
            return True
        else:
            remaining_time = str(timedelta(seconds=self.minimum_idle_time - idle_duration))
            logging.debug(f"USB is NOT idle - last activity: {last_seen_human} (device: {self.last_usb_device}), {remaining_time} remaining")
            return False

    def check_cpu_idle(self):
        if not self.enable_cpu_monitoring:
            # When CPU monitoring is disabled, always return True (don't block on CPU)
            return True

        if self.cpu_percentages:
            cpu_average = sum(self.cpu_percentages) / len(self.cpu_percentages)
            is_idle = cpu_average < LOW_CPU_THRESHOLD
            logging.debug(f"CPU average: {cpu_average:.1f}%, idle: {is_idle}")
            return is_idle
        else:
            return False

    def check_backup_not_running(self):
        return not os.path.exists('/var/run/backup.running')

    def start_monitoring(self):
        logging.info("Starting IdlePowerSaver daemon...")
        startup_time = self._humanize_time(time.time())
        logging.info(f"Daemon started at {startup_time}")
        logging.info(f"CPU monitoring feature flag: {self.enable_cpu_monitoring}")

        try:
            self.load_usbmon_module()
            self.toggle_cpu_scaling_governor("ondemand")

            cpu_monitor_thread = threading.Thread(target=self.monitor_cpu, daemon=True)
            cpu_monitor_thread.start()
            if self.enable_cpu_monitoring:
                logging.info("CPU monitoring thread started")
            else:
                logging.info("CPU monitoring thread started (but disabled via feature flag)")

            usb_monitor_thread = threading.Thread(target=self.monitor_usb, daemon=True)
            usb_monitor_thread.start()
            logging.info("USB monitoring thread started")

            config_msg = f"Monitoring configuration: USB idle time: {self.minimum_idle_time//60}min"
            if self.enable_cpu_monitoring:
                config_msg += f", CPU threshold: {LOW_CPU_THRESHOLD}%"
            else:
                config_msg += ", CPU monitoring: disabled"
            logging.info(config_msg)

            main_loop_count = 0
            check_interval = 30  # Check every 30 seconds instead of 1 second
            try:
                while not self.shutdown_flag.is_set():
                    main_loop_count += 1
                    usb_idle = self.check_usb_idle()
                    cpu_idle = self.check_cpu_idle()
                    backup_not_running = self.check_backup_not_running()

                    # Log status every 10 checks (5 minutes at 30s intervals)
                    if main_loop_count % 10 == 0:
                        status_msg = f"Status check #{main_loop_count}: USB idle: {usb_idle}"
                        if self.enable_cpu_monitoring:
                            status_msg += f", CPU idle: {cpu_idle}"
                        status_msg += f", Backup not running: {backup_not_running}"
                        logging.info(status_msg)

                    if usb_idle and cpu_idle and backup_not_running:
                        logging.info("All conditions met for system suspension")
                        self.suspend_all_vms()
                        logging.info("Waiting for all VMs to be suspended...")
                        vm_wait_start = time.time()
                        while not self.are_all_vms_suspended() and not self.shutdown_flag.is_set():
                            time.sleep(5)  # Check VM status every 5 seconds instead of 1
                            if time.time() - vm_wait_start > 300:  # 5 minute timeout
                                logging.warning("Timeout waiting for VMs to suspend, proceeding anyway")
                                break
                        if not self.shutdown_flag.is_set():
                            self.suspend_system()

                    if not self.shutdown_flag.wait(check_interval):  # Wait 30 seconds or until shutdown
                        continue
                    break
            except KeyboardInterrupt:
                logging.info("Received keyboard interrupt")
                self.shutdown_flag.set()
        except Exception as e:
            logging.error(f"Fatal error in monitoring loop: {e}")
            raise
        finally:
            logging.info("Shutting down monitoring threads...")
            self.shutdown_flag.set()
            if 'cpu_monitor_thread' in locals() and cpu_monitor_thread.is_alive():
                cpu_monitor_thread.join(timeout=5)
            if 'usb_monitor_thread' in locals() and usb_monitor_thread.is_alive():
                usb_monitor_thread.join(timeout=5)
            logging.info("IdlePowerSaver daemon stopped")


if __name__ == "__main__":
    idle_power_saver = IdlePowerSaver()
    idle_power_saver.start_monitoring()
