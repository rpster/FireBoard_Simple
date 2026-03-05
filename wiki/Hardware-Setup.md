# Hardware Setup

## Bill of Materials

| Component | Details |
|-----------|---------|
| Raspberry Pi 5 | Main compute board |
| PCIe FireWire card | IEEE 1394 interface, maps to `/dev/fw1` |
| USB microSD card reader | USB 2.0, used for capture storage |
| Custom I2C user control board | ATtiny85-based; provides button, LED, and slide switch |
| SSD1306 OLED display | 128x32 pixels, monochrome, I2C interface |

## I2C Bus

All peripherals share I2C bus 1 (`/dev/i2c-1`). The ATtiny85 USI slave requires a 10ms pause between I2C transactions to process stop conditions and reset its state machine.

| Device | Address |
|--------|---------|
| User Control Board | `0x20` |
| OLED Display | `0x3C` |

## User Control Board Register Protocol

The custom control board exposes three registers over I2C:

| Register | R/W | Description |
|----------|-----|-------------|
| `0x00` | R | **Button state** - bit 0: pressed, bit 1: held |
| `0x01` | R | **Slide switch** - 0 = OFF (manual mode), 1 = ON (camera-controlled mode) |
| `0x02` | W | **LED control** - write one of the mode values below |

### LED Modes

| Value | Mode | Usage |
|-------|------|-------|
| `0x00` | OFF | Manual mode idle |
| `0x01` | ON | Recording (manual mode), card detected confirmation |
| `0x02` | PULSE | Waiting for camera to start recording (camera-controlled mode) |
| `0x03` | BLINK | Format confirmation prompt, menu active |
| `0x04` | DOUBLE_PULSE | No storage or no camera detected |
| `0x05` | FAST_BLINK | Saving/syncing data to disk |

## I2C Communication Details

The driver implements reliability features to handle ATtiny85 USI timing constraints:

- **Inter-transaction gap**: 10ms pause after each read/write
- **Retries**: 3 attempts per transaction
- **Retry backoff**: 50ms between retry attempts
- **Fallback values**: On persistent failure, last-known-good register values are used

## FireWire Interface

The PCIe FireWire card is managed by the kernel's `firewire-core` and `firewire-ohci` modules. When a DV camera is connected, it appears as `/dev/fw1`. The controller checks for this device node to determine camera presence.

Capture is performed by `dvgrab`, a command-line tool for FireWire DV capture, which must be compiled and placed at `/usr/local/bin/dvgrab`.

## OLED Display

The SSD1306 is a 128x32 pixel monochrome OLED driven via the `luma.oled` Python library. The display is optional; if not detected at startup, the controller runs in headless mode with all display calls becoming silent no-ops. Brightness is adjustable through the menu system with three levels:

| Level | Contrast Value |
|-------|---------------|
| High | 255 |
| Medium | 80 |
| Low | 1 |

Default brightness at startup is 200.
