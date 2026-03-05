# User Control Board

The User Control Board is a custom I2C slave peripheral built around an ATtiny85 microcontroller. It provides a momentary push button, an SPDT slide switch, and a multi-mode LED to the main controller. The firmware, Makefile, and test script live in the `User Control Board/` directory at the repo root.

**I2C Address:** `0x20` (7-bit)

## Register Map

| Address | Name | Access | Values |
|---------|------|--------|--------|
| `0x00` | Button | Read-only | `0x00` = released, `0x01` = pressed |
| `0x01` | Slide Switch | Read-only | `0x00` = off, `0x01` = on |
| `0x02` | LED Mode | Read/Write | See LED modes table below |

### LED Modes

| Value | Mode | Description |
|-------|------|-------------|
| `0x00` | OFF | LED off |
| `0x01` | ON | LED solid on |
| `0x02` | PULSE | Smooth breathing effect (2 s period) |
| `0x03` | BLINK | 1 Hz square-wave blink |
| `0x04` | DOUBLE PULSE | Two quick flashes then a long pause |
| `0x05` | FAST BLINK | 5 Hz square-wave blink |

See [Hardware Setup](Hardware-Setup) for how the main controller uses each LED mode.

---

## Hardware

### Pin Assignments (ATtiny85 DIP-8)

```
                 ┌───────┐
    (RESET) PB5 ─┤1     8├─ VCC  (3.3V from Pi)
  (SLIDE)   PB3 ─┤2     7├─ PB2  (SCL) ──► to Pi GPIO 3
  (BUTTON)  PB4 ─┤3     6├─ PB1  (LED output)
            GND ─┤4     5├─ PB0  (SDA) ──► to Pi GPIO 2
                 └───────┘
```

| ATtiny Pin | Function | Connection |
|------------|----------|------------|
| PB0 (5) | SDA | Pi GPIO 2 (SDA1) + 4.7kΩ pull-up to VCC |
| PB2 (7) | SCL | Pi GPIO 3 (SCL1) + 4.7kΩ pull-up to VCC |
| PB1 (6) | LED | LED anode → 330Ω → PB1 |
| PB3 (2) | Slide Switch | Switch between PB3 and GND |
| PB4 (3) | Button | Momentary button between PB4 and GND |
| VCC (8) | Power | Pi 3.3V |
| GND (4) | Ground | Pi GND |

Internal pull-ups are enabled on PB3 and PB4. Both inputs are **active-low** (pressing/closing pulls the pin to GND).

### Schematic

```
Pi 5 3.3V ──────┬──────────────────────── ATtiny85 VCC (pin 8)
                 │
                 ├── 4.7kΩ ── SDA bus
                 │
                 └── 4.7kΩ ── SCL bus

Pi GPIO 2 (SDA) ──────────────────────── ATtiny85 PB0 (pin 5)
Pi GPIO 3 (SCL) ──────────────────────── ATtiny85 PB2 (pin 7)
Pi GND ────────────────────────────────── ATtiny85 GND (pin 4)

ATtiny85 PB1 (pin 6) ── 330Ω ── LED(+) ── LED(-) ── GND

ATtiny85 PB3 (pin 2) ── Slide Switch ── GND

ATtiny85 PB4 (pin 3) ── Push Button ── GND
```

### Bill of Materials

| Qty | Part | Notes |
|-----|------|-------|
| 1 | ATtiny85-20PU (DIP-8) | Or ATtiny85V for 1.8V+ operation |
| 1 | LED (any colour) | 3mm or 5mm |
| 1 | 330Ω resistor | LED current limiter |
| 2 | 4.7kΩ resistors | I2C pull-ups on SDA and SCL |
| 1 | Momentary push button | Normally open |
| 1 | SPDT slide switch | Or SPST |
| 1 | 100nF ceramic capacitor | Decoupling, placed close to VCC–GND |
| 1 | 8-pin DIP socket | Optional but recommended |

---

## Building the Board

