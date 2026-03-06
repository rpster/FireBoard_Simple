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
LED_FAST_BLINK = 0x05

# OLED display (SSD1306 128x32)
OLED_I2C_ADDR = 0x3C
OLED_WIDTH = 128
OLED_HEIGHT = 32
OLED_DEFAULT_BRIGHTNESS = 200
BRIGHTNESS_HIGH = 255
BRIGHTNESS_MEDIUM = 80
BRIGHTNESS_LOW = 1

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
FW_INIT_DELAY = 10                  # Seconds to wait at startup for FireWire subsystem
FW_BUS_SETTLE_DELAY = 3             # Seconds to wait after /dev/fw1 appears for bus to settle
DVGRAB_FILE_PREFIX = "clip-"
# Patterns we watch for in dvgrab stdout/stderr
CAPTURE_STARTED_PATTERN = "Capture started"
CAPTURE_STOPPED_PATTERN = "Capture stopped"
CAMERA_DISCONNECTED_PATTERN = "send oops"
FIREWIRE_DEVICE = "/dev/fw1"

# ---------------------------------------------------------------------------
# Timing (seconds)
# ---------------------------------------------------------------------------
POLL_INTERVAL = 0.05          # 50 ms main loop tick (active states)
POLL_INTERVAL_IDLE = 0.2      # 200 ms for idle states
FORMAT_HOLD_TRIGGER = 5.0     # Hold to enter format mode
FORMAT_CONFIRM_HOLD = 5.0     # Hold to confirm format
CAMERA_RETRY_DELAY = 5.0      # Wait before retrying after no camera
STORAGE_CHECK_INTERVAL = 2.0  # Seconds between external drive presence checks
CARD_CONFIRM_DELAY = 3.0      # Seconds to show "Card OK!" confirmation
FW_DEVICE_CHECK_INTERVAL = 1.0  # Seconds between FireWire device presence checks
STOP_REC_SETTLE = 1.0         # Seconds to settle after saving screen displays
SWITCH_DEBOUNCE_TIME = 0.3    # Slide switch debounce
INPUT_SETTLE_TIME = 1.0       # Ignore button after mode switch (I2C settles)

# Menu
MENU_HOLD_TRIGGER = 2.5        # Hold to open menu
MENU_SELECT_HOLD = 2.0         # Hold 2s to select menu item
MENU_VISIBLE_COUNT = 2         # Menu items visible at once on 128x32 display
MENU_RESULT_DISPLAY_TIME = 3.0 # Seconds to show toggle result

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
LOG_FILE = "/var/log/firewire-controller.log"
PID_FILE = "/run/firewire-controller.pid"
