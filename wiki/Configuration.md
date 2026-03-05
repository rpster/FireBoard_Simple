# Configuration

All tunable parameters are defined in `config.py`. No configuration files are read at runtime; values are Python constants.

## I2C Settings

| Constant | Value | Description |
|----------|-------|-------------|
| `I2C_BUS` | `1` | I2C bus number (`/dev/i2c-1`) |
| `I2C_GAP` | `0.01` (10ms) | Pause after each I2C transaction for ATtiny85 USI |
| `I2C_RETRIES` | `3` | Retry attempts on I2C read/write failure |
| `I2C_RETRY_DELAY` | `0.05` (50ms) | Backoff between retry attempts |

## Hardware Addresses

| Constant | Value | Description |
|----------|-------|-------------|
| `UCB_I2C_ADDR` | `0x20` | User control board I2C address |
| `UCB_REG_BUTTON` | `0x00` | Button state register (R) |
| `UCB_REG_SWITCH` | `0x01` | Slide switch register (R) |
| `UCB_REG_LED` | `0x02` | LED control register (W) |
| `OLED_I2C_ADDR` | `0x3C` | OLED display I2C address |
| `OLED_WIDTH` | `128` | Display width in pixels |
| `OLED_HEIGHT` | `32` | Display height in pixels |

## LED Modes

| Constant | Value | Description |
|----------|-------|-------------|
| `LED_OFF` | `0x00` | LED off |
| `LED_ON` | `0x01` | LED on (steady) |
| `LED_PULSE` | `0x02` | Slow pulse |
| `LED_BLINK` | `0x03` | Blink |
| `LED_DOUBLE_PULSE` | `0x04` | Double pulse |
| `LED_FAST_BLINK` | `0x05` | Fast blink |

## OLED Brightness

| Constant | Value | Description |
|----------|-------|-------------|
| `OLED_DEFAULT_BRIGHTNESS` | `200` | Startup brightness |
| `BRIGHTNESS_HIGH` | `255` | Menu option: High |
| `BRIGHTNESS_MEDIUM` | `80` | Menu option: Medium |
| `BRIGHTNESS_LOW` | `1` | Menu option: Low |

## Storage

| Constant | Value | Description |
|----------|-------|-------------|
| `MOUNT_BASE` | `"/mnt/dvmedia"` | Mount point for external microSD |
| `FS_TYPE` | `"exfat"` | Filesystem type for formatting |
| `FS_LABEL` | `"DVMEDIA"` | Volume label applied during format |
| `SAVE_DIR_NAME` | `"captures"` | Subdirectory name for capture files |

## dvgrab

| Constant | Value | Description |
|----------|-------|-------------|
| `DVGRAB_BIN` | `"/usr/local/bin/dvgrab"` | Path to dvgrab binary |
| `FW_DEVICE_PATH` | `"/dev/fw1"` | FireWire device node for camera detection |
| `FW_INIT_DELAY` | `10` | Seconds to wait at startup for FireWire subsystem |
| `FW_BUS_SETTLE_DELAY` | `3` | Seconds to wait after `/dev/fw1` appears |
| `DVGRAB_FILE_PREFIX` | `"clip-"` | Filename prefix for captured DV files |
| `CAPTURE_STARTED_PATTERN` | `"Capture started"` | dvgrab output indicating recording began |
| `CAPTURE_STOPPED_PATTERN` | `"Capture stopped"` | dvgrab output indicating recording ended |
| `CAMERA_DISCONNECTED_PATTERN` | `"send oops"` | dvgrab output indicating camera disconnected |

## Timing

| Constant | Value | Description |
|----------|-------|-------------|
| `POLL_INTERVAL` | `0.05` (50ms) | Main loop tick for active states |
| `POLL_INTERVAL_IDLE` | `0.2` (200ms) | Main loop tick for idle states |
| `FORMAT_HOLD_TRIGGER` | `5.0` | Seconds to hold button to enter format mode |
| `FORMAT_CONFIRM_HOLD` | `5.0` | Seconds to hold button to confirm format |
| `CAMERA_RETRY_DELAY` | `5.0` | Seconds between camera reconnection attempts |
| `STORAGE_CHECK_INTERVAL` | `2.0` | Seconds between storage presence checks |
| `CARD_CONFIRM_DELAY` | `3.0` | Seconds to show "Card OK!" confirmation |
| `FW_DEVICE_CHECK_INTERVAL` | `1.0` | Seconds between FireWire device checks |
| `DEBOUNCE_TIME` | `0.08` (80ms) | Button debounce window |
| `STOP_REC_SETTLE` | `1.0` | Settle time after stopping recording |
| `SWITCH_DEBOUNCE_TIME` | `0.3` (300ms) | Slide switch debounce window |
| `INPUT_SETTLE_TIME` | `1.0` | Ignore button input after mode switch |

## Menu

| Constant | Value | Description |
|----------|-------|-------------|
| `MENU_HOLD_TRIGGER` | `2.5` | Seconds to hold button to open menu |
| `MENU_SELECT_HOLD` | `2.0` | Seconds to hold button to select menu item |
| `MENU_VISIBLE_COUNT` | `2` | Menu items visible at once on 128x32 display |
| `MENU_RESULT_DISPLAY_TIME` | `3.0` | Seconds to show toggle result (e.g., "Wifi: ON") |

## File Paths

| Constant | Value | Description |
|----------|-------|-------------|
| `LOG_FILE` | `"/var/log/firewire-controller.log"` | Application log output |
| `PID_FILE` | `"/run/firewire-controller.pid"` | PID file for running service |
