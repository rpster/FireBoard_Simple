#!/usr/bin/env python3
"""
ATtiny85 I2C Control Board — Test / Example Script
===================================================
Run on the Raspberry Pi 5 after flashing the ATtiny85 and
reconnecting the I2C bus (SDA/SCL).

Requirements:
    pip install smbus2

Usage:
    python3 test_board.py
"""

import time
import sys

try:
    from smbus2 import SMBus
except ImportError:
    print("Install smbus2:  pip install smbus2 --break-system-packages")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────
I2C_BUS     = 1          # /dev/i2c-1 on Pi 5
BOARD_ADDR  = 0x20

REG_BUTTON   = 0x00
REG_SLIDE_SW = 0x01
REG_LED_MODE = 0x02

LED_OFF          = 0x00
LED_ON           = 0x01
LED_PULSE        = 0x02
LED_BLINK        = 0x03
LED_DOUBLE_PULSE = 0x04
LED_FAST_BLINK   = 0x05

MODE_NAMES = {
    LED_OFF:          "OFF",
    LED_ON:           "ON",
    LED_PULSE:        "PULSE (breathe)",
    LED_BLINK:        "BLINK",
    LED_DOUBLE_PULSE: "DOUBLE PULSE",
    LED_FAST_BLINK:   "FAST BLINK",
}

# Delay between I2C transactions (ms).
# The ATtiny85 USI slave needs time to process stop conditions
# and reset its state machine between transactions.
I2C_GAP = 0.01   # 10 ms


def read_register(bus, reg):
    """Read a single byte from a register with retry."""
    for attempt in range(3):
        try:
            val = bus.read_byte_data(BOARD_ADDR, reg)
            time.sleep(I2C_GAP)
            return val
        except OSError:
            time.sleep(0.05)
    raise OSError(f"Failed to read register 0x{reg:02X} after 3 attempts")


def write_register(bus, reg, value):
    """Write a single byte to a register with retry."""
    for attempt in range(3):
        try:
            bus.write_byte_data(BOARD_ADDR, reg, value)
            time.sleep(I2C_GAP)
            return
        except OSError:
            time.sleep(0.05)
    raise OSError(f"Failed to write register 0x{reg:02X} after 3 attempts")


def read_button(bus):
    val = read_register(bus, REG_BUTTON)
    return "PRESSED" if val else "RELEASED"


def read_slide_switch(bus):
    val = read_register(bus, REG_SLIDE_SW)
    return "ON" if val else "OFF"


def set_led_mode(bus, mode):
    write_register(bus, REG_LED_MODE, mode)
    print(f"  LED mode set to: {MODE_NAMES.get(mode, f'0x{mode:02X}')}")


def demo_all_modes(bus):
    """Cycle through every LED mode for 3 seconds each."""
    modes = [LED_OFF, LED_ON, LED_PULSE, LED_BLINK, LED_DOUBLE_PULSE, LED_FAST_BLINK]
    for mode in modes:
        print(f"\n--- {MODE_NAMES[mode]} ---")
        set_led_mode(bus, mode)
        for _ in range(15):
            try:
                btn = read_button(bus)
                sw  = read_slide_switch(bus)
                print(f"  Button: {btn:10s}  Slide SW: {sw}", end="\r")
            except OSError:
                pass
            time.sleep(0.2)
        print()


def interactive_menu(bus):
    """Simple interactive menu."""
    while True:
        print("\n╔══════════════════════════════════╗")
        print("║   ATtiny85 I2C Control Board     ║")
        print("╠══════════════════════════════════╣")
        print("║  1. Read button                  ║")
        print("║  2. Read slide switch            ║")
        print("║  3. LED OFF                      ║")
        print("║  4. LED ON                       ║")
        print("║  5. LED PULSE                    ║")
        print("║  6. LED BLINK                    ║")
        print("║  7. LED DOUBLE PULSE             ║")
        print("║  8. LED FAST BLINK               ║")
        print("║  9. Demo all modes               ║")
        print("║  m. Continuous monitor            ║")
        print("║  0. Quit                         ║")
        print("╚══════════════════════════════════╝")

        choice = input("Select: ").strip()

        if   choice == "1": print(f"  Button: {read_button(bus)}")
        elif choice == "2": print(f"  Slide switch: {read_slide_switch(bus)}")
        elif choice == "3": set_led_mode(bus, LED_OFF)
        elif choice == "4": set_led_mode(bus, LED_ON)
        elif choice == "5": set_led_mode(bus, LED_PULSE)
        elif choice == "6": set_led_mode(bus, LED_BLINK)
        elif choice == "7": set_led_mode(bus, LED_DOUBLE_PULSE)
        elif choice == "8": set_led_mode(bus, LED_FAST_BLINK)
        elif choice == "9": demo_all_modes(bus)
        elif choice == "m":
            print("  Monitoring (Ctrl+C to stop)...")
            errors = 0
            try:
                while True:
                    try:
                        btn = read_button(bus)
                        sw  = read_slide_switch(bus)
                        led = read_register(bus, REG_LED_MODE)
                        print(f"  BTN: {btn:10s}  SW: {sw:4s}  "
                              f"LED: {MODE_NAMES.get(led, '?'):16s}"
                              f"  (errors: {errors})", end="\r")
                    except OSError:
                        errors += 1
                    time.sleep(0.15)
            except KeyboardInterrupt:
                print()
        elif choice == "0":
            set_led_mode(bus, LED_OFF)
            print("Goodbye!")
            break
        else:
            print("  Invalid selection.")


def main():
    print(f"Opening I2C bus {I2C_BUS}, device address 0x{BOARD_ADDR:02X}")
    try:
        with SMBus(I2C_BUS) as bus:
            # Quick connectivity test
            try:
                read_register(bus, REG_BUTTON)
                print("  Board detected!")
            except OSError:
                print("  ERROR: No device at address "
                      f"0x{BOARD_ADDR:02X} on bus {I2C_BUS}.")
                print("  Check wiring and that the ATtiny85 is programmed.")
                sys.exit(1)

            interactive_menu(bus)

    except FileNotFoundError:
        print(f"  ERROR: /dev/i2c-{I2C_BUS} not found.")
        print("  Enable I2C: sudo raspi-config → Interface Options → I2C")
        sys.exit(1)


if __name__ == "__main__":
    main()
