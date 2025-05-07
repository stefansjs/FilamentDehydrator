import asyncio
import os

#micropython imports
from machine import Pin

# local imports
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
        app.schedule(2000, self.hygrometer.try_read)
        app.schedule(100, self.check)
        app.run()


    def check(self):
        temp, humidity = self.hygrometer.get_humidity(), self.hygrometer.get_temperature()
        if temp and temp > self.unsafe_temperature:
            print(f"Panic! Heater is too hot: {temp}, limit {self.unsafe_temperature}")
            self.panic()

        if self.thermister.get_temperature() > self.unsafe_temperature:
            print(f"Panic! Thermister is too hot: {self.thermister.get_temperature()}, limit {self.unsafe_temperature}")
            self.panic()

        # if humidity

    def panic(self):
        self.heater.off()
        self.exhaust_fan.on()
        self.recirculation_fan.on()

        if self.heater.get_state() == "on":
            print("Panic! Heater is on.")
            os.system("sudo shutdown -h now")
            raise RuntimeError("Panic! Heater is on.")
        
        if self.screen is not None:
            self.screen.display("OVERHEATING")
            self.screen.display(f"{self.heater.get_temperature()}℃")
            
    async def status_led(self):
        while True:
            on_time_ms, off_time_ms = self._get_blink_pattern(self.state)
            Pico.PICO_LED.on()
            await asyncio.sleep_ms(round(on_time_ms))
            if off_time_ms > 0:
                Pico.PICO_LED.off()
                await asyncio.sleep_ms(round(off_time_ms))

    @staticmethod
    def _get_blink_pattern(state):
        
        status_blink ={
            Status.ERROR: (10, 1),
            Status.UNKNOWN: (0.8, 0.125),
            Status.STARTING: (1.5, 0.625),
            Status.HEATING: (4, 0.75),
            Status.EXHAUSTING: (8, 0.75),
            Status.RUNNING: (0.3, 0.7),
            Status.TARGET_REACHED: (1, 0.75),
        }
        
        blink_frequency, blink_duty_cycle = status_blink.get(state, status_blink[Status.UNKNOWN])
        cycle_period_ms = 1000 / blink_frequency
        on_time_ms = cycle_period_ms * blink_duty_cycle
        off_time_ms = cycle_period_ms * (1 - blink_duty_cycle)

        return on_time_ms, off_time_ms   
    
    def _error_callback(self, func, exception):
        self.state = Status.ERROR
        Pico.PICO_LED.on()


def read_config(path=DEFAULT_CONFIG_PATH):
    try:
        with open(path, "rb") as f:
            config_dict = toml.load(path)
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
    drybox = build()
    drybox.reset()
    drybox.run()


if __name__ == "__main__":
    main()
