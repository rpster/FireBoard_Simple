# Architecture

## Module Overview

```
controller.py          Main state machine (791 lines)
    ├── config.py          Global constants (85 lines)
    ├── hardware.py        I2C hardware abstraction (167 lines)
    ├── oled_display.py    OLED display manager (356 lines)
    ├── dvgrab_manager.py  dvgrab process manager (268 lines)
    └── storage.py         Storage detection & formatting (196 lines)
```

## State Machine

The controller is built around an 11-state finite state machine defined in `controller.py`. Each state has a dedicated tick handler dispatched via a lookup table.

### States

| State | Description |
|-------|-------------|
| `STARTUP` | Initial boot, splash screen, FireWire init delay |
| `NO_STORAGE` | No USB microSD detected; polling every 2s |
| `CARD_DETECTED` | microSD just inserted; shows "Card OK!" for 3s before entering recording mode |
| `NO_CAMERA` | FireWire device `/dev/fw1` not found; retries every 5s. Menu and format accessible. |
| `CAM_ON_WAITING` | Camera-controlled mode, waiting for camera to start recording |
| `CAM_ON_RECORDING` | Camera-controlled mode, actively recording |
| `CAM_OFF_READY` | Manual mode, waiting for button press to start recording |
| `CAM_OFF_RECORDING` | Manual mode, actively recording |
| `SAVING` | Syncing captured data to disk via `fsync` |
| `FORMAT_CONFIRM` | Awaiting user confirmation to format microSD |
| `FORMATTING` | Format in progress (runs in background thread) |
| `MENU` | Interactive menu system active |

### State Transitions

```
STARTUP
  ├── [no storage] ──────────────────────── NO_STORAGE
  ├── [no camera]  ──────────────────────── NO_CAMERA
  ├── [switch ON]  ──────────────────────── CAM_ON_WAITING
  └── [switch OFF] ──────────────────────── CAM_OFF_READY

NO_STORAGE
  └── [card inserted] ──────────────────── CARD_DETECTED ── [3s] ── CAM_ON/OFF

NO_CAMERA
  ├── [camera found] ───────────────────── CAM_ON_WAITING / CAM_OFF_READY
  └── [hold 2.5s] ──────────────────────── MENU

CAM_ON_WAITING
  ├── [camera starts recording] ────────── CAM_ON_RECORDING
  └── [hold 2.5s] ──────────────────────── MENU

CAM_ON_RECORDING
  └── [camera stops recording] ─────────── SAVING ── CAM_ON_WAITING

CAM_OFF_READY
  ├── [button press] ───────────────────── CAM_OFF_RECORDING
  └── [hold 2.5s] ──────────────────────── MENU

CAM_OFF_RECORDING
  └── [button press] ───────────────────── SAVING ── CAM_OFF_READY

MENU
  ├── [select Format] ──────────────────── FORMAT_CONFIRM
  ├── [select Exit] ────────────────────── CAM_ON/OFF (re-init dvgrab)
  └── [select Wifi/BT/Brightness] ──────── (toggle, stay in MENU)

FORMAT_CONFIRM
  ├── [hold 5s] ────────────────────────── FORMATTING ── (done) ── CAM_ON/OFF or MENU
  └── [short press] ────────────────────── NO_CAMERA or MENU
```

Any state can transition to `NO_STORAGE` if the microSD is removed, or to `NO_CAMERA` if the FireWire device disappears or dvgrab crashes.

## Module Details

### `config.py`

Central constants file. No logic, only values. All timing, addresses, paths, and display parameters are defined here. See [Configuration](Configuration) for the full reference.

### `hardware.py` - UserControlBoard

I2C driver for the custom ATtiny85-based control board.

**Key design decisions:**
- **Retry with fallback**: Each I2C read/write retries up to 3 times. On persistent failure, returns the last successful value for that register rather than raising an exception.
- **Debouncing**: Both button and switch inputs are software-debounced (80ms for button, 300ms for switch) to filter electrical noise.
- **Button reset**: After mode transitions, the button state is reset to the current physical state to prevent stale holds from triggering actions. The debounced state is set to the current raw reading so only a fresh press/release cycle generates edges.

