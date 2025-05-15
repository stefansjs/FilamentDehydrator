import asyncio
from pico.pin import Analog  # Import Pin and ADC from the machine module

# micropython imports
from machine import Pin, PWM
import utime
import dht


class UnsafeTemperature(Exception):
    pass


class Thermister:
    def __init__(self, pin, min_temp: float = 0, max_temp: float = 100, sensor_scaling: float = 1):
        self.pin = Analog(pin, scale=sensor_scaling, offset=min_temp if sensor_scaling > 0 else max_temp)
        self.min_temp = min_temp
        self.max_temp = max_temp
        self.sensor_scaling = sensor_scaling
        

    def get_temperature(self) -> float:
        """
        Returns temperature in Celsius.
        """
        return self.pin.read_float() 
    
    def get_temperature_fahrenheit(self) -> float:
        """
        Returns temperature in Fahrenheit.
        """
        return self.get_temperature() * 9 / 5 + 32


class Heater:
    def __init__(self, pin: int):
        """
        Initialize the heater with a pin and an optional unsafe temperature.

        Args:
            pin (int): The pin number for the heater.
            unsafe_temperature (int, optional): The temperature at which the heater is considered unsafe. Defaults to 65.
        """
        self.pin = Pin(pin, Pin.OUT, pull=Pin.PULL_DOWN)
        self.pin.off()
        self.is_on = False
        self.target_temperature = None
        self.temp_histeresis = 2

    def on(self, force=False):
        """
        Turn on the heater.
        """
        if self.is_on and force is False:
            return
        
        self.pin.on()
        self.is_on = True
        print("Heater is ON")

    def off(self, force=False):
        """
        Turn off the heater.
        """
        if force is False and not self.is_on:
            return
        
        self.pin.off()
        self.is_on = False
        print("Heater is OFF")


class TemperatureController:
    UNSAFE_TEMPERATURE = 70
    UNSAFE_PICO_TEMPERATURE = 85  # From Pico datasheet


    def __init__(self, heater, thermister, hysteresis_c=1, max_temperature: int = UNSAFE_TEMPERATURE):
        self.max_temperature = max_temperature
        
        self.heater = heater
        self.thermister = thermister
        self._target_temperature = None
        self.temp_hysteresis = hysteresis_c
        self.heater.off()
        self.state = "idle"

    def get_temperature(self):
        return self.thermister.get_temperature()

    def set_temperature(self, temp):
        self._target_temperature = temp
        if self.state == "running":
            print(f"Setting temperature to {temp}")

    def off(self):
        self._target_temperature = None

    def run_loop(self):
        TemperatureController.check(self)
        
        temp = self.get_temperature()
        if self._target_temperature is not None and temp is not None:
            if temp < self._target_temperature - self.temp_hysteresis:
                self.heater.on()
            elif temp > self._target_temperature + self.temp_hysteresis:
                self.heater.off()
        
        else:
            self.state = "waiting for temperature"

    async def run(self, check_interval_ms):
        TemperatureController.check(self)
        current_temp = self.get_temperature()
        self.state = "waiting for temperature"
        
        # If the run loop is kicked off before setting a temperature, wait for the set temperature
        while current_temp is None:
            await asyncio.sleep_ms(check_interval_ms)
            current_temp = self.get_temperature()
            TemperatureController.check(self)

        # Run until target temp is set to None
        self.state = "running"        
        print(f"Heating to {self._target_temperature}")
        while True:
            self.run_loop()


    @staticmethod
    def check(*heaters):
        """
        Check if the heater is in a safe state. If the temperature exceeds the unsafe limit, panic.
        """
        temp = Pico.PICO_THERMISTER.get_temperature()
        if temp is not None and temp > TemperatureController.UNSAFE_PICO_TEMPERATURE:
            print("Pico overheating!")
            for heater in heaters:
                heater.off()
            raise UnsafeTemperature(f"Pico exceeded it's safe operating temperature: {temp} > {TemperatureController.UNSAFE_PICO_TEMPERATURE}")

        for heater in heaters:
            temp = heater.get_temperature()
            if temp is not None and temp > heater.max_temperature:
                print("Panic! Unsafe temperature detected.")
                for heater in heaters:
                    heater.off()
        
                raise UnsafeTemperature(f"a heater went beyond its configured max temperature: {heater.pin}, {temp} > {heater.max_temperature}")
        
        return True

            


