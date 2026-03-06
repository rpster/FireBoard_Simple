/*
 * ATtiny85 I2C Control Board — Final Production Firmware
 * ========================================================
 * I2C Address: 0x20 (7-bit)
 *
 * Register Map:
 *   0x00 - Button     (read-only)   0x00=released, 0x01=pressed
 *   0x01 - Slide SW   (read-only)   0x00=off, 0x01=on
 *   0x02 - LED Mode   (read/write)  0=off, 1=on, 2=pulse, 3=blink, 4=double
 *
 * Pins:
 *   PB0 (pin 5) - SDA    PB2 (pin 7) - SCL
 *   PB1 (pin 6) - LED    PB3 (pin 2) - Button    PB4 (pin 3) - Slide SW
 *
 * Fuses: LFUSE=0xE2  HFUSE=0xDF  EFUSE=0xFF  (8 MHz internal RC)
 */

#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/sleep.h>
#include <util/delay.h>

/* ═══════════════════════ Configuration ════════════════════════ */

#define SLAVE_ADDR        0x20

#define DDR_USI           DDRB
#define PORT_USI          PORTB
#define PIN_USI           PINB
#define PORT_USI_SDA      PB0
#define PORT_USI_SCL      PB2
#define PIN_USI_SDA       PB0
#define PIN_USI_SCL       PB2

#define PIN_LED           PB1
#define PIN_BUTTON        PB4
#define PIN_SLIDE_SW      PB3

#define REG_BUTTON        0
#define REG_SLIDE_SW      1
#define REG_LED_MODE      2
#define REG_COUNT         3

#define LED_OFF           0
#define LED_ON            1
#define LED_PULSE         2
#define LED_BLINK         3
#define LED_DOUBLE_PULSE  4
#define LED_FAST_BLINK    5

#define BLINK_HALF_PERIOD 500
#define FAST_BLINK_HALF   100
#define PULSE_PERIOD      2000
#define DPULSE_ON_TIME    120
#define DPULSE_GAP_TIME   150
#define DPULSE_OFF_TIME   1200
#define DEBOUNCE_MS       20

/* ═══════════════════ USI I2C Slave Driver ════════════════════ */

enum {
    OF_CHECK_ADDRESS,
    OF_SEND_DATA,
    OF_REQUEST_ACK,
    OF_CHECK_ACK,
    OF_RECEIVE_DATA,
    OF_STORE_DATA_AND_SEND_ACK
};

static volatile uint8_t of_state;
static volatile uint8_t reg_ptr     = 0;
static volatile uint8_t reg_ptr_set = 0;
static volatile uint8_t regs[REG_COUNT] = { 0, 0, LED_OFF };

static inline void sda_input(void)  { DDR_USI  &= ~(1 << PORT_USI_SDA); }
static inline void sda_output(void) { DDR_USI  |=  (1 << PORT_USI_SDA); }
static inline void sda_low(void)    { PORT_USI &= ~(1 << PORT_USI_SDA); }
static inline void sda_high(void)   { PORT_USI |=  (1 << PORT_USI_SDA); }
static inline void scl_input(void)  { DDR_USI  &= ~(1 << PORT_USI_SCL); }
static inline void scl_output(void) { DDR_USI  |=  (1 << PORT_USI_SCL); }
static inline void scl_high(void)   { PORT_USI |=  (1 << PORT_USI_SCL); }

static void twi_reset_state(void)
{
    USISR = (1<<USISIF)|(1<<USIOIF)|(0<<USIPF)|(1<<USIDC)|(0x00<<USICNT0);
    USICR = (1<<USISIE)|(0<<USIOIE)|
            (1<<USIWM1)|(0<<USIWM0)|
            (1<<USICS1)|(0<<USICS0)|(0<<USICLK)|(0<<USITC);
}

static void twi_reset(void)
{
    sda_input();  sda_low();
    scl_input();
    PORT_USI &= ~(1 << PORT_USI_SCL);
    sda_output(); sda_high(); sda_input();
    scl_output(); scl_high();
    twi_reset_state();
}

