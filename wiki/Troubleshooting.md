# Troubleshooting

## "No Card" on Display

The controller cannot find a USB-connected microSD card.

**Check:**
1. Ensure the USB microSD reader is plugged in with a card inserted
2. Verify the device appears: `ls /dev/sd*`
3. Check sysfs for USB block devices: `ls /sys/block/ | grep -v loop | grep -v ram | grep -v mmcblk | grep -v zram`
4. Try a different USB port or card reader
5. Check the system log: `dmesg | tail -20`

The controller polls for storage every 2 seconds. Once a card is detected, it will automatically mount and proceed.

## "No Camera" on Display

The FireWire device `/dev/fw1` is not present.

**Check:**
1. Ensure the DV camera is powered on and connected via FireWire
2. Verify the device node exists: `ls /dev/fw*`
3. Check FireWire kernel modules are loaded:
   ```bash
   lsmod | grep firewire
   ```
   You should see `firewire_core` and `firewire_ohci`.
4. If modules are not loaded:
   ```bash
   sudo modprobe firewire-core
   sudo modprobe firewire-ohci
   ```
5. Check the PCIe FireWire card is recognized: `lspci | grep 1394`
6. Try power-cycling the camera

The controller retries camera detection every 5 seconds. The menu is still accessible in this state (hold button for 2.5s).

## OLED Display Not Working

**Check:**
1. Verify the display is connected to I2C bus 1
2. Scan for I2C devices:
   ```bash
   sudo i2cdetect -y 1
   ```
   You should see `3c` in the output grid.
3. Check the log for detection messages:
   ```bash
   grep -i oled /var/log/firewire-controller.log
   ```

If the OLED is not detected, the controller runs in **headless mode** where all display calls are silent no-ops. The controller is fully functional without the display.

## I2C Errors in Logs

Messages like `I2C read failed addr=0x20 reg=0x00 after 3 attempts` indicate communication issues with the control board.

**Causes:**
- Loose I2C wiring (SDA/SCL connections)
- Missing pull-up resistors on the I2C bus
- ATtiny85 not powered or not running firmware
- Bus contention from other devices

**Mitigations built into the controller:**
- Each transaction retries up to 3 times with 50ms backoff
- On persistent failure, the last-known-good value is used
- 10ms inter-transaction gap accommodates ATtiny85 USI timing

## Format Fails

**Check:**
1. Ensure `exfatprogs` is installed: `which mkfs.exfat`
2. Verify the device is not busy: `lsof /mnt/dvmedia`
3. Check that the service has write access to the block device (the systemd unit allows `block-sd`)
4. Review the log for specific errors:
   ```bash
   grep -i format /var/log/firewire-controller.log
   ```

The format pipeline runs: `wipefs` → `sfdisk` → `partprobe` → `mkfs.exfat` → mount. Any step can fail independently.

## Service Won't Start

**Check:**
1. Service status:
   ```bash
   sudo systemctl status firewire-controller
   ```
2. Recent logs:
   ```bash
   sudo journalctl -u firewire-controller -n 50
   ```
3. Verify dvgrab binary exists at `/usr/local/bin/dvgrab`:
   ```bash
   ls -la /usr/local/bin/dvgrab
   ```
4. Verify application files are installed:
   ```bash
   ls /opt/firewire-controller/
   ```
5. Check Python dependencies:
   ```bash
   python3 -c "import smbus2; import luma.oled; import PIL; print('OK')"
   ```

The service is configured to restart on failure with a 5-second delay. Check if it's crash-looping:
```bash
sudo systemctl status firewire-controller | grep "Active:"
```

## Button Not Responding

**Possible causes:**
- **Input settle period**: After mode switches, button input is suppressed for 1 second to let I2C settle. This is normal.
- **Debounce window**: Button presses shorter than 80ms are filtered out.
- **Already in a hold state**: If the button was held (e.g., for menu), release it fully before pressing again.

**Check:**
1. Verify the control board is detected:
   ```bash
   sudo i2cdetect -y 1
   ```
   Address `0x20` should appear.
2. Read the button register directly:
   ```bash
   sudo i2cget -y 1 0x20 0x00
   ```
   Should return `0x01` when pressed, `0x00` when released.

## WiFi/BT Toggle Shows "N/A"

The rfkill interface for the wireless device was not found.

**Check:**
1. Verify rfkill is available:
   ```bash
   /usr/sbin/rfkill
   ```
2. Check available wireless interfaces:
   ```bash
   rfkill list
   ```
   You should see entries with type `wlan` and/or `bluetooth`.
3. If no wireless hardware is present, the toggle will always show "N/A".

## dvgrab Crashes Repeatedly

If dvgrab keeps dying and the controller cycles between recording mode and "No Camera":

**Check:**
1. Verify the dvgrab binary works standalone:
   ```bash
   /usr/local/bin/dvgrab --version
   ```
2. Test manual capture:
   ```bash
   /usr/local/bin/dvgrab -i /tmp/test-
   ```
3. Check for FireWire permission issues in `dmesg`
4. Ensure the FireWire libraries are installed:
   ```bash
   dpkg -l | grep -E "libraw1394|libavc1394|libiec61883"
   ```

## Viewing Logs

The controller logs to both the systemd journal and `/var/log/firewire-controller.log`.

```bash
# Live journal output
sudo journalctl -u firewire-controller -f

# Application log file
sudo tail -f /var/log/firewire-controller.log

# Filter for errors/warnings only
sudo grep -E "ERROR|WARNING" /var/log/firewire-controller.log
```
