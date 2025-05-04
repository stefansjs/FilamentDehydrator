from machine import ADC, Pin
from utime import sleep, sleep_ms


LED_PIN = "LED"
TEMP_PIN = "TEMP"
pin = Pin("LED", Pin.OUT)


def main():

    pin.off()
    print("Starting up")
    # Flash once for startup
    flash(pause_after=1000)

    # Check temperature pin
    temp_pin = ADC(Pin(TEMP_PIN, Pin.IN))
    print(f"Temperature pin: {temp_pin.read_u16()}")
    # Flash twice for temperature check
    flash(times=2, pause_after=1000)

    # End by turning on the LED permanently
    pin.on()


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
        pin.on()
        sleep_ms(duration_ms)
        pin.off()
    sleep_ms(pause_after)



if __name__ == '__main__':
    try:
        main()
    
    except Exception as e:
        print(f"An error occurred: {e}")
        while True:
            flash(duration_ms=250)
    
    else:
        print("Done.")