### `oled_display.py` - OledDisplay

Renders all UI screens on the SSD1306 display using Pillow for drawing and `luma.oled` for device communication.

**Key design decisions:**
- **Graceful degradation**: If the display or luma libraries are not available, all public methods become silent no-ops. The controller runs fully functional in headless mode.
- **Frame caching**: Each frame is compared to the last via `tobytes()`. Identical frames skip the I2C write, reducing bus traffic.
- **Horizontal scrolling**: Long text lines scroll horizontally at 40 pixels/second with a 1-second pause at the start of each cycle.
- **Loading animation**: A 6-frame dot progression (`.` through `......`) updates every 300ms for formatting and startup screens.
- **Multiple font sizes**: DejaVuSansMono in sizes 10-18 for different screen contexts.

### `dvgrab_manager.py` - DvgrabManager

Manages the dvgrab child process that performs the actual FireWire DV capture.

**Key design decisions:**
- **PTY-based communication**: Uses `pty.fork()` to create a pseudo-terminal for bidirectional I/O with dvgrab. This allows both reading dvgrab's output and sending keystrokes in interactive mode.
- **Non-blocking polling**: `select.select()` with zero timeout reads available output without blocking the main loop.
- **Two capture modes**:
  - Camera-controlled: `dvgrab --record-start <prefix>` - dvgrab monitors the camera's record signal
  - Interactive: `dvgrab -i <prefix>` - the controller sends `c` to start and `Escape` to stop capture
- **Output pattern matching**: Monitors dvgrab's stdout for "Capture started", "Capture stopped", and "send oops" (camera disconnect) patterns.
- **Process cleanup**: Sends SIGTERM, waits 500ms, then SIGKILL. Also runs `pkill` to catch any stray dvgrab processes.

### `storage.py`

Handles USB microSD detection, mounting, and formatting.

**Key design decisions:**
- **USB detection via sysfs**: Scans `/sys/block/` entries and checks if the device's sysfs path contains "usb" to identify USB-connected storage. Skips virtual devices (loop, ram, zram) and onboard MMC.
- **Format pipeline**: Wipes the partition table (`wipefs`), creates a DOS partition table with a single exFAT partition (`sfdisk`), re-reads partitions (`partprobe`), formats (`mkfs.exfat`), and remounts.
- **Lazy unmount fallback**: If a normal unmount fails, falls back to `umount -l` (lazy unmount).

### `controller.py` - FirewireController

The main orchestrator that ties everything together.

**Key design decisions:**
- **Dispatch table**: State handlers are stored in a dict (`_dispatch`) built once in `__init__`, avoiding if/elif chains in the main loop.
- **Adaptive polling**: Active states (recording, format confirm, menu) poll at 50ms; idle states poll at 200ms.
- **Input settle time**: After mode transitions, button input is suppressed for 1 second to let I2C settle after dvgrab starts FireWire I/O.
- **Saving optimization**: Uses per-file `fsync` (via `sync <file...>`) instead of `syncfs` (via `sync -f`) to avoid flushing the entire device's dirty pages, which is slow on USB storage.
- **Background format**: The format operation runs in a daemon thread so the loading animation can update on the main thread.
- **WiFi/BT toggle**: Uses `/usr/sbin/rfkill` to soft-block/unblock wireless interfaces by their rfkill ID.
- **Signal handling**: SIGTERM and SIGINT trigger a clean shutdown (stop dvgrab, turn off LED, clear display, remove PID file).

## Main Loop

Each iteration of the main loop (`run()`) performs:

1. **Switch check** - Read slide switch; if changed, transition to the new mode
2. **Button poll** - Read debounced button state (suppressed during settle period)
3. **State dispatch** - Call the current state's tick handler
4. **Storage watchdog** - Every 2s, verify the microSD is still present
5. **Camera watchdog** - Every 1s, verify `/dev/fw1` exists and dvgrab is running
6. **Sleep** - Sleep for the remainder of the poll interval