1. Solder the DIP socket (or the ATtiny85 directly) onto your PCB/perfboard
2. Wire VCC (pin 8) to Pi 3.3V and GND (pin 4) to Pi GND
3. Place the 100nF decoupling capacitor as close to pins 4 and 8 as possible
4. Connect the 4.7kΩ pull-up resistors from SDA (PB0) and SCL (PB2) to VCC
5. Wire the LED with a 330Ω series resistor from PB1 to GND
6. Connect the slide switch between PB3 and GND
7. Connect the momentary button between PB4 and GND
8. Run SDA to Pi GPIO 2 and SCL to Pi GPIO 3

No external pull-ups are needed on the button or slide switch — the firmware enables internal pull-ups on PB3 and PB4.

---

## Firmware Overview

The firmware source is in `User Control Board/firmware/main.c`. It runs on the ATtiny85 at 8 MHz (internal RC oscillator) and implements:

- **USI I2C slave driver** — Bit-level implementation of the I2C slave protocol using the ATtiny85's Universal Serial Interface. Handles address matching, register pointer auto-increment, and read/write transactions.
- **Input debouncing** — 20ms integrating debouncer on both the button and slide switch. Inputs are polled every 1ms in the main loop.
- **LED effect engine** — Timer1 hardware PWM on PB1 (OC1A) drives the LED. Six modes are supported: off, on, pulse (quadratic breathing curve), blink, double pulse, and fast blink.
- **Pull-up re-assertion** — The main loop re-asserts pull-ups on PB3/PB4 every iteration since ISR writes to PORTB can clobber them.

---

## Compiling the Firmware

### Install Toolchain

On the Raspberry Pi 5:

```bash
sudo apt update
sudo apt install -y avr-libc avrdude gcc-avr
```

### Make Targets

From the `User Control Board/firmware/` directory:

| Command | Action |
|---------|--------|
| `make` | Compile `main.c` → `main.hex` and print memory usage |
| `make flash` | Flash `main.hex` to the ATtiny85 via SPI |
| `make fuses` | Program fuses for 8 MHz internal oscillator |
| `make verify` | Verify flash contents match `main.hex` |
| `make clean` | Remove build artifacts |

```bash
cd "User Control Board/firmware"
make clean
make
```

---

## Flashing from Raspberry Pi 5

### Enable SPI

```bash
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable
# Reboot if prompted
```

Verify SPI is active:

```bash
ls /dev/spidev0.*
# Should show: /dev/spidev0.0  /dev/spidev0.1
```

### SPI Wiring

Connect the ATtiny85 to the Pi's SPI bus for programming. **This wiring is separate from the final I2C connections — disconnect the LED, I2C pull-ups, and any I2C master before programming.**

```
Raspberry Pi 5                  ATtiny85
─────────────                   ────────
GPIO 10 (MOSI, pin 19) ──────► PB0 (pin 5)   DI
GPIO  9 (MISO, pin 21) ◄────── PB1 (pin 6)   DO
GPIO 11 (SCLK, pin 23) ──────► PB2 (pin 7)   USCK
GPIO 25       (pin 22) ──────► PB5 (pin 1)   RESET
3.3V          (pin  1) ──────► VCC (pin 8)
GND           (pin  6) ──────► GND (pin 4)
```

Add a **10kΩ pull-up** from RESET (pin 1) to VCC and a **100nF cap** across VCC–GND.

### Test Connectivity

```bash
sudo avrdude -c linuxspi -p t85 -P /dev/spidev0.0:/dev/gpiochip4:25 -B 10kHz
```

Expected output:

```
avrdude: AVR device initialized and ready to accept instructions
avrdude: Device signature = 0x1e930b (probably t85)
```

> **Note:** On Pi 5, the header GPIOs are on `gpiochip4` (RP1 chip). If your kernel has the July 2024+ reorder patch, use `gpiochip0` instead. Run `gpiodetect` to verify.

### Program Fuses (Once Only)

