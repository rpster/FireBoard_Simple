# User Guide

## Startup Sequence

When the service starts (on boot or manually), the controller performs the following:

1. **Splash screen** - Displays "1394Pi" with a loading animation for 10 seconds while the FireWire subsystem initializes.
2. **Storage detection** - Scans for a USB-connected microSD card. If none is found, displays "No Card" and waits.
3. **Mount storage** - Mounts the microSD at `/mnt/dvmedia` and creates a `captures/` subdirectory.
4. **Camera check** - Looks for the FireWire device at `/dev/fw1`. If not found, displays "No Camera" and retries every 5 seconds.
5. **Enter recording mode** - Reads the slide switch position and enters the appropriate mode.

## Recording Modes

The slide switch on the control board selects between two recording modes.

### Camera Controlled ON (switch = ON)

The DV camera's record button controls when capture starts and stops.

| State | OLED Display | LED | Description |
|-------|-------------|-----|-------------|
| Waiting | "Press Rec on Cam" | Pulse | dvgrab is running, waiting for camera to trigger recording |
| Recording | "REC \| CAM CTRL" + runtime | On (steady) | Camera is recording, runtime counter updates live |
| Saving | "SAVING..." | Fast blink | Flushing captured data to microSD |

### Camera Controlled OFF (switch = OFF)

The button on the control board controls recording.

| State | OLED Display | LED | Description |
|-------|-------------|-----|-------------|
| Ready | "Press to Rec" | Off | Waiting for button press to start capture |
| Recording | "REC \| MANUAL" + runtime | On (steady) | Recording in progress, runtime counter updates live |
| Saving | "SAVING..." | Fast blink | Flushing captured data to microSD |

After saving completes, the display shows the previous clip's duration (e.g., "Last: 00:05:23").

## Button Interactions

The single button has different behaviors depending on how long it is held:

| Action | Duration | Context | Result |
|--------|----------|---------|--------|
| Short press | < 2.5s | CAM_OFF_READY | Start recording |
| Short press | < 2.5s | CAM_OFF_RECORDING | Stop recording |
| Hold | 2.5 seconds | Waiting/Ready/No Camera | Open menu |

## Menu System

Hold the button for 2.5 seconds from a waiting, ready, or no-camera state to open the menu.

### Navigation

- **Short press** - Cycle to the next menu item
- **Hold 2 seconds** - Select the highlighted item

The OLED displays 2 menu items at a time. The currently selected item is highlighted (inverted). Items scroll as you navigate past the visible window.

### Menu Items

| Item | Action |
|------|--------|
| **Brightness** | Opens a sub-menu with High, Medium, Low options |
| **Wifi: ON/OFF** | Toggles WiFi via rfkill. Shows current state. |
| **BT: ON/OFF** | Toggles Bluetooth via rfkill. Shows current state. |
| **Format** | Enters the format confirmation flow (see below) |
| **Exit** | Returns to the recording mode |

### Brightness Sub-Menu

| Option | Contrast Value |
|--------|---------------|
| High | 255 |
| Medium | 80 |
| Low | 1 |

Select an option or choose "Back" to return to the main menu.

## Formatting the microSD

The format feature is accessible from the menu ("Format" item) or by holding the button while in the "No Camera" state.

### Format Flow

1. **Prompt** - The OLED displays "FORMAT microSD?" with alternating instructions:
   - "Hold 5s = FORMAT"
   - "Press = CANCEL"
2. **Confirm** - Hold the button for 5 seconds. A countdown is shown ("Formatting in 3s"). Release at any time to cancel.
3. **Formatting** - The display shows "Formatting..." with an animated dot progression. The process:
   - Unmounts the microSD
   - Wipes the partition table
   - Creates a DOS partition table with a single exFAT partition
   - Formats as exFAT with the label "DVMEDIA"
   - Remounts and recreates the `captures/` directory
4. **Result** - Shows "Format OK!" on success or "Format failed" on error.

## Storage Hot-Swap

The controller monitors the external microSD every 2 seconds.

- **Card removed** - If the microSD is removed during operation, any active recording is stopped. The display shows "No Card" and the LED double-pulses until a card is reinserted.
- **Card inserted** - When a new card is detected, it is automatically mounted. The display briefly shows "Card OK!" before returning to the recording mode.

## Camera Reconnection

The controller checks for the FireWire device (`/dev/fw1`) every second.

- If the camera disconnects or dvgrab crashes, the display shows "No Camera" and the controller retries every 5 seconds.
- When the camera is reconnected, the controller waits 3 seconds for the FireWire bus to settle, then re-enters the current recording mode.

## Mode Switching

Flipping the slide switch during operation immediately transitions to the new mode. A mode banner (e.g., "Cam Ctrl ON") is displayed for 3 seconds before entering the waiting/ready state. The switch is ignored during format confirmation, formatting, and menu interactions.
