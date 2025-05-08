from collections import namedtuple


Cycle = namedtuple('Cycle', ['frequency', 'duty_cycle'])

class Blink:
    CONSTANT = Cycle(10, 1)
    SLOW_CALM = Cycle(1.5, 0.625)
    ACTIVE_CALM = Cycle(4, 0.75)
    ACTIVE = Cycle(8, 0.75)

    IDLE_CALM = Cycle(0.3, 0.7)
    IDLE_FAST = Cycle(1, 0.75)

    WARNING = Cycle(0.8, 0.125)

    by_name = {
        "ERROR, CONSTANT": CONSTANT,
        "UNKNOWN, WARNING": WARNING,
        "STARTING, SLOW_CALM": SLOW_CALM,
        "HEATING, ACTIVE_CALM": ACTIVE_CALM,
        "EXHAUSTING, ACTIVE": ACTIVE,
        "RUNNING, IDLE_CALM": IDLE_CALM,
        "TARGET_REACHED, IDLE2": IDLE_FAST,
    }

    @staticmethod
    def blink_time_ms(cycle):
        blink_frequency, blink_duty_cycle = cycle
        cycle_period_ms = 1000 / blink_frequency
        on_time_ms = cycle_period_ms * blink_duty_cycle
        off_time_ms = cycle_period_ms * (1 - blink_duty_cycle)

        return on_time_ms, off_time_ms
    


def main():
    from drybox.hardware import Pico
    import utime
    
    while True:
        for status_name, status in Blink.by_name.items():
            print(f"Status: {status_name}")
            ms_remaining = 5_000
            while ms_remaining > 0:
                on_time_ms, off_time_ms = Blink.blink_time_ms(status)
                ms_remaining -= on_time_ms + off_time_ms

                Pico.PICO_LED.on()
                utime.sleep_ms(round(on_time_ms))
                Pico.PICO_LED.off()
                utime.sleep_ms(round(off_time_ms))

if __name__ == "__main__":
    main()
