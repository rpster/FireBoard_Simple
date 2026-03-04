"""
Firewire Controller - Configuration Constants
All tunable parameters and hardware addresses in one place.
"""

# ---------------------------------------------------------------------------
# I2C
# ---------------------------------------------------------------------------
I2C_BUS = 1  # /dev/i2c-1 on Raspberry Pi 5
I2C_GAP = 0.01          # 10 ms pause after each I2C transaction (ATtiny85 USI needs this)
I2C_RETRIES = 3         # retry attempts on I2C failure
I2C_RETRY_DELAY = 0.05  # 50 ms backoff between retries

# Custom user control board
UCB_I2C_ADDR = 0x20
UCB_REG_BUTTON = 0x00      # R  - bit0: pressed, bit1: held
UCB_REG_SWITCH = 0x01      # R  - 0=OFF, 1=ON
UCB_REG_LED = 0x02         # W  - 0x00=off, 0x01=on, 0x02=pulse, 0x03=blink

LED_OFF = 0x00
LED_ON = 0x01
LED_PULSE = 0x02
LED_BLINK = 0x03
LED_DOUBLE_PULSE = 0x04

# OLED display (SSD1306 128x32)
OLED_I2C_ADDR = 0x3C
OLED_WIDTH = 128
OLED_HEIGHT = 32

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
MOUNT_BASE = "/mnt/dvmedia"
FS_TYPE = "exfat"
FS_LABEL = "DVMEDIA"
SAVE_DIR_NAME = "captures"

# ---------------------------------------------------------------------------
# dvgrab
# ---------------------------------------------------------------------------
DVGRAB_BIN = "/usr/local/bin/dvgrab"
FW_DEVICE_PATH = "/dev/fw1"         # FireWire device node; presence = camera connected
DVGRAB_FILE_PREFIX = "clip-"
# Patterns we watch for in dvgrab stdout/stderr
CAPTURE_STARTED_PATTERN = "Capture started"
CAPTURE_STOPPED_PATTERN = "Capture stopped"
CAMERA_DISCONNECTED_PATTERN = "send oops"

# ---------------------------------------------------------------------------
# Timing (seconds)
# ---------------------------------------------------------------------------
POLL_INTERVAL = 0.05          # 50 ms main loop tick
FORMAT_HOLD_TRIGGER = 5.0     # Hold to enter format mode
FORMAT_CONFIRM_HOLD = 5.0     # Hold to confirm format
CAMERA_RETRY_DELAY = 5.0      # Wait before retrying after no camera
STORAGE_CHECK_INTERVAL = 2.0  # Seconds between external drive presence checks
DEBOUNCE_TIME = 0.15          # Button debounce
SWITCH_DEBOUNCE_TIME = 0.3    # Slide switch debounce
INPUT_SETTLE_TIME = 1.0       # Ignore button after mode switch (I2C settles)

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
LOG_FILE = "/var/log/firewire-controller.log"
PID_FILE = "/run/firewire-controller.pid"
