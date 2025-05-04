from machine import Pin
from pico.pin import Analog  # Import Pin and ADC from the machine module


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
        self.pin = Pin(pin, Pin.OUT)
        self.max_temperature = max_temperature
        self.is_on = False

    def on(self):
        """
        Turn on the heater.
        """
        self.pin.on()
        self.is_on = True
        print("Heater is ON")


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

    PICO_THERMISTER = Thermister(4, min_temp=PICO_OFFSET, max_temp=PICO_MAX_TEMP, sensor_scaling=PICO_SCALE)


if __name__ == "__main__":
    from collections import OrderedDict
    from utime import sleep_ms

    sensors = OrderedDict([
        ('Pico temperature', Pico.PICO_THERMISTER.get_temperature,),
    ])

    print("; ".join(sensors.keys()))

    while True:
        try:
            values = [str(getter()) for getter in sensors.values()]
            print("; ".join(values))
            sleep_ms(500)
        except KeyboardInterrupt:
            break