ISR(USI_START_vect)
{
    sda_input();
    while (!(PIN_USI & (1 << PIN_USI_SDA)) &&
            (PIN_USI & (1 << PIN_USI_SCL)))
        ;
    if (PIN_USI & (1 << PIN_USI_SDA)) {
        twi_reset();
        return;
    }
    of_state = OF_CHECK_ADDRESS;
    /* NOTE: Do NOT reset reg_ptr_set here — repeated START
     * must preserve the register pointer set during write phase */
    USIDR = 0xFF;
    USICR = (1<<USISIE)|(1<<USIOIE)|
            (1<<USIWM1)|(1<<USIWM0)|
            (1<<USICS1)|(0<<USICS0)|(0<<USICLK)|(0<<USITC);
    USISR = (1<<USISIF)|(1<<USIOIF)|(0<<USIPF)|(1<<USIDC)|(0x00<<USICNT0);
}

ISR(USI_OVF_vect)
{
    uint8_t data = USIDR;
    uint8_t set_counter = 0x00;

again:
    switch (of_state) {
    case OF_CHECK_ADDRESS: {
        uint8_t addr = (data >> 1);
        uint8_t dir  = data & 0x01;
        if (addr == SLAVE_ADDR) {
            of_state = dir ? OF_SEND_DATA : OF_RECEIVE_DATA;
            USIDR = 0x00;
            set_counter = 0x0E;
            sda_output();
        } else {
            USIDR = 0x00;
            twi_reset_state();
            return;
        }
        break;
    }
    case OF_SEND_DATA:
        of_state = OF_REQUEST_ACK;
        USIDR = (reg_ptr < REG_COUNT) ? regs[reg_ptr++] : 0xFF;
        set_counter = 0x00;
        sda_output();
        break;
    case OF_REQUEST_ACK:
        of_state = OF_CHECK_ACK;
        USIDR = 0x00;
        set_counter = 0x0E;
        sda_input();
        break;
    case OF_CHECK_ACK:
        if (data) { twi_reset(); return; }
        of_state = OF_SEND_DATA;
        goto again;
    case OF_RECEIVE_DATA:
        of_state = OF_STORE_DATA_AND_SEND_ACK;
        set_counter = 0x00;
        sda_input();
        break;
    case OF_STORE_DATA_AND_SEND_ACK:
        of_state = OF_RECEIVE_DATA;
        if (!reg_ptr_set) {
            reg_ptr = data;
            reg_ptr_set = 1;
        } else {
            if (reg_ptr == REG_LED_MODE && data <= LED_FAST_BLINK)
                regs[REG_LED_MODE] = data;
            reg_ptr++;
        }
        USIDR = 0x00;
        set_counter = 0x0E;
        sda_output();
        break;
    }
    USISR = (0<<USISIF)|(1<<USIOIF)|(0<<USIPF)|(1<<USIDC)|(set_counter<<USICNT0);
}

/* ══════════════════ Input Debouncing ═════════════════════════ */

static uint8_t debounce(uint8_t *counter, uint8_t raw)
{
    if (raw) {
        if (*counter < DEBOUNCE_MS) (*counter)++;
    } else {
        if (*counter > 0) (*counter)--;
    }
    return (*counter >= DEBOUNCE_MS) ? 1 : 0;
}

/* ═══════════════════ LED Effect Engine ═══════════════════════ */

static uint8_t breathe_curve(uint16_t t, uint16_t period)
{
    uint16_t half = period / 2;
    uint16_t phase;
    if (t < half)
        phase = (uint32_t)t * 255 / half;
    else
        phase = (uint32_t)(period - t) * 255 / half;
    return (uint16_t)(phase * phase) / 255;
}

/* Timer0 overflow ISR — sole purpose is to wake from SLEEP_MODE_IDLE.
 * Fires every ~2.048 ms at 8 MHz / 64 prescaler. */
ISR(TIMER0_OVF_vect)
{
    /* empty — wake only */
}

/* ═══════════════════════ Main ════════════════════════════════ */

