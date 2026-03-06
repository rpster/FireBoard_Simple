"""
Firewire Controller - dvgrab Process Manager
Launches dvgrab in the appropriate mode, monitors its output for
capture-start / capture-stop events, and sends keystrokes for interactive control.
"""

import logging
import os
import pty
import select
import signal
import subprocess
import time

import config

log = logging.getLogger(__name__)

# Pre-compute lowered pattern strings (config values are constants)
_CAMERA_DISCONNECTED_LOWER = config.CAMERA_DISCONNECTED_PATTERN.lower()
_CAPTURE_STARTED_LOWER = config.CAPTURE_STARTED_PATTERN.lower()
_CAPTURE_STOPPED_LOWER = config.CAPTURE_STOPPED_PATTERN.lower()


class DvgrabManager:
    """
    Manages a single dvgrab child process.

    In Camera Controlled ON mode  → dvgrab --record-start <prefix>
    In Camera Controlled OFF mode → dvgrab -i <prefix>

    The process is run inside a pseudo-terminal so that we can both read its
    output and send keystrokes (for interactive mode).
    """

    def __init__(self, save_dir: str):
        self._save_dir = save_dir
        self._master_fd: int | None = None
        self._pid: int | None = None
        self._recording = False
        self._record_start_time: float | None = None
        self._last_clip_duration: float = 0.0
        self._output_buffer = ""
        self._camera_disconnected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self, camera_controlled: bool):
        """
        Kill any existing dvgrab, then start a new one.
        camera_controlled=True  → --record-start flag
        camera_controlled=False → -i (interactive) flag
        """
        self.stop()

        prefix = os.path.join(self._save_dir, config.DVGRAB_FILE_PREFIX)

        if camera_controlled:
            args = [config.DVGRAB_BIN, "--record-start", prefix]
        else:
            args = [config.DVGRAB_BIN, "-i", prefix]

        log.info("Starting dvgrab: %s", " ".join(args))

        # Fork with a pty so we can interact
        pid, master_fd = pty.fork()
        if pid == 0:
            # Child – exec dvgrab
            os.execvp(args[0], args)
            # Should never reach here
            os._exit(1)
        else:
            self._pid = pid
            self._master_fd = master_fd
            self._recording = False
            self._record_start_time = None
            self._output_buffer = ""
            self._camera_disconnected = False
            log.info("dvgrab started pid=%d", pid)

    def stop(self):
        """Terminate any running dvgrab process."""
        # Also kill any stray dvgrab processes
        try:
            subprocess.run(["pkill", "-f", config.DVGRAB_BIN],
                           capture_output=True, timeout=5)
        except Exception:
            pass

        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGTERM)
                time.sleep(0.5)
                os.kill(self._pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                os.waitpid(self._pid, os.WNOHANG)
            except ChildProcessError:
                pass
            self._pid = None

        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

        if self._recording:
            self._finalize_clip()
        self._recording = False
        log.info("dvgrab stopped")

    @property
    def running(self) -> bool:
        if self._pid is None:
            return False
        try:
            pid, status = os.waitpid(self._pid, os.WNOHANG)
            if pid != 0:
                # Drain any remaining output so we can see why it died
                self._drain_output()
                if os.WIFEXITED(status):
                    log.warning("dvgrab exited with code %d", os.WEXITSTATUS(status))
                elif os.WIFSIGNALED(status):
                    log.warning("dvgrab killed by signal %d", os.WTERMSIG(status))
                self._pid = None
                return False
        except ChildProcessError:
            self._pid = None
            return False
        return True

    def _drain_output(self):
        """Read and log any remaining output from dvgrab's pty."""
        if self._master_fd is None:
            return
        try:
            while True:
                ready, _, _ = select.select([self._master_fd], [], [], 0)
                if not ready:
                    break
                data = os.read(self._master_fd, 4096).decode("utf-8", errors="replace")
                if not data:
                    break
                for line in data.splitlines():
                    line = line.strip()
                    if line:
                        log.info("dvgrab: %s", line)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------
    def send_key(self, key: str):
        """
        Send a keystroke to dvgrab's pty.
        key='c' for capture toggle, key='\\x1b' for Escape.
        """
        if self._master_fd is None:
            return
        try:
            os.write(self._master_fd, key.encode())
            log.debug("Sent key %r to dvgrab", key)
        except OSError as exc:
            log.warning("Failed to send key to dvgrab: %s", exc)

    def send_capture_start(self):
        """Send 'c' to dvgrab to start capture (interactive mode)."""
        self.send_key("c")

    def send_capture_stop(self):
        """Send Escape to dvgrab to stop capture (interactive mode)."""
        self.send_key("\x1b")

    def poll_output(self) -> list[str]:
        """
        Non-blocking read of dvgrab pty output.
        Returns list of events: 'capture_started', 'capture_stopped', or [].
        """
        events = []
        if self._master_fd is None:
            return events

        try:
            ready, _, _ = select.select([self._master_fd], [], [], 0)
        except (ValueError, OSError):
            return events

        if ready:
            try:
                data = os.read(self._master_fd, 4096).decode("utf-8", errors="replace")
                self._output_buffer += data
                # Safety cap: discard oldest data if buffer grows without newlines
                if len(self._output_buffer) > 8192 and "\n" not in self._output_buffer:
                    self._output_buffer = self._output_buffer[-4096:]
            except OSError:
                return events

        # Process complete lines
        while "\n" in self._output_buffer:
            line, self._output_buffer = self._output_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            log.info("dvgrab: %s", line)

            line_lower = line.lower()
            if _CAMERA_DISCONNECTED_LOWER in line_lower:
                log.warning("Camera disconnected (dvgrab: %s)", line)
                self._camera_disconnected = True
                events.append("camera_disconnected")
            elif _CAPTURE_STARTED_LOWER in line_lower:
                events.append("capture_started")
                self._recording = True
                self._record_start_time = time.monotonic()
            elif _CAPTURE_STOPPED_LOWER in line_lower:
                events.append("capture_stopped")
                self._finalize_clip()
                self._recording = False

        return events

    # ------------------------------------------------------------------
    # Recording state
    # ------------------------------------------------------------------
    @property
    def camera_disconnected(self) -> bool:
        return self._camera_disconnected

    @property
    def is_recording(self) -> bool:
        return self._recording

    @is_recording.setter
    def is_recording(self, value: bool):
        self._recording = value
        if value:
            self._record_start_time = time.monotonic()
        else:
            self._finalize_clip()

    def get_recording_runtime(self) -> float:
        """Seconds since current recording started."""
        if self._record_start_time is None:
            return 0.0
        return time.monotonic() - self._record_start_time

    def get_last_clip_duration(self) -> float:
        """Duration of the most recently completed clip in seconds."""
        return self._last_clip_duration

    def _finalize_clip(self):
        if self._record_start_time is not None:
            self._last_clip_duration = time.monotonic() - self._record_start_time
        self._record_start_time = None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format seconds into HH:MM:SS."""
        s = int(seconds)
        h, remainder = divmod(s, 3600)
        m, sec = divmod(remainder, 60)
        return f"{h:02d}:{m:02d}:{sec:02d}"
