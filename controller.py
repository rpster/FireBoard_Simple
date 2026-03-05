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
import threading
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
    CARD_DETECTED = "card_detected"
    MENU = "menu"


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
        self._no_camera_time: float | None = None
        self._format_awaiting_release = False
        self._format_from_menu = False
        self._mode_entered_time: float = 0.0
        self._last_storage_check: float = 0.0
        self._last_fw_device_check: float = 0.0
        self._fw_device_present: bool = True

        # Saving state tracking
        self._sync_proc: subprocess.Popen | None = None
        self._saving_clip_str: str = ""
        self._card_detected_time: float = 0.0

        # Menu tracking
        self._menu_index = 0
        self._menu_scroll = 0
        self._menu_awaiting_release = False
        self._menu_items: list[str] = []
        self._wifi_rfkill_id: str | None = None
        self._bt_rfkill_id: str | None = None

        # Signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # State dispatch table (built once, reused every tick)
        self._dispatch = {
            State.CAM_ON_WAITING: self._tick_cam_on_waiting,
            State.CAM_ON_RECORDING: self._tick_cam_on_recording,
            State.CAM_OFF_READY: self._tick_cam_off_ready,
            State.CAM_OFF_RECORDING: self._tick_cam_off_recording,
            State.FORMAT_CONFIRM: self._tick_format_confirm,
            State.FORMATTING: self._tick_formatting,
            State.NO_STORAGE: self._tick_no_storage,
            State.CARD_DETECTED: self._tick_card_detected,
            State.NO_CAMERA: self._tick_no_camera,
            State.SAVING: self._tick_saving,
            State.MENU: self._tick_menu,
        }

    def _handle_signal(self, signum, frame):
        log.info("Received signal %d – shutting down", signum)
        self._running = False

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------
    def startup(self):
        """Run once after boot."""
        log.info("=== Firewire Controller starting ===")

        # Log initial WiFi/BT status
        self._is_wifi_enabled()
        self._is_bt_enabled()

        # Write PID file
        with open(config.PID_FILE, "w") as f:
            f.write(str(os.getpid()))

        # Show splash and wait for FireWire subsystem to initialise
        log.info("Waiting %ds for FireWire subsystem", config.FW_INIT_DELAY)
        self.oled.reset_scroll()
        deadline = time.monotonic() + config.FW_INIT_DELAY
        while self._running and time.monotonic() < deadline:
            self.oled.show_startup()
            time.sleep(config.POLL_INTERVAL)

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

        # If no FireWire device yet, enter NO_CAMERA state in the main loop
        # so the button is polled and format mode can be triggered.
        if not os.path.exists(config.FW_DEVICE_PATH):
            log.info("Waiting for FireWire device %s", config.FW_DEVICE_PATH)
            self.oled.show_no_camera()
            self.ucb.set_led(config.LED_DOUBLE_PULSE)
            self._state = State.NO_CAMERA
            self._no_camera_time = time.monotonic()
            self._camera_controlled = self.ucb.read_switch()
            return

        log.info("FireWire device %s found – waiting %ds for bus to settle",
                 config.FW_DEVICE_PATH, config.FW_BUS_SETTLE_DELAY)
        time.sleep(config.FW_BUS_SETTLE_DELAY)

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
        time.sleep(3)

        # Stop any existing capture
        if self.dvgrab:
            self.dvgrab.stop()

        self._prev_clip_str = ""

        if not self.dvgrab:
            log.warning("No camera available – staying in NO_CAMERA state")
            self.oled.show_no_camera()
            self.ucb.set_led(config.LED_DOUBLE_PULSE)
            self._state = State.NO_CAMERA
            self._no_camera_time = time.monotonic()
            return

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
                if self._state not in (State.FORMAT_CONFIRM, State.FORMATTING, State.MENU):
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
            handler = self._dispatch.get(self._state)

            if handler:
                handler(btn)

            # 4. Periodically check external drive is still present
            now = time.monotonic()
            if (now - self._last_storage_check) >= config.STORAGE_CHECK_INTERVAL:
                self._last_storage_check = now
                if self.storage_info and self._state not in (
                    State.NO_STORAGE, State.FORMAT_CONFIRM, State.FORMATTING,
                    State.STARTUP, State.MENU,
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
            now_fw = time.monotonic()
            if (now_fw - self._last_fw_device_check) >= config.FW_DEVICE_CHECK_INTERVAL:
                self._last_fw_device_check = now_fw
                self._fw_device_present = os.path.exists(config.FW_DEVICE_PATH)
            fw_device_missing = not self._fw_device_present
            if self.dvgrab and (
                not self.dvgrab.running or self.dvgrab.camera_disconnected or fw_device_missing
            ) and self._state not in (
                State.FORMAT_CONFIRM, State.FORMATTING, State.NO_STORAGE,
                State.STARTUP, State.NO_CAMERA, State.SAVING, State.MENU,
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
        sleep_time = self._current_poll_interval() - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    def _current_poll_interval(self) -> float:
        """Return the appropriate poll interval for the current state."""
        if self._state in (
            State.CAM_ON_RECORDING,
            State.CAM_OFF_RECORDING,
            State.FORMAT_CONFIRM,
            State.MENU,
        ):
            return config.POLL_INTERVAL
        return config.POLL_INTERVAL_IDLE

    def _input_settled(self) -> bool:
        """True once enough time has passed after a mode switch for I2C to settle."""
        return (time.monotonic() - self._mode_entered_time) >= config.INPUT_SETTLE_TIME

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    # --- Camera Controlled ON ---
    def _tick_cam_on_waiting(self, btn: dict):
        if btn["is_held"] and btn["hold_duration"] >= config.MENU_HOLD_TRIGGER:
            self._enter_menu()
            return
        events = self.dvgrab.poll_output() if self.dvgrab else []
        if "capture_started" in events:
            self.ucb.set_led(config.LED_ON)
            self._state = State.CAM_ON_RECORDING
            self.oled.show_recording("00:00:00", camera_controlled=True)
            log.info("Recording started (camera-controlled)")
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
        self.oled.show_recording(DvgrabManager.format_duration(rt), camera_controlled=True)

    # --- Camera Controlled OFF ---
    def _tick_cam_off_ready(self, btn: dict):
        if btn["is_held"] and btn["hold_duration"] >= config.MENU_HOLD_TRIGGER:
            self._enter_menu()
            return

        # Drain dvgrab output
        if self.dvgrab:
            self.dvgrab.poll_output()

        if btn["released"] and self._input_settled():
            # Short press (< 5s hold) → start capture
            self.dvgrab.send_capture_start()
            self.dvgrab.is_recording = True
            self.ucb.set_led(config.LED_ON)
            self.oled.show_recording("00:00:00")
            self._state = State.CAM_OFF_RECORDING
            log.info("Recording started (manual)")
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
            # Let I2C and button state settle after saving screen is shown
            time.sleep(config.STOP_REC_SETTLE)
            self.ucb.reset_button()
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
        # sync only the capture files + their parent directory, not the
        # entire filesystem.  sync -f calls syncfs() which flushes every
        # dirty page on the device (metadata, allocation bitmap, etc.)
        # and is very slow on USB storage.  sync <file…> calls fsync()
        # per file, flushing only the relevant data blocks.
        save_dir = self.storage_info["save_dir"] if self.storage_info else None
        targets = []
        if save_dir:
            try:
                targets = [
                    os.path.join(save_dir, f)
                    for f in os.listdir(save_dir)
                    if f.startswith(config.DVGRAB_FILE_PREFIX)
                ]
            except OSError:
                pass
            # Also sync the directory so the new entry is persisted
            targets.append(save_dir)
        if targets:
            self._sync_proc = subprocess.Popen(
                ["sync", "--"] + targets,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
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
                self.oled.show_waiting(self._prev_clip_str, camera_controlled=False)
                self._state = State.CAM_OFF_READY

    # --- Format mode ---
    def _enter_format_mode(self):
        log.info("Entering format confirmation mode")
        self._state = State.FORMAT_CONFIRM
        self._format_awaiting_release = True
        self.ucb.set_led(config.LED_BLINK)
        self.oled.reset_scroll()
        self.oled.show_format_prompt()

    def _tick_format_confirm(self, btn: dict):
        if self._format_awaiting_release:
            # Phase 1: wait for user to release the initial hold
            self.oled.show_format_prompt()  # Update scroll animation
            if btn["released"]:
                self._format_awaiting_release = False
                self.ucb.reset_button()
            return

        # Phase 2: waiting for new input
        if btn["is_held"]:
            if btn["hold_duration"] >= config.FORMAT_CONFIRM_HOLD:
                self._do_format()
                return
            remaining = int(config.FORMAT_CONFIRM_HOLD - btn["hold_duration"]) + 1
            self.oled.show_format_countdown(remaining)
        elif btn["released"]:
            self._cancel_format()
        else:
            self.oled.show_format_prompt()  # Update scroll animation

    def _do_format(self):
        log.info("Formatting external microSD")
        self._state = State.FORMATTING

        if self.dvgrab:
            self.dvgrab.stop()

        result = [None]
        def _run_format():
            result[0] = format_storage(self.storage_info)
        fmt_thread = threading.Thread(target=_run_format, daemon=True)
        self.oled.reset_loading_dots()
        fmt_thread.start()
        while fmt_thread.is_alive():
            self.oled.show_formatting()
            time.sleep(config.POLL_INTERVAL)
        success = result[0]

        if success:
            self.oled.show_format_done()
            log.info("Format complete")
        else:
            self.oled.show_error("Format failed")
            log.error("Format failed")

        time.sleep(4)

        if self._format_from_menu:
            self._return_to_menu()
            return

        # Re-init dvgrab with updated save_dir
        self.dvgrab = DvgrabManager(self.storage_info["save_dir"])
        self._enter_mode(self._camera_controlled)

    def _cancel_format(self):
        log.info("Format cancelled")
        self.oled.show_format_cancelled()
        time.sleep(4)
        if self._format_from_menu:
            self._return_to_menu()
            return
        self.oled.show_no_camera()
        self.ucb.set_led(config.LED_DOUBLE_PULSE)
        self._state = State.NO_CAMERA
        self._no_camera_time = time.monotonic()
        self.ucb.reset_button()

    def _tick_formatting(self, btn: dict):
        # Just wait – format is running synchronously in _do_format
        pass

    # --- Menu system ---
    def _build_menu_items(self) -> list[str]:
        """Build menu item labels with current WiFi/BT status."""
        wifi_state = "ON" if self._is_wifi_enabled() else "OFF"
        bt_state = "ON" if self._is_bt_enabled() else "OFF"
        return [f"Wifi: {wifi_state}", f"BT: {bt_state}", "Format", "Exit"]

    def _rfkill_soft_blocked(self, rfkill_type: str) -> tuple[bool, str] | None:
        """Check rfkill soft-block state for a given type (e.g. 'wlan', 'bluetooth').

        Returns (soft_blocked, id) or None on error.
        Parses the table output of plain ``rfkill`` which looks like::

            ID TYPE      DEVICE      SOFT      HARD
             0 bluetooth hci0     blocked unblocked
             1 wlan      phy0   unblocked unblocked
        """
        try:
            result = subprocess.run(
                ["/usr/sbin/rfkill"], capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[1] == rfkill_type:
                    return (parts[3] != "unblocked", parts[0])
        except Exception as exc:
            log.warning("rfkill query failed for %s: %s", rfkill_type, exc)
        return None

    def _is_wifi_enabled(self) -> bool:
        info = self._rfkill_soft_blocked("wlan")
        if info is not None:
            blocked, rfkill_id = info
            self._wifi_rfkill_id = rfkill_id
            enabled = not blocked
            log.info("WiFi status: %s (rfkill id %s)", "enabled" if enabled else "disabled", rfkill_id)
            return enabled
        log.info("WiFi status: unavailable (rfkill interface not found)")
        return False

    def _is_bt_enabled(self) -> bool:
        info = self._rfkill_soft_blocked("bluetooth")
        if info is not None:
            blocked, rfkill_id = info
            self._bt_rfkill_id = rfkill_id
            enabled = not blocked
            log.info("BT status: %s (rfkill id %s)", "enabled" if enabled else "disabled", rfkill_id)
            return enabled
        log.info("BT status: unavailable (rfkill interface not found)")
        return False

    def _enter_menu(self):
        log.info("Entering menu")
        if self.dvgrab:
            self.dvgrab.stop()
            self.dvgrab = None
        self._state = State.MENU
        self._menu_awaiting_release = True
        self._menu_index = 0
        self._menu_scroll = 0
        self._menu_items = self._build_menu_items()
        self.ucb.set_led(config.LED_BLINK)
        self.oled.show_menu(self._menu_items, self._menu_index, self._menu_scroll)

    def _tick_menu(self, btn: dict):
        if self._menu_awaiting_release:
            self.oled.show_menu(self._menu_items, self._menu_index, self._menu_scroll)
            if btn["released"]:
                self._menu_awaiting_release = False
                self.ucb.reset_button()
            return

        # Select immediately when hold reaches 3s (don't wait for release)
        if btn["is_held"] and btn["hold_duration"] >= config.MENU_SELECT_HOLD:
            self._handle_menu_select()
            if self._state == State.MENU:
                self._menu_awaiting_release = True
            return

        if btn["released"]:
            # Short press → cycle to next item
            self._menu_index += 1
            if self._menu_index >= len(self._menu_items):
                self._menu_index = 0
                self._menu_scroll = 0
            elif self._menu_index >= self._menu_scroll + config.MENU_VISIBLE_COUNT:
                self._menu_scroll = self._menu_index - config.MENU_VISIBLE_COUNT + 1
            # Re-poll WiFi/BT status on each navigation press
            self._menu_items = self._build_menu_items()

        self.oled.show_menu(self._menu_items, self._menu_index, self._menu_scroll)

    def _toggle_rfkill(self, rfkill_type: str, label: str):
        """Toggle an rfkill interface and show the result.

        Reads the current soft-block state and ID directly from rfkill,
        then runs the opposite command:
            soft blocked   → rfkill unblock <id>
            soft unblocked → rfkill block <id>
        """
        info = self._rfkill_soft_blocked(rfkill_type)
        if info is not None:
            is_blocked, rfkill_id = info
            cmd = "unblock" if is_blocked else "block"
            subprocess.run(["/usr/sbin/rfkill", cmd, rfkill_id], capture_output=True, timeout=5)
            new_state = "ON" if is_blocked else "OFF"
            log.info("%s toggled: %s (rfkill %s %s)", label, new_state, cmd, rfkill_id)
            self.oled.show_menu_result(f"{label}: {new_state}")
        else:
            log.warning("%s rfkill interface not found", label)
            self.oled.show_menu_result(f"{label}: N/A")
        time.sleep(config.MENU_RESULT_DISPLAY_TIME)
        self._menu_items = self._build_menu_items()

    def _handle_menu_select(self):
        if self._menu_index == 0:
            self._toggle_rfkill("wlan", "Wifi")
        elif self._menu_index == 1:
            self._toggle_rfkill("bluetooth", "BT")
        elif self._menu_index == 2:
            # Format – reuse existing flow
            if not self.storage_info:
                self.oled.show_menu_result("No Card")
                time.sleep(config.MENU_RESULT_DISPLAY_TIME)
            else:
                self._format_from_menu = True
                self._enter_format_mode()
                return
        elif self._menu_index == 3:
            # Exit menu
            self._exit_menu()
            return
        self.ucb.reset_button()

    def _exit_menu(self):
        log.info("Exiting menu")
        self._camera_controlled = self.ucb.read_switch()
        if self.storage_info:
            self.dvgrab = DvgrabManager(self.storage_info["save_dir"])
        self._enter_mode(self._camera_controlled)

    def _return_to_menu(self):
        """Return to menu after format completes or is cancelled."""
        self._format_from_menu = False
        self._menu_awaiting_release = True
        self._menu_items = self._build_menu_items()
        self._state = State.MENU
        self.ucb.set_led(config.LED_BLINK)
        self.ucb.reset_button()
        self.oled.show_menu(self._menu_items, self._menu_index, self._menu_scroll)

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
        self.oled.show_card_detected()
        self.ucb.set_led(config.LED_ON)
        self._card_detected_time = time.monotonic()
        self._state = State.CARD_DETECTED

    def _tick_card_detected(self, btn: dict):
        if (time.monotonic() - self._card_detected_time) >= config.CARD_CONFIRM_DELAY:
            self._enter_mode(self._camera_controlled)

    def _tick_no_camera(self, btn: dict):
        # Allow menu hold even without a camera
        if btn["is_held"] and btn["hold_duration"] >= config.MENU_HOLD_TRIGGER:
            self._enter_menu()
            return

        elapsed = time.monotonic() - self._no_camera_time
        if elapsed >= config.CAMERA_RETRY_DELAY:
            if not os.path.exists(config.FW_DEVICE_PATH):
                self._no_camera_time = time.monotonic()
                return
            log.info("FireWire device %s found – retrying camera connection",
                     config.FW_DEVICE_PATH)
            # First connection since boot: wait for bus to settle, init dvgrab
            if not self.dvgrab:
                time.sleep(config.FW_BUS_SETTLE_DELAY)
                self.dvgrab = DvgrabManager(self.storage_info["save_dir"])
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
