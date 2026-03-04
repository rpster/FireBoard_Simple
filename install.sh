#!/bin/bash
# ============================================================================
# Firewire Controller - Installer
# Run as root: sudo ./install.sh
# ============================================================================
set -euo pipefail

INSTALL_DIR="/opt/firewire-controller"
SERVICE_NAME="firewire-controller"

echo "=== Firewire Controller Installer ==="

# Check root
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (sudo ./install.sh)"
    exit 1
fi

# -------------------------------------------------------
# 1. Enable I2C if not already enabled
# -------------------------------------------------------
echo "[1/6] Ensuring I2C is enabled..."
if ! grep -q "^dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null; then
    echo "dtparam=i2c_arm=on" >> /boot/firmware/config.txt
    echo "  I2C added to config.txt (reboot required)"
fi

# Load i2c module now if not loaded
modprobe i2c-dev 2>/dev/null || true

if ! grep -q "i2c-dev" /etc/modules 2>/dev/null; then
    echo "i2c-dev" >> /etc/modules
fi

# Load FireWire modules now if not loaded
modprobe firewire-core 2>/dev/null || true
modprobe firewire-ohci 2>/dev/null || true

for mod in firewire-core firewire-ohci; do
    if ! grep -q "$mod" /etc/modules 2>/dev/null; then
        echo "$mod" >> /etc/modules
        echo "  $mod added to /etc/modules"
    fi
done

# -------------------------------------------------------
# 2. Install system packages
# -------------------------------------------------------
echo "[2/6] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq \
    python3-pip \
    python3-smbus \
    python3-pil \
    i2c-tools \
    exfatprogs \
    libraw1394-dev \
    libavc1394-dev \
    libiec61883-dev \
    > /dev/null

# -------------------------------------------------------
# 3. Install Python packages
# -------------------------------------------------------
echo "[3/6] Installing Python packages..."
pip3 install --break-system-packages -q \
    smbus2 \
    luma.oled \
    luma.core \
    Pillow

# -------------------------------------------------------
# 4. Create mount point
# -------------------------------------------------------
echo "[4/6] Creating mount point..."
mkdir -p /mnt/dvmedia

# -------------------------------------------------------
# 5. Install application files
# -------------------------------------------------------
echo "[5/6] Installing application to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for f in config.py hardware.py oled_display.py storage.py dvgrab_manager.py controller.py requirements.txt; do
    cp "${SCRIPT_DIR}/${f}" "${INSTALL_DIR}/${f}"
done

chmod +x "${INSTALL_DIR}/controller.py"

# -------------------------------------------------------
# 6. Install and enable systemd service
# -------------------------------------------------------
echo "[6/6] Installing systemd service..."
cp "${SCRIPT_DIR}/firewire-controller.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

echo ""
echo "=== Installation complete ==="
echo ""
echo "The service will start automatically on next boot."
echo "To start now:  sudo systemctl start ${SERVICE_NAME}"
echo "To view logs:  sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "NOTE: If I2C was just enabled, a reboot is required."
echo "NOTE: Ensure your custom dvgrab binary is at /usr/local/bin/dvgrab"
