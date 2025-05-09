import asyncio
from machine import Pin
from pico.pin import Analog  # Import Pin and ADC from the machine module

# micropython imports
import utime
import dht


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
    UNSAFE_TEMPERATURE = 70
    UNSAFE_PICO_TEMPERATURE = 85  # From Pico datasheet
    

    @staticmethod
    def check(*heaters):
        """
        Check if the heater is in a safe state. If the temperature exceeds the unsafe limit, panic.
        """
        if Pico.PICO_THERMISTER.get_temperature() > Heater.UNSAFE_PICO_TEMPERATURE:
            print("Panic! Unsafe temperature detected.")
            return False
        
        for heater in heaters:
            if heater.get_temperature() > heater.max_temperature:
                print("Panic! Unsafe temperature detected.")
                return False
        
        return True

    def __init__(self, pin: int, max_temperature: int = UNSAFE_TEMPERATURE):
        """
        Initialize the heater with a pin and an optional unsafe temperature.

        Args:
            pin (int): The pin number for the heater.
            unsafe_temperature (int, optional): The temperature at which the heater is considered unsafe. Defaults to 65.
        """
        self.pin = Pin(pin, Pin.OUT, pull=Pin.PULL_DOWN)
        self.max_temperature = max_temperature
        self.is_on = False

    def on(self):
        """
        Turn on the heater.
        """
        self.pin.on()
        self.is_on = True
        print("Heater is ON")

    def off(self):
        """
        Turn off the heater.
        """
        self.pin.off()
        self.is_on = False
        print("Heater is OFF")


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
