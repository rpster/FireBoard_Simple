# ──────────────────────────────────────────────────────────────
# ATtiny85 I2C Control Board — Makefile
# ──────────────────────────────────────────────────────────────
# Usage:
#   make              Build firmware (main.hex)
#   make flash        Flash via SPI using avrdude + linuxspi on Pi 5
#   make fuses        Program fuses for 8 MHz internal oscillator
#   make clean        Remove build artifacts
#   make verify       Verify flash contents
# ──────────────────────────────────────────────────────────────

# ── Toolchain ─────────────────────────────────────────────────
CC        = avr-gcc
OBJCOPY   = avr-objcopy
OBJDUMP   = avr-objdump
SIZE      = avr-size
AVRDUDE   = avrdude

# ── Target MCU ────────────────────────────────────────────────
MCU       = attiny85
F_CPU     = 8000000UL

# ── avrdude programmer settings (Raspberry Pi 5 SPI) ─────────
# linuxspi requires the format: /dev/spidev:/dev/gpiochip:resetpin
# On Pi 5, the header GPIOs are on gpiochip4 (RP1 chip).
# If your kernel has the July 2024+ reorder patch, use gpiochip0 instead.
# Run 'gpiodetect' to verify which chip has the 40-pin header lines.
# The reset pin is GPIO 25 (physical pin 22).
PROGRAMMER = linuxspi
SPIDEV     = /dev/spidev0.0
GPIOCHIP   = /dev/gpiochip4
RESET_PIN  = 25
AVRDUDE_FLAGS = -c $(PROGRAMMER) -p t85 -P $(SPIDEV):$(GPIOCHIP):$(RESET_PIN) -B 10kHz -x disable_no_cs

# ── Fuse values (8 MHz internal osc, no clock div, SPI enabled) ──
# Low:   0xE2  (8 MHz internal, no CKDIV8, fast startup)
# High:  0xDF  (default — SPIEN, no watchdog, EEPROM not preserved)
# Ext:   0xFF  (self-programming disabled)
LFUSE     = 0xE2
HFUSE     = 0xDF
EFUSE     = 0xFF

# ── Source files ──────────────────────────────────────────────
SRC       = main.c
OBJ       = $(SRC:.c=.o)
TARGET    = main

# ── Compiler flags ────────────────────────────────────────────
CFLAGS    = -mmcu=$(MCU) -DF_CPU=$(F_CPU) \
            -Os -Wall -Wextra -std=gnu99 \
            -funsigned-char -funsigned-bitfields \
            -fpack-struct -fshort-enums \
            -ffunction-sections -fdata-sections
LDFLAGS   = -mmcu=$(MCU) -Wl,--gc-sections

# ──────────────────────────────────────────────────────────────
# Targets
# ──────────────────────────────────────────────────────────────

.PHONY: all flash fuses clean verify size

all: $(TARGET).hex size

$(TARGET).elf: $(OBJ)
	$(CC) $(LDFLAGS) -o $@ $^

$(TARGET).hex: $(TARGET).elf
	$(OBJCOPY) -O ihex -R .eeprom $< $@

$(TARGET).lst: $(TARGET).elf
	$(OBJDUMP) -d $< > $@

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

size: $(TARGET).elf
	@echo ""
	@echo "────── Memory Usage ──────"
	$(SIZE) --mcu=$(MCU) --format=avr $(TARGET).elf
	@echo ""

flash: $(TARGET).hex
	sudo $(AVRDUDE) $(AVRDUDE_FLAGS) -U flash:w:$(TARGET).hex:i

verify: $(TARGET).hex
	sudo $(AVRDUDE) $(AVRDUDE_FLAGS) -U flash:v:$(TARGET).hex:i

fuses:
	sudo $(AVRDUDE) $(AVRDUDE_FLAGS) \
		-U lfuse:w:$(LFUSE):m \
		-U hfuse:w:$(HFUSE):m \
		-U efuse:w:$(EFUSE):m

clean:
	rm -f $(OBJ) $(TARGET).elf $(TARGET).hex $(TARGET).lst

