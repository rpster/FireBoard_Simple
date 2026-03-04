#!/usr/bin/env python3
"""
Firewire Controller - Main State Machine
Orchestrates the user control board, OLED display, dvgrab, and storage.
Runs as a systemd service after boot.
"""

import logging
import os
import signal
import subprocess
import sys
import time

import config
from hardware import UserControlBoard
from oled_display import OledDisplay
from dvgrab_manager import DvgrabManager
from storage import detect_external_sd, mount_storage, format_storage, is_storage_present

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
    NO_CAMERA = "no_camera"
    SAVING = "saving"


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
        self._no_camera_time: float | None = None
        self._mode_entered_time: float = 0.0
        self._last_storage_check: float = 0.0

        # Saving state tracking
        self._sync_proc: subprocess.Popen | None = None
        self._saving_clip_str: str = ""

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
        if not self._running:
            return
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

        # Reset button state so stale holds don't carry across mode switches
        self.ucb.reset_button()
        # Let I2C bus settle after dvgrab starts firewire I/O
        self._mode_entered_time = time.monotonic()

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

            # 2. Poll button (suppress during I2C settle period)
            if not self._input_settled():
                self.ucb.reset_button()
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
                State.NO_CAMERA: self._tick_no_camera,
                State.SAVING: self._tick_saving,
            }.get(self._state)

            if handler:
                handler(btn)

            # 4. Periodically check external drive is still present
            now = time.monotonic()
            if (now - self._last_storage_check) >= config.STORAGE_CHECK_INTERVAL:
                self._last_storage_check = now
                if self.storage_info and self._state not in (
                    State.NO_STORAGE, State.FORMAT_CONFIRM, State.FORMATTING,
                    State.STARTUP,
                ):
                    if not is_storage_present(self.storage_info):
                        log.warning("External drive removed")
                        if self.dvgrab:
                            self.dvgrab.stop()
                        self.storage_info = None
                        self.oled.show_no_card()
                        self.ucb.set_led(config.LED_DOUBLE_PULSE)
                        self._state = State.NO_STORAGE
                        self._tick_sleep(tick_start)
                        continue

            # 5. Make sure dvgrab is still running (no camera → retry)
            fw_device_missing = not os.path.exists(config.FW_DEVICE_PATH)
            if self.dvgrab and (
                not self.dvgrab.running or self.dvgrab.camera_disconnected or fw_device_missing
            ) and self._state not in (
                State.FORMAT_CONFIRM, State.FORMATTING, State.NO_STORAGE,
                State.STARTUP, State.NO_CAMERA, State.SAVING,
            ):
                if fw_device_missing:
                    log.warning("FireWire device %s missing – no camera detected", config.FW_DEVICE_PATH)
                else:
                    log.warning("dvgrab process died – no camera detected")
                self.dvgrab.stop()
                self.oled.show_no_camera()
                self.ucb.set_led(config.LED_DOUBLE_PULSE)
                self._state = State.NO_CAMERA
                self._no_camera_time = time.monotonic()

            self._tick_sleep(tick_start)

        self.shutdown()

    def _tick_sleep(self, tick_start: float):
        elapsed = time.monotonic() - tick_start
        sleep_time = config.POLL_INTERVAL - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    def _input_settled(self) -> bool:
        """True once enough time has passed after a mode switch for I2C to settle."""
        return (time.monotonic() - self._mode_entered_time) >= config.INPUT_SETTLE_TIME

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
        if self._input_settled() and btn["is_held"] and btn["hold_duration"] >= config.FORMAT_HOLD_TRIGGER:
            self._enter_format_mode()
            return

    def _tick_cam_on_recording(self, btn: dict):
        events = self.dvgrab.poll_output() if self.dvgrab else []
        if "capture_stopped" in events:
            dur = self.dvgrab.get_last_clip_duration()
            self._prev_clip_str = DvgrabManager.format_duration(dur)
            log.info("Recording stopped (camera-controlled) duration=%s", self._prev_clip_str)
            self._enter_saving()
            return

        # Update runtime display
        rt = self.dvgrab.get_recording_runtime()
        self.oled.show_recording(DvgrabManager.format_duration(rt))

    # --- Camera Controlled OFF ---
    def _tick_cam_off_ready(self, btn: dict):
        # Drain dvgrab output
        if self.dvgrab:
            self.dvgrab.poll_output()

        if btn["pressed"] and self._input_settled():
            # Start capture
            self.dvgrab.send_capture_start()
            self.dvgrab.is_recording = True
            self.ucb.set_led(config.LED_ON)
            self.oled.show_recording("00:00:00")
            self._state = State.CAM_OFF_RECORDING
            log.info("Recording started (manual)")
            return

        # Check for format hold
        if self._input_settled() and btn["is_held"] and btn["hold_duration"] >= config.FORMAT_HOLD_TRIGGER:
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
            log.info("Recording stopped (manual) duration=%s", self._prev_clip_str)
            self._enter_saving()
            return

        # Update runtime display
        rt = self.dvgrab.get_recording_runtime()
        self.oled.show_recording(DvgrabManager.format_duration(rt))

    # --- Saving (sync flush) ---
    def _enter_saving(self):
        """Enter the SAVING state: flush writes to external drive."""
        log.info("Syncing data to external drive")
        self._saving_clip_str = self._prev_clip_str
        self.ucb.set_led(config.LED_FAST_BLINK)
        self.oled.show_saving(self._saving_clip_str)
        mount = self.storage_info["mount_point"] if self.storage_info else "/"
        self._sync_proc = subprocess.Popen(
            ["sync", "-f", mount],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._state = State.SAVING

    def _tick_saving(self, btn: dict):
        if self._sync_proc and self._sync_proc.poll() is not None:
            log.info("Sync complete")
            self._sync_proc = None
            if self._camera_controlled:
                self.ucb.set_led(config.LED_PULSE)
                self.oled.show_waiting(self._prev_clip_str)
                self._state = State.CAM_ON_WAITING
            else:
                self.ucb.set_led(config.LED_OFF)
                self.oled.show_waiting(self._prev_clip_str)
                self._state = State.CAM_OFF_READY

    # --- Format mode ---
    def _enter_format_mode(self):
        log.info("Entering format confirmation mode")
        self._state = State.FORMAT_CONFIRM
        self._format_hold_start = time.monotonic()
        self.ucb.set_led(config.LED_BLINK)
        self.oled.show_format_prompt()

    def _tick_format_confirm(self, btn: dict):
        if btn["is_held"]:
            # User is still holding – check if confirm duration reached
            hold = time.monotonic() - self._format_hold_start
            if hold >= config.FORMAT_CONFIRM_HOLD:
                self._do_format()
                return
        else:
            # Button released – cancel format
            self._cancel_format()

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
        now = time.monotonic()
        if (now - self._last_storage_check) < config.STORAGE_CHECK_INTERVAL:
            return
        self._last_storage_check = now

        info = detect_external_sd()
        if info is None:
            return

        if not mount_storage(info):
            log.warning("External drive detected but mount failed – will retry")
            return

        log.info("External drive mounted: %s", info["save_dir"])
        self.storage_info = info
        self.dvgrab = DvgrabManager(info["save_dir"])
        self._enter_mode(self._camera_controlled)

    def _tick_no_camera(self, btn: dict):
        # Allow format hold even without a camera
        if self.storage_info and btn["is_held"] and btn["hold_duration"] >= config.FORMAT_HOLD_TRIGGER:
            self._enter_format_mode()
            return

        elapsed = time.monotonic() - self._no_camera_time
        if elapsed >= config.CAMERA_RETRY_DELAY:
            if not os.path.exists(config.FW_DEVICE_PATH):
                # Device still absent – reset timer and keep waiting
                self._no_camera_time = time.monotonic()
                return
            log.info("Retrying camera connection (%s present)", config.FW_DEVICE_PATH)
            self._enter_mode(self._camera_controlled)

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
