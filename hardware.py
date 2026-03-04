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
        self._last_good: dict[int, int] = {}  # reg -> last known good value
        self._last_button_raw = False
        self._button_press_start: float | None = None
        self._last_debounce_time: float = 0.0
        self._debounced_state = False
        self._prev_debounced_state = False
        self._last_switch_raw = False
        self._switch_debounce_time: float = 0.0
        self._debounced_switch = False
        self._verify_device()
        # Seed switch debounce state from hardware so the first read_switch()
        # returns the actual position rather than the hardcoded False default.
        raw_switch = bool(self._read_reg(config.UCB_REG_SWITCH) & 0x01)
        self._last_switch_raw = raw_switch
        self._debounced_switch = raw_switch

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _verify_device(self):
        """Quick probe to make sure the board is on the bus."""
        try:
            self._read_reg(config.UCB_REG_BUTTON)
            log.info("User control board detected at 0x%02X", self._addr)
        except OSError:
            log.error("User control board NOT found at 0x%02X", self._addr)
            raise

    def _read_reg(self, reg: int) -> int:
        """Read a register with inter-transaction gap and retries.

        The ATtiny85 USI slave needs time to process I2C stop conditions
        and reset its state machine between transactions.
        """
        for attempt in range(config.I2C_RETRIES):
            try:
                val = self._bus.read_byte_data(self._addr, reg)
                time.sleep(config.I2C_GAP)
                self._last_good[reg] = val
                return val
            except OSError:
                time.sleep(config.I2C_RETRY_DELAY)
        log.warning("I2C read failed addr=0x%02X reg=0x%02X after %d attempts",
                    self._addr, reg, config.I2C_RETRIES)
        return self._last_good.get(reg, 0)

    def _write_reg(self, reg: int, value: int):
        """Write a register with inter-transaction gap and retries."""
        for attempt in range(config.I2C_RETRIES):
            try:
                self._bus.write_byte_data(self._addr, reg, value)
                time.sleep(config.I2C_GAP)
                return
            except OSError:
                time.sleep(config.I2C_RETRY_DELAY)
        log.warning("I2C write failed addr=0x%02X reg=0x%02X val=0x%02X after %d attempts",
                    self._addr, reg, value, config.I2C_RETRIES)

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

        # Snapshot previous state BEFORE any update (every tick)
        self._prev_debounced_state = self._debounced_state

        # Only accept a new value once the signal is stable
        if (now - self._last_debounce_time) >= config.DEBOUNCE_TIME:
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
        """Return debounced switch state. True = Camera Controlled ON."""
        now = time.monotonic()
        raw = bool(self._read_reg(config.UCB_REG_SWITCH) & 0x01)

        if raw != self._last_switch_raw:
            self._switch_debounce_time = now
        self._last_switch_raw = raw

        if (now - self._switch_debounce_time) >= config.SWITCH_DEBOUNCE_TIME:
            self._debounced_switch = raw

        return self._debounced_switch

    def reset_button(self):
        """Reset button state after mode transitions.

        Sets debounced state to True so that a noisy line reading
        as 'pressed' does NOT generate a False→True edge.  A real
        press will only register after the line is first seen as
        released (True→False) then pressed again (False→True).
        """
        now = time.monotonic()
        raw = self.read_button_raw()
        self._last_button_raw = raw
        self._last_debounce_time = now
        self._debounced_state = raw
        self._prev_debounced_state = raw
        self._button_press_start = None

    def set_led(self, mode: int):
        """Set LED mode: LED_OFF, LED_ON, LED_PULSE, LED_BLINK, LED_DOUBLE_PULSE."""
        self._write_reg(config.UCB_REG_LED, mode)
        log.debug("LED set to 0x%02X", mode)

    def close(self):
        self._bus.close()