class Fan:
    """
    PWM fan control with independ notions of duty cycle and on/off
    """
    U16_MAX = 65535

    def __init__(self, pin, freq=10_000, duty_cycle=0.5, kick_start_ms=1000):
        self.pin = pin
        self.pwm = PWM(pin, freq=freq, duty_u16=0)  # Start in an OFF state
        self.is_on = False
        self.kick_start_ms = kick_start_ms

        self._duty_cycle = int(round(duty_cycle * Fan.U16_MAX))
        self._background_task = None

    @property
    def duty_cycle(self):
        return self._duty_cycle / self.U16_MAX
    
    @duty_cycle.setter
    def duty_cycle(self, value):
        """ Sets duty cycle as a percentage from 0 to 1 """
        self._duty_cycle = int(round(value * Fan.U16_MAX))
        if self.is_on:
            self.pwm.duty_u16(self._duty_cycle)

    def on(self):
        print(f"Turning on at {self.duty_cycle*100}%")
        if self._background_task is None or self._background_task.done():
            self._background_task = asyncio.create_task(self.kick_start())
    
    def off(self):
        print("Turning off PWM fan")
        if self._background_task is not None and not self._background_task.done():
            self._background_task.cancel()
        if self._background_task is not None:
            self._background_task = None

        self.pwm.duty_u16(0)
        self.is_on = False

    async def kick_start(self):
        print(f"Kick-starting fan for {self.kick_start_ms}ms")
        self.pwm.duty_u16(Fan.U16_MAX)
        await asyncio.sleep_ms(self.kick_start_ms)
        
        print(f"slowing back down to {self.duty_cycle * 100}")
        self.pwm.duty_u16(self._duty_cycle)
        self.is_on = True


class Hygrometer:
    def __init__(self, pin: int = 28):
        self.pin = dht.DHT11(Pin(pin))
        self.start_time = utime.ticks_ms()
        self.read_time = None

        self.temperature = None
        self.humidity = None

    def measure_async(self):
        asyncio.create_task(self._read())

    async def _read(self):
        self.try_read()  # Just run the read function without returning its result

    def try_read(self):
        """
        Read the DHT11 sensor data.
        """
        current_time = utime.ticks_ms()
        last_time = self.read_time if self.read_time is not None else self.start_time
        if utime.ticks_diff(current_time, last_time) < 1_000:  # 1 second
            return False
        
        # Pico.PICO_LED.on()
        try:
            self.pin.measure()
            self.temperature = self.pin.temperature()
            self.humidity = self.pin.humidity()
        
        except Exception as e:
            print("Failed to read measurements")
            self.temperature = None
            self.humidity = None
            return False
        
        finally:
            self.read_time = current_time
        
        return True
    
    def get_humidity(self):
        return self.humidity
    
    def get_temperature(self):
        return self.temperature
        
    


class Pico:
    """
    A class to hold singletons for the Pico board.

    RPi Pico has a strange algorithm for the thermister.
    The formula is:
    V = 3.3 * ADC / 65535 = 3.3 * float_value
    T = 27 - (V - 0.706) / 0.001721
    I want to convert this to a much more straightforward linear equation.
    So, if 
       T = 27 - (V - 0.706) / 0.001721
         = 27 - V / 0.001721 + 0.706 / 0.001721
         = -V / 0.001721 + 27 + 0.706 / 0.001721
         = -(3.3 * float_value) / 0.001721 + 27 + 0.706 / 0.001721
         = float_value * -3.3 / 0.001721 + 27 + 0.706 / 0.001721
    """

    PICO_SCALE = -3.3 / 0.001721  # = -1917.4898...
    PICO_OFFSET = 27 + 0.706 / 0.001721  # = 437.22661
    PICO_MIN_TEMP = PICO_SCALE + PICO_OFFSET  # 27 - (3.3V - 0.706) / 0.001721 = 27 - 2.594 / 0.001721 = -1480.26
    PICO_MAX_TEMP = PICO_OFFSET  # 27 - (0 - 0.706) / 0.001721 = 27 + 0.706 / 0.001721 = 437.227

    PICO_THERMISTER = Thermister(4, min_temp=PICO_MIN_TEMP, max_temp=PICO_MAX_TEMP, sensor_scaling=PICO_SCALE)
    PICO_LED = Pin("LED", Pin.OUT)




def main():
    from microapp import MicroApp
    from collections import OrderedDict

    hygrometer = Hygrometer()

    start_time = utime.ticks_ms()
    def time_since_start():
        return utime.ticks_diff(utime.ticks_ms(), start_time) / 1000

    data = OrderedDict([
        ('Pico temperature', Pico.PICO_THERMISTER.get_temperature,),
        ('humidity', hygrometer.get_humidity,),
        ('dht tmperature', hygrometer.get_temperature,),
        ('timestamp', time_since_start),
    ])

    def main(app):
        Pico.PICO_LED.toggle()
        values = [str(getter()) for getter in data.values()]
        print("; ".join(values))


    MicroApp.RESET_RUN_LOOP()
    app = MicroApp(verbose=False)
    app.schedule(2000, hygrometer.try_read)
    app.run(400, main)
