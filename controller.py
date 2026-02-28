#!/usr/bin/env python3
"""
Firewire Controller - Main State Machine
Orchestrates the user control board, OLED display, dvgrab, and storage.
Runs as a systemd service after boot.
"""

import logging
import os
import signal
import sys
import time

import config
from hardware import UserControlBoard
from oled_display import OledDisplay
from dvgrab_manager import DvgrabManager
from storage import detect_external_sd, mount_storage, format_storage

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("controller")


# ---------------------------------------------------------------------------
# State definitions
# ---------------------------------------------------------------------------
class State:
    STARTUP = "startup"
    NO_STORAGE = "no_storage"
    CAM_ON_WAITING = "cam_on_waiting"
    CAM_ON_RECORDING = "cam_on_recording"
    CAM_OFF_READY = "cam_off_ready"
    CAM_OFF_RECORDING = "cam_off_recording"
    FORMAT_CONFIRM = "format_confirm"
    FORMATTING = "formatting"


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
class FirewireController:
    def __init__(self):
        self._running = True
        self._state = State.STARTUP
        self._prev_switch: bool | None = None
        self._camera_controlled = False
        self._prev_clip_str = ""

        # Hardware
        self.ucb = UserControlBoard()
        self.oled = OledDisplay()
        self.dvgrab: DvgrabManager | None = None
        self.storage_info: dict | None = None

        # Format-mode tracking
        self._format_hold_start: float | None = None

        # Signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        log.info("Received signal %d – shutting down", signum)
        self._running = False

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------
    def startup(self):
        """Run once after boot."""
        log.info("=== Firewire Controller starting ===")

        # Write PID file
        with open(config.PID_FILE, "w") as f:
            f.write(str(os.getpid()))

        # Show splash
        self.oled.show_startup()
        time.sleep(1)

        # Detect storage
        self.storage_info = detect_external_sd()
        if self.storage_info is None:
            log.warning("No external microSD detected")
            self.oled.show_no_card()
            self.ucb.set_led(config.LED_DOUBLE_PULSE)
            self._state = State.NO_STORAGE
            # Keep polling until storage appears or we're stopped
            while self._running and self.storage_info is None:
                time.sleep(2)
                self.storage_info = detect_external_sd()
            if not self._running:
                return

        if not mount_storage(self.storage_info):
            log.error("Failed to mount external storage")
            self.oled.show_error("Mount failed")
            time.sleep(3)

        # Init dvgrab manager
        self.dvgrab = DvgrabManager(self.storage_info["save_dir"])

        # Read initial switch position and enter appropriate mode
        self._camera_controlled = self.ucb.read_switch()
        self._enter_mode(self._camera_controlled)

    # ------------------------------------------------------------------
    # Mode transitions
    # ------------------------------------------------------------------
    def _enter_mode(self, camera_controlled: bool):
        """Transition into the selected mode."""
        self._camera_controlled = camera_controlled
        mode_name = "Cam Ctrl ON" if camera_controlled else "Cam Ctrl OFF"
        log.info("Entering mode: %s", mode_name)
        self.oled.show_mode(mode_name)
        time.sleep(1.5)

        # Stop any existing capture
        if self.dvgrab:
            self.dvgrab.stop()

        self._prev_clip_str = ""

        if camera_controlled:
            # Camera Controlled ON
            self.dvgrab.start(camera_controlled=True)
            self.ucb.set_led(config.LED_PULSE)
            self.oled.show_waiting()
            self._state = State.CAM_ON_WAITING
        else:
            # Camera Controlled OFF
            self.dvgrab.start(camera_controlled=False)
            self.ucb.set_led(config.LED_OFF)
            self.oled.show_ready()
            self._state = State.CAM_OFF_READY

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self):
        self.startup()

        while self._running:
            tick_start = time.monotonic()

            # 1. Check for mode switch change
            current_switch = self.ucb.read_switch()
            if self._prev_switch is not None and current_switch != self._prev_switch:
                if self._state not in (State.FORMAT_CONFIRM, State.FORMATTING):
                    self._enter_mode(current_switch)
                    self._prev_switch = current_switch
                    self._tick_sleep(tick_start)
                    continue
            self._prev_switch = current_switch

            # 2. Poll button
            btn = self.ucb.poll_button()

            # 3. Dispatch based on state
            handler = {
                State.CAM_ON_WAITING: self._tick_cam_on_waiting,
                State.CAM_ON_RECORDING: self._tick_cam_on_recording,
                State.CAM_OFF_READY: self._tick_cam_off_ready,
                State.CAM_OFF_RECORDING: self._tick_cam_off_recording,
                State.FORMAT_CONFIRM: self._tick_format_confirm,
                State.FORMATTING: self._tick_formatting,
                State.NO_STORAGE: self._tick_no_storage,
            }.get(self._state)

            if handler:
                handler(btn)

            # 4. Make sure dvgrab is still running (restart if crashed)
            if self.dvgrab and not self.dvgrab.running and self._state not in (
                State.FORMAT_CONFIRM, State.FORMATTING, State.NO_STORAGE, State.STARTUP
            ):
                log.warning("dvgrab process died – restarting")
                self._enter_mode(self._camera_controlled)

            self._tick_sleep(tick_start)

        self.shutdown()

    def _tick_sleep(self, tick_start: float):
        elapsed = time.monotonic() - tick_start
        sleep_time = config.POLL_INTERVAL - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    # --- Camera Controlled ON ---
    def _tick_cam_on_waiting(self, btn: dict):
        events = self.dvgrab.poll_output() if self.dvgrab else []
        if "capture_started" in events:
            self.ucb.set_led(config.LED_BLINK)
            self._state = State.CAM_ON_RECORDING
            self.oled.show_recording("00:00:00")
            log.info("Recording started (camera-controlled)")
            return

        # Check for format hold (only when not recording)
        if btn["is_held"] and btn["hold_duration"] >= config.FORMAT_HOLD_TRIGGER:
            self._enter_format_mode()
            return

    def _tick_cam_on_recording(self, btn: dict):
        events = self.dvgrab.poll_output() if self.dvgrab else []
        if "capture_stopped" in events:
            dur = self.dvgrab.get_last_clip_duration()
            self._prev_clip_str = DvgrabManager.format_duration(dur)
            self.ucb.set_led(config.LED_PULSE)
            self.oled.show_waiting(self._prev_clip_str)
            self._state = State.CAM_ON_WAITING
            log.info("Recording stopped (camera-controlled) duration=%s", self._prev_clip_str)
            return

        # Update runtime display
        rt = self.dvgrab.get_recording_runtime()
        self.oled.show_recording(DvgrabManager.format_duration(rt))

    # --- Camera Controlled OFF ---
    def _tick_cam_off_ready(self, btn: dict):
        # Drain dvgrab output
        if self.dvgrab:
            self.dvgrab.poll_output()

        if btn["pressed"]:
            # Start capture
            self.dvgrab.send_capture_start()
            self.dvgrab.is_recording = True
            self.ucb.set_led(config.LED_ON)
            self.oled.show_recording("00:00:00")
            self._state = State.CAM_OFF_RECORDING
            log.info("Recording started (manual)")
            return

        # Check for format hold
        if btn["is_held"] and btn["hold_duration"] >= config.FORMAT_HOLD_TRIGGER:
            self._enter_format_mode()
            return

    def _tick_cam_off_recording(self, btn: dict):
        # Drain dvgrab output
        if self.dvgrab:
            self.dvgrab.poll_output()

        if btn["pressed"]:
            # Stop capture
            self.dvgrab.send_capture_stop()
            dur = self.dvgrab.get_recording_runtime()
            self.dvgrab.is_recording = False
            self._prev_clip_str = DvgrabManager.format_duration(dur)
            self.ucb.set_led(config.LED_OFF)
            self.oled.show_waiting(self._prev_clip_str)
            self._state = State.CAM_OFF_READY
            log.info("Recording stopped (manual) duration=%s", self._prev_clip_str)
            return

        # Update runtime display
        rt = self.dvgrab.get_recording_runtime()
        self.oled.show_recording(DvgrabManager.format_duration(rt))

    # --- Format mode ---
    def _enter_format_mode(self):
        log.info("Entering format confirmation mode")
        self._state = State.FORMAT_CONFIRM
        self._format_hold_start = None
        self.ucb.set_led(config.LED_BLINK)
        self.oled.show_format_prompt()

    def _tick_format_confirm(self, btn: dict):
        if btn["is_held"]:
            if self._format_hold_start is None:
                self._format_hold_start = time.monotonic()
            hold = time.monotonic() - self._format_hold_start
            if hold >= config.FORMAT_CONFIRM_HOLD:
                self._do_format()
                return
        else:
            # Button released or not held
            if btn["released"] and self._format_hold_start is not None:
                # Short press = cancel
                hold = time.monotonic() - self._format_hold_start
                if hold < config.FORMAT_CONFIRM_HOLD:
                    self._cancel_format()
                    return
            if btn["pressed"] and self._format_hold_start is None:
                # First press after entering format mode = cancel
                self._cancel_format()
                return
            self._format_hold_start = None

    def _do_format(self):
        log.info("Formatting external microSD")
        self._state = State.FORMATTING
        self.oled.show_formatting()

        if self.dvgrab:
            self.dvgrab.stop()

        success = format_storage(self.storage_info)

        if success:
            self.oled.show_format_done()
            log.info("Format complete")
        else:
            self.oled.show_error("Format failed")
            log.error("Format failed")

        time.sleep(2)

        # Re-init dvgrab with updated save_dir
        if self.dvgrab:
            self.dvgrab = DvgrabManager(self.storage_info["save_dir"])
        self._enter_mode(self._camera_controlled)

    def _cancel_format(self):
        log.info("Format cancelled")
        self.oled.show_format_cancelled()
        time.sleep(1.5)
        self._enter_mode(self._camera_controlled)

    def _tick_formatting(self, btn: dict):
        # Just wait – format is running synchronously in _do_format
        pass

    def _tick_no_storage(self, btn: dict):
        pass

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def shutdown(self):
        log.info("Shutting down")
        if self.dvgrab:
            self.dvgrab.stop()
        self.ucb.set_led(config.LED_OFF)
        self.oled.clear()
        self.ucb.close()
        try:
            os.remove(config.PID_FILE)
        except OSError:
            pass
        log.info("=== Firewire Controller stopped ===")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    ctrl = FirewireController()
    ctrl.run()


if __name__ == "__main__":
    main()
