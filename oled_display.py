"""
Firewire Controller - OLED Display Manager
Auto-detects SSD1306 128x32 I2C OLED and provides a simple drawing API.
Falls back to headless (no-op) mode if display is absent.
"""

import logging
import time

import config

log = logging.getLogger(__name__)

try:
    from luma.core.interface.serial import i2c as luma_i2c
    from luma.oled.device import ssd1306
    from PIL import Image, ImageDraw, ImageFont
    LUMA_AVAILABLE = True
except ImportError:
    LUMA_AVAILABLE = False
    log.warning("luma.oled not installed – OLED support disabled")


def _load_font(size: int = 10):
    """Try to load a small TTF; fall back to default bitmap font."""
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", size)
    except (OSError, IOError):
        return ImageFont.load_default()


class OledDisplay:
    """
    Manages the optional 128×32 SSD1306 OLED.
    If the display is not found, every public method becomes a silent no-op.
    """

    def __init__(self):
        self._device = None
        self._available = False
        self._font = None
        self._font_large = None
        self._detect()

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------
    def _detect(self):
        if not LUMA_AVAILABLE:
            log.info("OLED libraries not available – headless mode")
            return

        try:
            serial = luma_i2c(port=config.I2C_BUS, address=config.OLED_I2C_ADDR)
            self._device = ssd1306(serial, width=config.OLED_WIDTH,
                                   height=config.OLED_HEIGHT)
            self._device.contrast(200)
            self._available = True
            self._font = _load_font(10)
            self._font_large = _load_font(16)
            log.info("OLED display detected at 0x%02X", config.OLED_I2C_ADDR)
        except Exception as exc:
            log.info("No OLED display found (0x%02X): %s – headless mode",
                     config.OLED_I2C_ADDR, exc)

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------
    def _new_canvas(self) -> tuple:
        """Return (Image, ImageDraw) for the display size."""
        img = Image.new("1", (config.OLED_WIDTH, config.OLED_HEIGHT), 0)
        draw = ImageDraw.Draw(img)
        return img, draw

    def _show(self, img: "Image.Image"):
        if self._device:
            self._device.display(img)

    # ------------------------------------------------------------------
    # Public high-level screens
    # ------------------------------------------------------------------
    def clear(self):
        if not self._available:
            return
        img, _ = self._new_canvas()
        self._show(img)

    def show_text(self, line1: str, line2: str = "", line3: str = ""):
        """Show up to 3 lines of small text."""
        if not self._available:
            return
        img, draw = self._new_canvas()
        y = 0
        for line in (line1, line2, line3):
            if line:
                draw.text((0, y), line, fill=1, font=self._font)
            y += 11
        self._show(img)

    def show_mode(self, mode_name: str):
        """Display the current mode prominently."""
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 0), "Mode:", fill=1, font=self._font)
        draw.text((0, 14), mode_name, fill=1, font=self._font_large)
        self._show(img)

    def show_waiting(self, prev_clip_len: str = ""):
        """Waiting for Record screen."""
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 0), "Waiting for Record", fill=1, font=self._font)
        if prev_clip_len:
            draw.text((0, 12), f"Last clip: {prev_clip_len}", fill=1, font=self._font)
        self._show(img)

    def show_recording(self, runtime_str: str):
        """REC + live runtime."""
        if not self._available:
            return
        img, draw = self._new_canvas()
        # Large "REC" with dot
        draw.ellipse((0, 2, 8, 10), fill=1)
        draw.text((12, 0), "REC", fill=1, font=self._font_large)
        draw.text((0, 20), runtime_str, fill=1, font=self._font)
        self._show(img)

    def show_ready(self):
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 8), "Ready", fill=1, font=self._font_large)
        self._show(img)

    def show_format_prompt(self):
        """Format confirmation prompt."""
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 0), "FORMAT microSD?", fill=1, font=self._font)
        draw.text((0, 12), "Hold 5s = YES", fill=1, font=self._font)
        draw.text((0, 23), "Press   = CANCEL", fill=1, font=self._font)
        self._show(img)

    def show_formatting(self):
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 8), "Formatting...", fill=1, font=self._font_large)
        self._show(img)

    def show_format_done(self):
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 0), "Format complete!", fill=1, font=self._font_large)
        self._show(img)

    def show_format_cancelled(self):
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 8), "Format cancelled", fill=1, font=self._font)
        self._show(img)

    def show_error(self, msg: str):
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 0), "ERROR", fill=1, font=self._font_large)
        draw.text((0, 18), msg[:21], fill=1, font=self._font)
        self._show(img)

    def show_no_card(self):
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 8), "No Card", fill=1, font=self._font_large)
        self._show(img)

    def show_startup(self):
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 4), "FW Controller", fill=1, font=self._font_large)
        draw.text((0, 22), "Starting...", fill=1, font=self._font)
        self._show(img)
