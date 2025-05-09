import asyncio
import os

#micropython imports
from machine import Pin
import utime

# local imports
from blink import Blink
from drybox import hardware
from drybox.hardware import Pico
from external import tomli as toml
from microapp.microapp import MicroApp

DEFAULT_CONFIG_PATH = "/config.toml"

def build(config=None):
    """
    Build the drybox from the configuration.
    
    Args:
        config (dict): The configuration dictionary containing the drybox settings.
    
    Returns:
        DryBox: An instance of the DryBox class.
    """
    config = validate_config(config) if config else read_config(DEFAULT_CONFIG_PATH)
    hardware_config = config['hardware']
    heater = hardware.Heater(hardware_config['heater_pin'])
    hygrometer = hardware.Hygrometer(hardware_config['hygrometer_pin'])
    recirculation_fan = Pin(hardware_config['recirculation_fan_pin'], Pin.OUT)
    exhaust_fan = Pin(hardware_config['exhaust_fan_pin'], Pin.OUT)

    print(f"Built heater={hardware_config['heater_pin']}, hygrometer={hardware_config['hygrometer_pin']}, recirculation_fan={hardware_config['recirculation_fan_pin']}, exhaust_fan={hardware_config['exhaust_fan_pin']}")

    # optional components
    thermister = hardware.Thermister(hardware_config['thermister_pin']) if 'thermister_pin' in config else None
    screen = None

    return DryBox(config, heater, hygrometer, recirculation_fan, exhaust_fan, screen)


class Status:
    UNKNOWN = 0
    ERROR = -1
    STARTING = 1

    # Running states
    RUNNING = 10
    HEATING = 11
    EXHAUSTING = 12
    TARGET_REACHED = 13

STATUS_BY_NAME = {
    "unknown": Status.UNKNOWN,
    "error": Status.ERROR,
    "starting": Status.STARTING,
    "running": Status.RUNNING,
    "heating": Status.HEATING,
    "exhausting": Status.EXHAUSTING,
    "target_reached": Status.TARGET_REACHED
}


