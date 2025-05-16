
import asyncio


class SlowCycle:
    """
    A class that provides a very slow on-off cycle, measured as period in seconds rather than frequency in Hz
    """
    ON = "on"
    OFF = "off"
    RUNNING = "running"
    CANCELLED = "cancelled"

    def __init__(self, pin, cycle_percent=0.5, cycle_period_s=10, check_interval_ms=250):
        self.pin = pin
        self.mode = SlowCycle.OFF
        self.cycle_percent = cycle_percent
        self.cycle_period_s = cycle_period_s
        self.check_interval_ms = check_interval_ms

        self.pin.off()
        self._pin_state = SlowCycle.OFF
        self._on_time_ms = 0
        self._off_time_ms = 0
        self._update_on_off_times()
        

    def _update_on_off_times(self):
        self._on_time_ms = round(self.cycle_percent * self.cycle_period_s * 1000)
        self._off_time_ms = round(1000 * self.cycle_period_s) - self._on_time_ms

    def set_period(self, period_s):
        self.cycle_period_s = period_s
        self._update_on_off_times()

    def set_duty_cycle(self, duty_cycle):
        self.cycle_percent = duty_cycle
        self._update_on_off_times()

    def set_mode(self, mode):
        if mode not in [SlowCycle.ON, SlowCycle.OFF, SlowCycle.RUNNING]:
            raise ValueError("Invalid cycle mode")
        self.mode = mode

    def on(self):
        self.set_mode(SlowCycle.ON)
        if self._pin_state != SlowCycle.ON:
            print(f"Turning on pin {self.pin}")

    def off(self):
        self.set_mode(SlowCycle.OFF)
        if self._pin_state != SlowCycle.OFF:
            print(f"Turning off pin {self.pin}")
    
    def cycle(self):
        self.set_mode(SlowCycle.RUNNING)
        print(f"Cycling pin {self.pin}")

    def shut_down(self):
        print(f"turning off cycle pin {self.pin}")
        self.mode = SlowCycle.CANCELLED
        self.pin.off()
        

    async def run(self):
        while self.mode != SlowCycle.CANCELLED:
            if self.mode == SlowCycle.ON:
                self.pin.on()
                self._pin_state = SlowCycle.ON
                await asyncio.sleep_ms(self.check_interval_ms)
            
            elif self.mode == SlowCycle.OFF:
                self.pin.off()
                self._pin_state = SlowCycle.OFF
                await asyncio.sleep_ms(self.check_interval_ms)

            elif self.mode == SlowCycle.RUNNING and self._pin_state == SlowCycle.OFF:
                # turn pin on
                self.pin.on()
                self._pin_state = SlowCycle.ON
                await asyncio.sleep_ms(self._on_time_ms)

            elif self.mode == SlowCycle.RUNNING and self._pin_state == SlowCycle.ON:
                # turn pin off
                self.pin.off()
                self._pin_state = SlowCycle.OFF
                await asyncio.sleep_ms(self._off_time_ms)
                