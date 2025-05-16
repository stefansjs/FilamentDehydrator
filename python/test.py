from machine import ADC, Pin
from utime import sleep, sleep_ms


LED_PIN = "LED"
TEMP_PIN = 4
led = Pin("LED", Pin.OUT)
relays = [
    Pin(10, Pin.OUT),
    Pin(11, Pin.OUT),
    Pin(12, Pin.OUT),
    Pin(13, Pin.OUT),
]


def main():

    led.off()
    print("Starting up")
    # Flash once for startup
    flash(pause_after=1000)

    # Check temperature pin
    check_thermister()
    # Flash twice for temperature check
    flash(times=2, pause_after=1000)

    # Check relay pin
    check_relays()
    flash(times=3, pause_after=1000)

    # End by flashing the LED indefinitely
    while True:
        flash(duration_ms=250)


def check_thermister():
    temp_pin = ADC(TEMP_PIN)
    print(f"Temperature pin: {temp_pin.read_u16()}")

    if temp_pin.read_u16() in (0, 65535):
        raise ValueError("Temperature pin value is suspicious")
    
    temp_voltage = temp_pin.read_u16() * 3.3 / 65535
    print(f"Temperature voltage: {temp_voltage}V")
    
    temp_celsius = 27 - (temp_voltage - 0.706) / 0.001721
    print(f"Temperature: {temp_celsius}º°C")
    

def check_relays():
    led.off()
    for relay in relays:
        relay.off()

    led.on()
    for relay in relays:
        sleep_ms(100)
        relay.on()
        sleep_ms(500)
        led.off()
        relay.off()
        # sleep_ms(100)



def flash(duration_ms=100, times=1, pause_before=None, pause_after=0):
    """
    Flash the LED a specified number of times.
    
    Args:
        duration_ms (int): The duration in milliseconds for which to flash the LED.
        times (int): The number of times to flash the LED.
    """
    pause_before = 0 if pause_before is None else pause_before
    pause_after = duration_ms if pause_after is None else pause_after

    sleep_ms(pause_before)
    for _ in range(times):
        sleep_ms(duration_ms)
        led.on()
        sleep_ms(duration_ms)
        led.off()
    sleep_ms(pause_after)



if __name__ == '__main__':
    try:
        main()
    
    except Exception as e:
        print(f"An error occurred: {e}")
        led.on()
    
    else:
        print("Done.")