class DryBox:
    def __init__(self, config, heater, hygrometer, recirculation_fan, exhaust_fan, screen=None):
        """
        Initialize the DryBox with the specified components.
        
        Args:
            heater (Heater): The heater component.
            thermistor (Thermistor): The thermistor component.
            hygrometer (Hygrometer): The hygrometer component.
            recirculation_fan (Fan): The recirculation fan component.
            exhaust_fan (Fan): The exhaust fan component.
        """
        # State machines are nice
        self.state = Status.STARTING
        asyncio.create_task(self.status_led())

        # IO objects
        self.heater = heater
        self.thermister = Pico.PICO_THERMISTER
        self.hygrometer = hygrometer
        self.recirculation_fan = recirculation_fan
        self.exhaust_fan = exhaust_fan
        self.screen = screen

        # config parameters
        self.config = config
        self.unsafe_temperature = config['unsafe_temperature']
        self.target_humidity = self.config['target_humidity']
        self.target_temperature = self.config['target_temperature']

        # status
        print(self.heater, self.thermister, self.hygrometer, self.recirculation_fan, self.exhaust_fan, self.screen)
        self.state = Status.RUNNING

    def heat(self):
        self.state = Status.HEATING
        self.heater.on()
        self.recirculation_fan.on()

    def stay_hot(self):
        self.state = Status.TARGET_REACHED
        self.heater.off()
        self.recirculation_fan.on()

    def vent(self):
        self.state = Status.EXHAUSTING
        self.heater.off()
        self.recirculation_fan.off()
        self.exhaust_fan.on()

    def idle(self):
        self.state = Status.RUNNING
        self.heater.off()
        self.recirculation_fan.off()
        self.exhaust_fan.off()

    def reset(self):
        """
        Reset the DryBox to its initial state.
        """
        Pico.PICO_LED.off()
        self.heater.off()
        self.recirculation_fan.off()
        self.exhaust_fan.off()
        Pico.PICO_LED.on()

    def run(self):
        self.reset()
        app = MicroApp()
        app.schedule(250, self.print_readings)
        app.add_scheduled(app._repeat_with_interval(2000, self.hygrometer.try_read))
        app.run(100, self.check)


    def check(self, microapp):
        temp, humidity = self.hygrometer.get_humidity(), self.hygrometer.get_temperature()
        if temp and temp > self.unsafe_temperature:
            print(f"Panic! Heater is too hot: {temp}, limit {self.unsafe_temperature}")
            self.panic()
            return True

        if self.thermister.get_temperature() > self.unsafe_temperature:
            print(f"Panic! Thermister is too hot: {self.thermister.get_temperature()}, limit {self.unsafe_temperature}")
            self.panic()
            return True

        # if humidity

    def print_readings(self):
        pico_temp = Pico.PICO_THERMISTER.get_temperature()
        temperature, humidity = self.hygrometer.get_temperature(), self.hygrometer.get_humidity()
        current_time = utime.localtime()
        current_time = "{}:{:02d}:{:02d}:T{:02d}:{:02d}:{:02d}".format(*current_time)
        print(";".join(map(str, [pico_temp, temperature, humidity, current_time])))
        

    def panic(self):
        self.heater.off()
        self.exhaust_fan.on()
        self.recirculation_fan.on()

        if self.screen is not None:
            self.screen.display("OVERHEATED")
            self.screen.display(f"{self.heater.get_temperature()}℃")
            
        os.system("sudo shutdown -h now")
        raise RuntimeError("Panic! Heater is on.")
    
    async def status_led(self):
        while True:
            on_time_ms, off_time_ms = self._get_blink_pattern(self.state)
            Pico.PICO_LED.on()
            await asyncio.sleep_ms(round(on_time_ms))
            if off_time_ms > 0:
                Pico.PICO_LED.off()
                await asyncio.sleep_ms(round(off_time_ms))


    STATUS_LED_PATTERNS ={
        Status.ERROR: Blink.CONSTANT,
        Status.UNKNOWN: Blink.WARNING,
        Status.STARTING: Blink.SLOW_CALM,
        Status.HEATING: Blink.ACTIVE_CALM,
        Status.EXHAUSTING: Blink.ACTIVE,
        Status.RUNNING: Blink.IDLE_CALM,
        Status.TARGET_REACHED: Blink.IDLE_FAST,
    }

    @classmethod
    def _get_blink_pattern(cls, state):
        fallback = cls.STATUS_LED_PATTERNS[Status.UNKNOWN]
        return Blink.blink_time_ms(cls.STATUS_LED_PATTERNS.get(state, fallback))
    
    def _error_callback(self, func, exception):
        self.state = Status.ERROR
        Pico.PICO_LED.on()


def read_config(path=DEFAULT_CONFIG_PATH):
    try:
        with open(path, "rb") as f:
            config_dict = toml.load(f)
    except OSError:
        print("File error with config file: ", path)
        raise
    
    if "drybox" not in config_dict:
        raise ValueError(f"Config file {path} does not contain 'drybox' section.")
    
    drybox_config = config_dict["drybox"]
    validate_config(drybox_config)
    return drybox_config

def validate_config(config):
    if 'drybox' in config:
        config = config['drybox']

    if 'version' not in config:
        raise ValueError("Config file is missing a version. I won't know how to read it.")
    version = config['version'].split('.')
    
    # for now, before we make a 1.0 release, we'll only accept 1.0a
    if version != ['1', '0a']:
        raise ValueError(f"Config file version {config['version']} is not supported. I only support 1.0a.")
    
    required_keys = {
        'hardware': ['heater_pin', 'hygrometer_pin', 'recirculation_fan_pin', 'exhaust_fan_pin'],
        'pid': ['target_humidity', 'dehumidify_temperature']
    }
    
    errors = []
    for key, subkeys in required_keys.items():
        if key not in config:
            errors.append(f"Config file is missing required key: {key}")
            continue
        for subkey in subkeys:
            if subkey not in config[key]:
                errors.append(f"Config file is missing required subkey: {key}.{subkey}")
    
    return config



def main():
    asyncio.new_event_loop()
    drybox = build()
    asyncio.create_task(cycle_hardware(drybox))
    drybox.run()


async def cycle_hardware(drybox):
    print("Starting cycle_hardware")
    
    while True:
        print("heating")
        drybox.heat()
        await asyncio.sleep(2)

        print("Recirculating")
        drybox.stay_hot()
        await asyncio.sleep(10)

        print("Venting")
        drybox.vent()
        await asyncio.sleep(10)

        print("Idling")
        drybox.idle()
        await asyncio.sleep(10)



if __name__ == "__main__":
    main()
