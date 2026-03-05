# Installation

## Prerequisites

- Raspberry Pi 5 running Raspberry Pi OS (Debian-based)
- I2C enabled in boot configuration
- Internet connection for package installation

## Quick Install

```bash
sudo ./install.sh
```

The installer performs six steps:

1. **Enable I2C** - Adds `dtparam=i2c_arm=on` to `/boot/firmware/config.txt` and loads the `i2c-dev` kernel module. Also loads `firewire-core` and `firewire-ohci` modules and adds them to `/etc/modules` for persistence.

2. **Install system packages** -
   - `python3-pip`, `python3-smbus`, `python3-pil` - Python runtime
   - `i2c-tools` - I2C debugging utilities
   - `exfatprogs` - exFAT filesystem tools for microSD formatting
   - `libraw1394-dev`, `libavc1394-dev`, `libiec61883-dev` - FireWire development headers (needed to compile dvgrab)

3. **Install Python packages** -
   - `smbus2` - I2C communication
   - `luma.oled`, `luma.core` - OLED display driver
   - `Pillow` - Image rendering for display

4. **Create mount point** - Creates `/mnt/dvmedia` for external microSD mounting.

5. **Install application** - Copies source files to `/opt/firewire-controller/`.

6. **Install systemd service** - Copies the service unit to `/etc/systemd/system/` and enables it.

## dvgrab Binary

The controller requires a `dvgrab` binary at `/usr/local/bin/dvgrab`. This is the FireWire DV capture tool and may need to be compiled from source since it is not available in standard Raspberry Pi OS repositories.

## Managing the Service

```bash
# Start the service immediately
sudo systemctl start firewire-controller

# Stop the service
sudo systemctl stop firewire-controller

# View live logs
sudo journalctl -u firewire-controller -f

# Check service status
sudo systemctl status firewire-controller

# Disable auto-start on boot
sudo systemctl disable firewire-controller
```

The service is configured to restart automatically on failure with a 5-second delay.

## File Paths

| Path | Purpose |
|------|---------|
| `/opt/firewire-controller/` | Application source files |
| `/mnt/dvmedia/` | Mount point for external microSD |
| `/mnt/dvmedia/captures/` | Directory where DV captures are saved |
| `/var/log/firewire-controller.log` | Application log file |
| `/run/firewire-controller.pid` | PID file for the running service |
| `/usr/local/bin/dvgrab` | dvgrab binary |
| `/dev/i2c-1` | I2C bus device |
| `/dev/fw1` | FireWire device node (present when camera is connected) |

## Post-Install

- If I2C was just enabled, a **reboot is required**.
- Ensure the custom dvgrab binary is at `/usr/local/bin/dvgrab`.
- Connect the I2C user control board and OLED display before starting the service.
- Insert a microSD card in the USB reader.

## systemd Service Details

The service runs as root (required for I2C, mount, and format access) with the following hardening:

- `ProtectHome=yes` - No access to `/home`
- `ProtectSystem=strict` - Filesystem is read-only except for explicitly allowed paths
- `ReadWritePaths=/mnt/dvmedia /var/log /run /dev` - Write access for captures, logs, PID, and devices
- Device access restricted to I2C, rfkill, block devices (sd*), and FireWire character devices
