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


def _load_font(size: int = 10, bold: bool = False):
    """Try to load a small TTF; fall back to default bitmap font."""
    try:
        name = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)
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
        self._font_regular = None
        self._font_large_regular = None
        self._font_large = None
        self._font_xl = None
        self._font_startup_title = None
        self._font_startup_sub = None
        # Scroll state for long lines
        self._scroll_offset = 0.0
        self._scroll_text = None
        self._scroll_pause_until = 0.0
        self._scroll_last_time = 0.0
        # Loading dots animation state
        self._loading_dots = 0
        self._loading_last_time = 0.0
        self._last_frame_bytes: bytes | None = None
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
            self._font = _load_font(12, bold=True)
            self._font_regular = _load_font(12, bold=False)
            self._font_large_regular = _load_font(16, bold=False)
            self._font_large = _load_font(14)
            self._font_xl = _load_font(18)
            self._font_startup_title = _load_font(16, bold=True)
            self._font_startup_sub = _load_font(10, bold=True)
            self._font_menu = _load_font(14, bold=False)
            self._font_mode = _load_font(17, bold=True)
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
    def _new_canvas(self, inverted: bool = False) -> tuple:
        """Return (Image, ImageDraw) for the display size."""
        img = Image.new("1", (config.OLED_WIDTH, config.OLED_HEIGHT),
                        1 if inverted else 0)
        draw = ImageDraw.Draw(img)
        return img, draw

    def _show(self, img: "Image.Image"):
        if self._device:
            frame_bytes = img.tobytes()
            if frame_bytes == self._last_frame_bytes:
                return
            try:
                self._device.display(img)
                self._last_frame_bytes = frame_bytes
            except Exception:
                log.debug("OLED write failed – will retry next frame")

    def reset_loading_dots(self):
        """Reset loading dots animation state."""
        self._loading_dots = 0
        self._loading_last_time = 0.0

    def reset_scroll(self):
        """Reset horizontal scroll state."""
        self._scroll_offset = 0.0
        self._scroll_text = None
        self._scroll_pause_until = 0.0
        self._scroll_last_time = 0.0

    def _draw_scrolling_line(self, draw, y, text, font, force_scroll=False, fill=1):
        """Draw a line of text that scrolls horizontally if it exceeds display width."""
        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]

        if text_width <= config.OLED_WIDTH and not force_scroll:
            draw.text((0, y), text, fill=fill, font=font)
            return

        gap = 40  # pixel gap between repetitions
        total_scroll = max(text_width, config.OLED_WIDTH) + gap
        now = time.monotonic()

        # Reset scroll when text changes
        if self._scroll_text != text:
            self._scroll_text = text
            self._scroll_offset = 0.0
            self._scroll_pause_until = now + 1.0
            self._scroll_last_time = now

        # Advance scroll if not pausing
        if now >= self._scroll_pause_until:
            elapsed = now - self._scroll_last_time
            self._scroll_last_time = now
            self._scroll_offset += elapsed * 40  # 40 pixels per second
            if self._scroll_offset >= total_scroll:
                self._scroll_offset = 0.0
                self._scroll_pause_until = now + 1.0
        else:
            self._scroll_last_time = now  # Keep current during pause

        offset = int(self._scroll_offset)
        draw.text((-offset, y), text, fill=fill, font=font)
        if offset > 0:
            draw.text((-offset + total_scroll, y), text, fill=fill, font=font)

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
        img, draw = self._new_canvas(inverted=True)
        draw.text((0, 5), mode_name, fill=0, font=self._font_mode)
        self._show(img)

    def show_waiting(self, prev_clip_len: str = "", camera_controlled: bool = True):
        """Waiting for Record screen."""
        if not self._available:
            return
        img, draw = self._new_canvas()
        title = "Press Rec on Cam" if camera_controlled else "Press to Rec"
        draw.text((0, 0), title, fill=1, font=self._font)
        if prev_clip_len:
            draw.text((0, 20), f"Last: {prev_clip_len}", fill=1, font=self._font_regular)
        self._show(img)

    def show_recording(self, runtime_str: str, camera_controlled: bool = False):
        """REC + live runtime."""
        if not self._available:
            return
        img, draw = self._new_canvas()
        # Blink record dot at 500ms interval
        if int(time.monotonic() / 0.5) % 2 == 0:
            draw.ellipse((0, 2, 8, 10), fill=1)
        label = "REC | CAM CTRL" if camera_controlled else "REC | MANUAL"
        draw.text((12, 0), label, fill=1, font=self._font_large)
        draw.text((0, 16), runtime_str, fill=1, font=self._font_large_regular)
        self._show(img)

    def show_ready(self):
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 0), "Press to Rec", fill=1, font=self._font)
        self._show(img)

    def show_format_prompt(self):
        """Format confirmation prompt with alternating instruction line."""
        if not self._available:
            return
        img, draw = self._new_canvas(inverted=True)
        draw.text((0, 0), "FORMAT microSD?", fill=0, font=self._font)
        # Alternate between two messages every 3 seconds
        if int(time.monotonic() / 3) % 2 == 0:
            prefix, suffix = "Hold 5s = ", "FORMAT"
        else:
            prefix, suffix = "Press = ", "CANCEL"
        draw.text((0, 16), prefix, fill=0, font=self._font_regular)
        px = self._font_regular.getbbox(prefix)[2]
        draw.text((px, 16), suffix, fill=0, font=self._font)
        self._show(img)

    def show_format_countdown(self, seconds: int):
        """Format countdown while button is held."""
        if not self._available:
            return
        img, draw = self._new_canvas(inverted=True)
        draw.text((0, 0), f"Formatting in {seconds}s", fill=0, font=self._font)
        draw.text((0, 16), "Release to CANCEL", fill=0, font=self._font)
        self._show(img)

    def show_formatting(self):
        if not self._available:
            return
        now = time.monotonic()
        if now - self._loading_last_time >= 0.3:
            self._loading_last_time = now
            self._loading_dots = (self._loading_dots + 1) % 6
        img, draw = self._new_canvas(inverted=True)
        draw.text((0, 5), "Formatting" + "." * self._loading_dots, fill=0, font=self._font)
        self._show(img)

    def show_format_done(self):
        if not self._available:
            return
        img, draw = self._new_canvas(inverted=True)
        draw.text((0, 5), "Format OK!", fill=0, font=self._font_xl)
        self._show(img)

    def show_format_cancelled(self):
        if not self._available:
            return
        img, draw = self._new_canvas(inverted=True)
        draw.text((0, 5), "Format Stop", fill=0, font=self._font_xl)
        self._show(img)

    def show_saving(self, clip_duration: str = ""):
        """Saving / flushing to disk warning screen."""
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 0), "SAVING...", fill=1, font=self._font)
        if clip_duration:
            draw.text((0, 20), f"Last: {clip_duration}", fill=1, font=self._font_regular)
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
        draw.text((0, 5), "No Card", fill=1, font=self._font_xl)
        self._show(img)

    def show_card_detected(self):
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 5), "Card OK!", fill=1, font=self._font_xl)
        self._show(img)

    def show_no_camera(self):
        if not self._available:
            return
        img, draw = self._new_canvas()
        draw.text((0, 5), "No Camera", fill=1, font=self._font_xl)
        self._show(img)

    # Fixed menu slot positions (2 items visible on 128x32 display)
    _MENU_TEXT_Y = (1, 17)          # text y for slot 0 and slot 1
    _MENU_HIGHLIGHT = ((0, 0, 127, 15),   # highlight rect for slot 0: y 0–15
                       (0, 16, 127, 31))   # highlight rect for slot 1: y 16–31

    def show_menu(self, items: list, selected_idx: int, scroll_offset: int):
        """Draw menu with 2 visible items; highlighted item uses inverted overlay."""
        if not self._available:
            return
        img, draw = self._new_canvas()
        visible = items[scroll_offset:scroll_offset + config.MENU_VISIBLE_COUNT]

        for i, label in enumerate(visible):
            actual_idx = scroll_offset + i
            if actual_idx == selected_idx:
                draw.rectangle(self._MENU_HIGHLIGHT[i], fill=1)
                draw.text((2, self._MENU_TEXT_Y[i]), label, fill=0, font=self._font_menu)
            else:
                draw.text((2, self._MENU_TEXT_Y[i]), label, fill=1, font=self._font_menu)

        self._show(img)

    def show_menu_result(self, text: str):
        """Show a toggle result (e.g. 'Wifi: ON') with inverted display."""
        if not self._available:
            return
        img, draw = self._new_canvas(inverted=True)
        draw.text((2, 8), text, fill=0, font=self._font)
        self._show(img)

    def show_startup(self):
        if not self._available:
            return
        now = time.monotonic()
        if now - self._loading_last_time >= 0.3:
            self._loading_last_time = now
            self._loading_dots = (self._loading_dots + 1) % 6
        img, draw = self._new_canvas()
        draw.text((0, 0), "1394Pi", fill=1, font=self._font_startup_title)
        draw.text((0, 19), "Loading" + "." * self._loading_dots, fill=1, font=self._font_startup_sub)
        self._show(img)
