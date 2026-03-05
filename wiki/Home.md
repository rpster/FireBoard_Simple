# 1394Pi - FireWire Controller for Raspberry Pi 5

A headless DV camera capture system built on the Raspberry Pi 5. It uses a PCIe FireWire (IEEE 1394) card to interface with DV cameras, a custom ATtiny85-based I2C control board for user input, and an SSD1306 OLED display for real-time feedback. Captured footage is saved to an external USB microSD card formatted as exFAT.

## Features

- **Dual recording modes** - Camera-controlled (camera's record button drives capture) or manual (button on the control board)
- **Real-time OLED display** - Mode indicators, live recording timers, menu navigation, status messages
- **On-device menu system** - Adjust brightness, toggle WiFi/Bluetooth, format storage
- **Hot-swappable storage** - Auto-detects USB microSD cards, mounts and creates capture directories
- **Safe formatting** - Two-stage confirmation to wipe and reformat the microSD as exFAT
- **Automatic recovery** - Detects camera disconnection, storage removal, and dvgrab crashes; recovers gracefully
- **Runs as a systemd service** - Starts on boot, restarts on failure, logs to journal

## Wiki Pages

| Page | Description |
|------|-------------|
| [Hardware Setup](Hardware-Setup) | Bill of materials, I2C wiring, register protocol |
| [Kernel Setup](Kernel-Setup) | Building a custom kernel with FireWire support |
| [Installation](Installation) | System setup, dependencies, running the installer |
| [dvgrab](dvgrab) | Fork details, build instructions, capture modes |
| [User Guide](User-Guide) | How to operate the controller day-to-day |
| [Architecture](Architecture) | State machine, module design, developer reference |
| [Configuration](Configuration) | All tunable parameters in `config.py` |
| [User Control Board](User-Control-Board) | ATtiny85 firmware, build guide, SPI flashing from Pi 5 |
| [Troubleshooting](Troubleshooting) | Common issues and how to resolve them |

## File Structure

```
firewire-controller/
├── config.py                    # System configuration constants
├── hardware.py                  # I2C hardware abstraction layer
├── oled_display.py              # OLED display manager
├── storage.py                   # External microSD detection & formatting
├── dvgrab_manager.py            # dvgrab process manager
├── controller.py                # Main state machine / controller
├── install.sh                   # Installation script
├── requirements.txt             # Python dependencies
├── firewire-controller.service  # systemd unit file
└── README.md
```
