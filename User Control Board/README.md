# ATtiny85 I2C Control Board

An I2C slave peripheral featuring a button, slide switch, and multi-mode LED, powered by an ATtiny85 microcontroller.

## Register Map

| Address | Name         | Access     | Values                                                                 |
|---------|--------------|------------|------------------------------------------------------------------------|
| `0x00`  | Button       | Read-only  | `0x00` = released, `0x01` = pressed                                    |
| `0x01`  | Slide Switch | Read-only  | `0x00` = off, `0x01` = on                                              |
| `0x02`  | LED Mode     | Read/Write | `0x00` off, `0x01` on, `0x02` pulse, `0x03` blink, `0x04` double pulse |

**I2C Address:** `0x20` (7-bit)

---

## Pin Assignments (ATtiny85 DIP-8)

```
                 ┌───────┐
    (RESET) PB5 ─┤1     8├─ VCC  (3.3V from Pi)
  (SLIDE)   PB3 ─┤2     7├─ PB2  (SCL) ──► to Pi GPIO 3
  (BUTTON)  PB4 ─┤3     6├─ PB1  (LED output)
            GND ─┤4     5├─ PB0  (SDA) ──► to Pi GPIO 2
                 └───────┘
```

| ATtiny Pin | Function      | Connection                         |
|------------|---------------|------------------------------------|
| PB0 (5)    | SDA           | Pi GPIO 2 (SDA1) + 4.7kΩ to VCC   |
| PB2 (7)    | SCL           | Pi GPIO 3 (SCL1) + 4.7kΩ to VCC   |
| PB1 (6)    | LED           | LED anode → 330Ω → PB1             |
| PB3 (2)    | Slide Switch  | Switch between PB3 and GND         |
| PB4 (3)    | Button        | Button between PB4 and GND         |
| VCC (8)    | Power         | Pi 3.3V (pin 1 or 17)              |
| GND (4)    | Ground        | Pi GND (pin 6, 9, 14, 20, 25, etc) |

Internal pull-ups are enabled on PB3 and PB4. Both inputs are **active-low** (pressing/closing pulls to GND).

External **4.7kΩ pull-up resistors** are required on SDA and SCL to VCC (3.3V).

---

## Hardware Setup

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

| Qty | Part                     | Notes                   |
|-----|--------------------------|-------------------------|
| 1   | ATtiny85-20PU (DIP-8)    | Or ATtiny85V for 1.8V+  |
| 1   | LED (any color)          | 3mm or 5mm              |
| 1   | 330Ω resistor            | LED current limiter     |
| 2   | 4.7kΩ resistors          | I2C pull-ups            |
| 1   | Momentary push button    | Normally open           |
| 1   | SPDT slide switch        | Or SPST                 |
| 1   | 100nF ceramic capacitor  | Decoupling on VCC-GND   |
| 1   | 8-pin DIP socket         | Optional but recommended|

---

## Flashing over SPI from Raspberry Pi 5

### Step 1: Install Toolchain

```bash
sudo apt update
sudo apt install -y avr-libc avrdude gcc-avr
```

### Step 2: Enable SPI on the Pi 5

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

### Step 3: Wiring for SPI Programming

Connect the ATtiny85 to the Pi's SPI bus for programming. **This is a separate wiring step from the final I2C bus connection.**

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

Also add a **10kΩ pull-up** from RESET (pin 1) to VCC, and a **100nF cap** across VCC–GND.

> **Important:** During SPI programming, the SPI pins overlap with the I2C/LED pins. Disconnect the LED, I2C pull-ups, and any I2C master before programming. Reconnect them afterward.

### Step 4: Configure avrdude for linuxspi

On the Pi 5, the `linuxspi` programmer uses the kernel SPI driver. Create or edit the avrdude config override if needed:

```bash
# Test connectivity — should read the device signature
sudo avrdude -c linuxspi -p t85 -P /dev/spidev0.0 -b 125000
```

Expected output:
```
avrdude: AVR device initialized and ready to accept instructions
avrdude: Device signature = 0x1e930b (probably t85)
```

If you get errors:
- Double-check wiring, especially RESET to GPIO 25
- Try a slower baud: `-b 62500`
- Ensure SPI is enabled and the kernel module is loaded: `lsmod | grep spi`

### Step 5: Program Fuses (Once Only)