int main(void)
{
    /* 8 MHz */
    CLKPR = (1 << CLKPCE);
    CLKPR = 0x00;

    /* LED via Timer1 PWM on OC1A (PB1) */
    DDRB |= (1 << PIN_LED);
    PORTB &= ~(1 << PIN_LED);
    TCCR1 = (1 << PWM1A) | (1 << COM1A1)
           | (0 << CS13) | (1 << CS12)
           | (0 << CS11) | (1 << CS10);
    GTCCR = 0;
    OCR1C = 255;
    OCR1A = 0;

    /* Timer0: ~2 ms overflow interrupt (wake source for idle sleep).
     * 8 MHz / 64 prescaler = 125 kHz tick, 256 counts ≈ 2.048 ms. */
    TCCR0A = 0;
    TCCR0B = (1 << CS01) | (1 << CS00);   /* clk/64 */
    TIMSK  |= (1 << TOIE0);               /* enable Timer0 overflow interrupt */

    set_sleep_mode(SLEEP_MODE_IDLE);
    sleep_enable();

    /* I2C slave */
    twi_reset();

    /* Button & slide switch: inputs with pull-ups
     * MUST be set AFTER twi_reset() to avoid PORTB being overwritten */
    DDRB  &= ~((1 << PIN_BUTTON) | (1 << PIN_SLIDE_SW));
    PORTB |=  ((1 << PIN_BUTTON) | (1 << PIN_SLIDE_SW));

    sei();

    uint8_t  btn_cnt  = 0;
    uint8_t  sw_cnt   = 0;
    uint16_t led_tick = 0;

    for (;;) {

        /* Poll stop condition — reset register pointer context */
        if (USISR & (1 << USIPF)) {
            USISR |= (1 << USIPF);
            reg_ptr_set = 0;
        }

        /* Re-assert pull-ups (ISRs share PORTB and could clobber these) */
        PORTB |= ((1 << PIN_BUTTON) | (1 << PIN_SLIDE_SW));

        /* Debounce inputs */
        uint8_t btn_raw = !(PINB & (1 << PIN_BUTTON));
        uint8_t sw_raw  = !(PINB & (1 << PIN_SLIDE_SW));
        regs[REG_BUTTON]   = debounce(&btn_cnt, btn_raw);
        regs[REG_SLIDE_SW] = debounce(&sw_cnt,  sw_raw);

        /* LED effect engine */
        uint8_t mode = regs[REG_LED_MODE];
        switch (mode) {

        case LED_OFF:
            OCR1A = 0;
            led_tick = 0;
            break;

        case LED_ON:
            OCR1A = 255;
            led_tick = 0;
            break;

        case LED_PULSE:
            OCR1A = breathe_curve(led_tick, PULSE_PERIOD);
            if (++led_tick >= PULSE_PERIOD) led_tick = 0;
            break;

        case LED_BLINK:
            OCR1A = (led_tick < BLINK_HALF_PERIOD) ? 255 : 0;
            if (++led_tick >= BLINK_HALF_PERIOD * 2) led_tick = 0;
            break;

        case LED_DOUBLE_PULSE: {
            uint16_t p1 = DPULSE_ON_TIME;
            uint16_t p2 = p1 + DPULSE_GAP_TIME;
            uint16_t p3 = p2 + DPULSE_ON_TIME;
            uint16_t total = p3 + DPULSE_OFF_TIME;

            if      (led_tick < p1) OCR1A = 255;
            else if (led_tick < p2) OCR1A = 0;
            else if (led_tick < p3) OCR1A = 255;
            else                    OCR1A = 0;

            if (++led_tick >= total) led_tick = 0;
            break;
        }

        case LED_FAST_BLINK:
            OCR1A = (led_tick < FAST_BLINK_HALF) ? 255 : 0;
            if (++led_tick >= FAST_BLINK_HALF * 2) led_tick = 0;
            break;

        default:
            OCR1A = 0;
            break;
        }

        sleep_cpu();
    }

    return 0;
}
