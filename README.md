# 1394Pi - FireWire Controller for Raspberry Pi 5

A lightweight headless system for controlling DV camera capture via FireWire (IEEE 1394)
using a Raspberry Pi 5 or CM5 with a PCIe FireWire card, custom I2C user control board, and I2C OLED display.

## Hardware Requirements

- Raspberry Pi 5 (also compatible with CM5)
- Custom kernel with FireWire support (standard Raspberry Pi OS images do not include it — see [Kernel Setup](wiki/Kernel-Setup.md))
- PCIe FireWire (IEEE 1394) card
- External USB drive or microSD card reader (USB 2.0)
- Custom I2C user control board (button, LED, slide switch)
- I2C 128×32 OLED display (SSD1306)

## I2C Address Map

| Device              | Default Address |
|---------------------|-----------------|
| User Control Board  | `0x20`          |
| OLED Display        | `0x3C`          |

## User Control Board I2C Protocol

The custom I2C user control board communicates via the following register map:

| Register | R/W | Description                                      |
|----------|-----|--------------------------------------------------|
| `0x00`   | R   | Button state (bit 0: pressed, bit 1: held)       |
| `0x01`   | R   | Slide switch state (0 = OFF, 1 = ON)             |
| `0x02`   | W   | LED control (0x00=off, 0x01=on, 0x02=pulse, 0x03=blink) |

## Installation

```bash
sudo ./install.sh
```

This will:
1. Install Python dependencies
2. Copy scripts to `/opt/firewire-controller/`
3. Install and enable the systemd service
4. Ensure I2C is enabled

## Modes

### Camera Controlled ON (slide switch = ON)
- dvgrab runs with `--record-start` flag
- Camera's record button controls capture start/stop
- LED pulses when waiting, blinks when recording

### Camera Controlled OFF (slide switch = OFF)
- dvgrab runs with `-i` flag (interactive)
- User button controls capture start/stop
- LED off when idle, on when recording

## Format Disk Feature
- While not recording, press and hold button for 5 seconds and release
- Confirmation prompt appears on OLED
- Hold button for 5 seconds to confirm format, or single-press to cancel
- Formats external microSD as exFAT with label "DVMEDIA"

## File Structure

```
firewire-controller/
├── User Control Board/     # ATtiny85 I2C control board
│   ├── firmware/
│   │   ├── main.c          # ATtiny85 firmware source
│   │   └── Makefile        # Build & flash targets (Pi 5 SPI)
│   ├── test_board.py       # Interactive test script
│   └── README.md           # Board documentation
├── install.sh              # Installation script
├── requirements.txt        # Python dependencies
├── config.py               # System configuration constants
├── hardware.py             # I2C hardware abstraction layer
├── oled_display.py         # OLED display manager
├── storage.py              # External microSD detection & formatting
├── dvgrab_manager.py       # dvgrab process manager
├── controller.py           # Main state machine / controller
├── firewire-controller.service  # systemd unit file
└── README.md
```