```bash
cd "User Control Board/firmware"
make fuses
```

This sets:

| Fuse | Value | Meaning |
|------|-------|---------|
| LFUSE | `0xE2` | 8 MHz internal RC, no CKDIV8, fast startup |
| HFUSE | `0xDF` | SPI programming enabled, no watchdog, BOD disabled |
| EFUSE | `0xFF` | Self-programming disabled |

> **Warning:** Do NOT set LFUSE to use an external clock unless you have one connected, or you will lock yourself out of SPI programming.

### Flash and Verify

```bash
make flash
make verify
```

---

## I2C Operation

After flashing, **rewire** from SPI programming to I2C operation:

1. Disconnect MOSI, MISO, SCLK, and RESET lines from the Pi's SPI pins
2. Connect PB0 → Pi GPIO 2 (SDA) and PB2 → Pi GPIO 3 (SCL)
3. Add 4.7kΩ pull-ups on SDA and SCL to 3.3V
4. Connect the LED (with resistor), button, and slide switch
5. Power cycle the ATtiny85

### Enable I2C and Test

```bash
sudo raspi-config
# Interface Options → I2C → Enable

# Scan the bus
sudo apt install -y i2c-tools
i2cdetect -y 1
# Should show 0x20 in the grid
```

### Quick Register Test

```bash
# Read inputs
i2cget -y 1 0x20 0x00    # Button (0x00=released, 0x01=pressed)
i2cget -y 1 0x20 0x01    # Slide switch (0x00=off, 0x01=on)

# Set LED modes
i2cset -y 1 0x20 0x02 0x00   # OFF
i2cset -y 1 0x20 0x02 0x01   # ON
i2cset -y 1 0x20 0x02 0x02   # Pulse
i2cset -y 1 0x20 0x02 0x03   # Blink
i2cset -y 1 0x20 0x02 0x04   # Double pulse
i2cset -y 1 0x20 0x02 0x05   # Fast blink
```

### Test Script

An interactive test script is provided at `User Control Board/test_board.py`. It requires `smbus2`:

```bash
pip install smbus2 --break-system-packages
python3 "User Control Board/test_board.py"
```

The script offers an interactive menu to read inputs, set LED modes, run a demo cycle through all modes, and continuously monitor all registers.

---

## Troubleshooting

**No device found on `i2cdetect`:**
- Check SDA/SCL wiring and that 4.7kΩ pull-ups are present
- Verify ATtiny85 is powered (measure VCC pin — should be ~3.3V)
- Confirm the firmware was flashed successfully and fuses were set
- Make sure I2C is enabled on the Pi (`sudo raspi-config`)

**Button/switch always reads the same value:**
- Verify active-low wiring (switch connects pin to GND when closed)
- With the switch open, measure the pin voltage — it should be ~3.3V (internal pull-up)

**LED doesn't respond to mode changes:**
- Check LED polarity and the 330Ω series resistor
- Set mode to ON (`i2cset -y 1 0x20 0x02 0x01`) and measure PB1 voltage
- If PB1 shows ~3.3V but the LED is dark, the LED may be inserted backwards

**SPI programming fails:**
- The Pi 5 uses a different SPI controller (RP1) — ensure your kernel and avrdude are up to date
- Try a slower clock: add `-B 20kHz` or `-B 50kHz` to the avrdude command
- Check that GPIO 25 is correctly wired to ATtiny85 RESET with the 10kΩ pull-up
- Make sure the LED, I2C pull-ups, and I2C master are disconnected during SPI programming (SPI pins overlap with I2C/LED pins)
- Run `gpiodetect` to confirm which gpiochip to use — update `GPIOCHIP` in the Makefile if needed

**I2C communication errors (OSError):**
- The ATtiny85 USI slave needs a ~10ms gap between I2C transactions
- The test script and main controller already include this delay (see [Configuration](Configuration) for `I2C_GAP`)
- If using custom code, add a short sleep between consecutive I2C reads/writes