Set the ATtiny85 to run at 8 MHz internal oscillator with no clock prescaler:

```bash
cd firmware/
make fuses
```

This sets:
- **LFUSE = 0xE2**: 8 MHz internal RC, no CKDIV8, 14CK+64ms startup
- **HFUSE = 0xDF**: SPI programming enabled, no watchdog, BOD disabled
- **EFUSE = 0xFF**: Self-programming disabled

> **Warning:** Do NOT set LFUSE to use an external clock unless you have one connected, or you will lock yourself out of SPI programming.

### Step 6: Build and Flash

```bash
cd firmware/
make clean
make
make flash
```

### Step 7: Verify

```bash
make verify
```

### Step 8: Reconnect for I2C Operation

After flashing, **rewire** from SPI programming to I2C operation:

1. Disconnect MOSI, MISO, SCLK, and RESET lines from the Pi's SPI pins
2. Connect PB0 → Pi GPIO 2 (SDA) and PB2 → Pi GPIO 3 (SCL)
3. Add 4.7kΩ pull-ups on SDA and SCL to 3.3V
4. Connect the LED (with resistor), button, and slide switch
5. Power cycle the ATtiny85

### Step 9: Enable I2C and Test

```bash
sudo raspi-config
# Interface Options → I2C → Enable

# Scan the bus
sudo apt install -y i2c-tools
i2cdetect -y 1
# Should show 0x20 in the grid

# Quick read test
i2cget -y 1 0x20 0x00    # Read button
i2cget -y 1 0x20 0x01    # Read slide switch

# Set LED to blink
i2cset -y 1 0x20 0x02 0x03

# Set LED to pulse (breathe)
i2cset -y 1 0x20 0x02 0x02
```

### Step 10: Run the Python Test Script

```bash
pip install smbus2 --break-system-packages
python3 test_board.py
```

---

## I2C Usage from Code

### Python (smbus2)

```python
from smbus2 import SMBus

ADDR = 0x20

with SMBus(1) as bus:
    # Read button state
    button = bus.read_byte_data(ADDR, 0x00)

    # Read slide switch
    switch = bus.read_byte_data(ADDR, 0x01)

    # Set LED to double-pulse
    bus.write_byte_data(ADDR, 0x02, 0x04)
```

### C (Linux i2c-dev)

```c
#include <linux/i2c-dev.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>

int fd = open("/dev/i2c-1", O_RDWR);
ioctl(fd, I2C_SLAVE, 0x20);

// Write: set LED to blink
uint8_t buf[2] = {0x02, 0x03};
write(fd, buf, 2);

// Read button: write register address, then read
uint8_t reg = 0x00;
write(fd, &reg, 1);
uint8_t val;
read(fd, &val, 1);
```

### Command Line (i2c-tools)

```bash
# Read all registers
i2cget -y 1 0x20 0x00   # Button
i2cget -y 1 0x20 0x01   # Slide switch
i2cget -y 1 0x20 0x02   # Current LED mode

# Set LED mode
i2cset -y 1 0x20 0x02 0x00   # OFF
i2cset -y 1 0x20 0x02 0x01   # ON
i2cset -y 1 0x20 0x02 0x02   # Pulse
i2cset -y 1 0x20 0x02 0x03   # Blink
i2cset -y 1 0x20 0x02 0x04   # Double pulse
```

---

## Troubleshooting

**No device found on i2cdetect:**
- Check SDA/SCL wiring and pull-ups
- Verify ATtiny85 is powered (measure VCC)
- Make sure you flashed successfully and set fuses
- Confirm I2C is enabled on the Pi

**Button/switch always reads 0 or 1:**
- Verify active-low wiring (switch connects pin to GND)
- Check that internal pull-ups are working (measure pin voltage with switch open — should be ~3.3V)

**LED doesn't respond:**
- Check LED polarity and series resistor
- Try `i2cset -y 1 0x20 0x02 0x01` and measure PB1 voltage

**SPI programming fails on Pi 5:**
- The Pi 5 uses a different SPI controller (RP1); ensure your kernel and avrdude are up to date
- Try `sudo avrdude -c linuxspi -p t85 -P /dev/spidev0.0 -b 62500` (slower clock)
- Check that GPIO 25 is correctly wired to ATtiny85 RESET with the pull-up resistor

---

## License

MIT — use freely in your projects.
