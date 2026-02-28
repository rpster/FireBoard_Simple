"""
Firewire Controller - Hardware Abstraction Layer
Handles I2C communication with the custom user control board.
"""

import logging
import time

import smbus2

import config

log = logging.getLogger(__name__)


class UserControlBoard:
    """Driver for the custom I2C user control board (button, LED, slide switch)."""

    def __init__(self, bus: smbus2.SMBus | None = None):
        self._bus = bus or smbus2.SMBus(config.I2C_BUS)
        self._addr = config.UCB_I2C_ADDR
        self._last_button_raw = False
        self._button_press_start: float | None = None
        self._last_debounce_time: float = 0.0
        self._debounced_state = False
        self._prev_debounced_state = False
        self._verify_device()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _verify_device(self):
        """Quick probe to make sure the board is on the bus."""
        try:
            self._bus.read_byte_data(self._addr, config.UCB_REG_BUTTON)
            log.info("User control board detected at 0x%02X", self._addr)
        except OSError:
            log.error("User control board NOT found at 0x%02X", self._addr)
            raise

    def _read_reg(self, reg: int) -> int:
        try:
            return self._bus.read_byte_data(self._addr, reg)
        except OSError:
            log.warning("I2C read error addr=0x%02X reg=0x%02X", self._addr, reg)
            return 0

    def _write_reg(self, reg: int, value: int):
        try:
            self._bus.write_byte_data(self._addr, reg, value)
        except OSError:
            log.warning("I2C write error addr=0x%02X reg=0x%02X val=0x%02X",
                        self._addr, reg, value)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def read_button_raw(self) -> bool:
        """Return True if the button is currently physically pressed."""
        val = self._read_reg(config.UCB_REG_BUTTON)
        return bool(val & 0x01)

    def poll_button(self) -> dict:
        """
        Call every tick.  Returns a dict:
            pressed        – True on the tick the button transitions to pressed
            released       – True on the tick the button transitions to released
            is_held        – True while button is held down
            hold_duration  – seconds the button has been held (0 if not held)
        """
        now = time.monotonic()
        raw = self.read_button_raw()

        # Debounce
        if raw != self._last_button_raw:
            self._last_debounce_time = now
        self._last_button_raw = raw

        if (now - self._last_debounce_time) >= config.DEBOUNCE_TIME:
            self._prev_debounced_state = self._debounced_state
            self._debounced_state = raw

        pressed = self._debounced_state and not self._prev_debounced_state
        released = not self._debounced_state and self._prev_debounced_state

        if pressed:
            self._button_press_start = now
        if released:
            self._button_press_start = None

        hold_duration = 0.0
        if self._debounced_state and self._button_press_start is not None:
            hold_duration = now - self._button_press_start

        return {
            "pressed": pressed,
            "released": released,
            "is_held": self._debounced_state,
            "hold_duration": hold_duration,
        }

    def read_switch(self) -> bool:
        """Return True when slide switch is in ON position (Camera Controlled ON)."""
        val = self._read_reg(config.UCB_REG_SWITCH)
        return bool(val & 0x01)

    def set_led(self, mode: int):
        """Set LED mode: LED_OFF, LED_ON, LED_PULSE, LED_BLINK, LED_DOUBLE_PULSE."""
        self._write_reg(config.UCB_REG_LED, mode)
        log.debug("LED set to 0x%02X", mode)

    def close(self):
        self._bus.close()
