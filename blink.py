import utime
from drybox.drybox import STATUS_BY_NAME, DryBox
from drybox.hardware import Pico

def main():
    while True:
        for status_name, status in STATUS_BY_NAME.items():
            print(f"Status: {status_name}")
            ms_remaining = 10_000
            while ms_remaining > 0:
                on_time_ms, off_time_ms = DryBox._get_blink_pattern(status)
                ms_remaining -= on_time_ms + off_time_ms

                Pico.PICO_LED.on()
                utime.sleep_ms(round(on_time_ms))
                Pico.PICO_LED.off()
                utime.sleep_ms(round(off_time_ms))

if __name__ == "__main__":
    main()
