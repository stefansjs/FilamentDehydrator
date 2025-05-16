from array import array
import asyncio
import os

#micropython imports
from machine import Pin
from pico.cycle import SlowCycle
import utime

# installed packages
import tomli as toml

# local imports
from blink import Blink
from drybox import hardware
from drybox.hardware import Pico
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

    # higher-level controls
    control_config = config['controls']
    heater = hardware.TemperatureController(
        heater,
        hygrometer, 
        hysteresis_c=control_config.get('heater_hysteresis', 2)
    )
    recirculation_fan = SlowCycle(
        recirculation_fan, 
        cycle_percent=control_config.get('recirculation_cycle_percent', 0.1),
        cycle_period_s=control_config.get('recirculation_cycle_period_s', 180)
    )

    print(f"Built heater={hardware_config['heater_pin']}, hygrometer={hardware_config['hygrometer_pin']}, recirculation_fan={hardware_config['recirculation_fan_pin']}, exhaust_fan={hardware_config['exhaust_fan_pin']}")

    # optional components
    screen = None

    drybox = DryBox(config, heater, hygrometer, recirculation_fan, exhaust_fan, screen)
    dehydrator = Dehydrator(drybox, config)
    return dehydrator


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
        self.unsafe_temperature = config['unsafe_temperature']
        self.target_humidity = config['target_humidity']
        self.target_temperature = config['target_temperature']

        # status
        print(self.heater, self.thermister, self.hygrometer, self.recirculation_fan, self.exhaust_fan, self.screen)
        self.state = Status.RUNNING

    def heat(self, target_temp=None):
        self.state = Status.HEATING
        self.heater.set_temperature(target_temp or self.target_temperature)
        self.recirculation_fan.on()
        self.exhaust_fan.off()
        print(f"Heating to {self.target_temperature}")

    def stay_hot(self):
        self.state = Status.TARGET_REACHED
        self.heater.set_temperature(self.target_temperature)
        self.recirculation_fan.cycle()
        print(f"Holding temperature at {self.target_temperature}")

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
        print("Reset drybox")

    def turn_off_everything(self):
        print("Shutting off everything")
        Pico.PICO_LED.off()
        self.heater.off()
        self.recirculation_fan.shut_down()
        self.exhaust_fan.off()

    def run(self, refresh_rate=3):
        self.reset()
        refresh_period_ms = round(1000 / refresh_rate)

        app = self.build_microapp(refresh_period_ms)
        app.run(100, self.check)


    def build_microapp(self, refresh_period_ms):
        app = MicroApp(error_handler=self.error_handler, cancel_callback=self.turn_off_everything)

        app.add_scheduled(app._repeat_with_interval(1500, self.hygrometer.try_read))
        app.add_scheduled(self.recirculation_fan.run())
        app.schedule(refresh_period_ms, self.print_readings)
        app.schedule(refresh_period_ms, self.heater.run_loop)
        
        return app


    def check(self, _=None):
        temp, __ = self.latest_readings()
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
        temperature, humidity = self.latest_readings()
        current_time = utime.localtime()
        current_time = "{}:{:02d}:{:02d}:T{:02d}:{:02d}:{:02d}".format(*current_time)
        print(";".join(map(str, [pico_temp, temperature, humidity, current_time])))

    def latest_readings(self):
        return self.hygrometer.get_temperature(), self.hygrometer.get_humidity()
    
    def panic(self):
        self.heater.off()
        self.exhaust_fan.on()
        self.recirculation_fan.on()

        if self.screen is not None:
            self.screen.display("OVERHEATED")
            self.screen.display(f"{self.heater.get_temperature()}℃")
            
        os.system("sudo shutdown -h now")
        raise RuntimeError("Panic! Heater is on.")
    
    def error_handler(self, func, error):
        if isinstance(error, KeyboardInterrupt):
            self.reset()
            return False
        return False
    
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



class Dehydrator:
    def __init__(self, drybox, config=None):
        self.drybox = drybox        
        config = config or {}

        control_config = config['controls']
        self.timeout_s = control_config['timeout_s']
        self.sample_rate = control_config['sample_rate']
        self.exhaust_duration_s = control_config['exhaust_duration_s']
        self.initial_wait_for_sensor = control_config.get('sensor_initial_wait_ms', 1000)
        self.sensor_settle_duration_s = control_config.get('sensor_settle_duration_s', 10)
        self.total_measurement_duration_s = control_config.get('total_measurement_duration_s', 90)
        self.measurement_interval_s = control_config.get('measurement_interval_s', 10)
        self.slope_threshold = control_config.get('slope_threshold', 0.5)
        
        self._sample_period_ms = round(1000 / self.sample_rate)
        self._num_measurements = round(self.total_measurement_duration_s / self.measurement_interval_s)

    @property
    def temp(self):
        return self.drybox.hygrometer.get_temperature()
    
    @property
    def humidity(self):
        return self.drybox.hygrometer.get_humidity()
    

    def run(self):
        app = self.drybox.build_microapp(self._sample_period_ms)
        app.add_scheduled(self.dry_filament())
        app.run(100, self.drybox.check)
        
    
    
    async def dry_filament(self):
        """
        This is the main entrypoint for running the entire filament drying sequence.
        """

        # For now let's do one preheat cycle and recirculate down to low levels
        temp = self.temp
        if temp is None:
            await asyncio.sleep_ms(self.initial_wait_for_sensor)
            temp = self.temp

        if temp is None:
            raise ValueError("Cannot read temperature")

        print("Preheating")
        did_preheat = await self.preheat(timeout_s=self.timeout_s)

        if not did_preheat:
            print("Timed out before preheat finished. That's probably bad")
            return

        
        # Let the values settle a little bit
        print(f"Wait for measurements to settle {self.sensor_settle_duration_s} s")
        self.drybox.stay_hot()
        await asyncio.sleep(self.sensor_settle_duration_s)

        # We should do at least one moisture absorption cycle before checking if we've reached our target
        humidity = await self.absorb_moisture(timeout_s=self.timeout_s)

        while True:
            print(f"Reading humidity {humidity}% RH")

            if humidity > self.drybox.target_humidity:
                # If humidity is high, first try pulling in new air before heating/absorbing moisture
                print(f"Venting at {humidity}% RH. Target is {self.drybox.target_humidity}")
                self.drybox.vent()
                await asyncio.sleep(self.exhaust_duration_s)
                self.drybox.idle()
                await asyncio.sleep(self.sensor_settle_duration_s)

                print("Humidity is high. Attempting to absorb some moisture")
                humidity = await self.absorb_moisture()

            else:
                print(f"Looks like we reached our target humidity. Sleeping for {self.total_measurement_duration_s}s")
                self.drybox.idle()
                await asyncio.sleep(self.total_measurement_duration_s)
                
                # run fan for a few seconds before reading the next
                self.drybox.recirculate()
                await asyncio.sleep(self.sensor_settle_duration_s)
                self.drybox.idle()
                humidity = self.humidity

        
    async def preheat(self, target_temp=None, pid_config=None, timeout_s=None):
        target_temp = target_temp or self.drybox.target_temperature

        start_temp = self.temp
        if start_temp <= 0 or start_temp >= 100:
            raise ValueError(f"temperature seems invalid: {start_temp}")
        
        timeout_ms = int(round(timeout_s or self.timeout_s))
        
        hysteresis = self.drybox.heater.temp_hysteresis
        settled_delay_s = self.sensor_settle_duration_s
        settled_delay_samples = settled_delay_s * self.sample_rate
        settled_samples = 0

        self.drybox.heat(target_temp)
        start_time = current_time = utime.ticks_ms()
        while True:
            current_temp = self.temp

            # Check loop pre-conditions
            if utime.ticks_diff(current_time, start_time) >= timeout_ms:
                return False
            
            # count how many times we've measured
            if target_temp - current_temp > hysteresis:
                settled_samples = 0
            elif current_temp - target_temp > hysteresis:
                settled_samples = 0
            elif settled_samples < settled_delay_samples:
                settled_samples += 1
            else:
                return True

            await asyncio.sleep_ms(self._sample_period_ms)


    async def absorb_moisture(self, timeout_s=60*60):
        start_time = utime.ticks_ms()
        self.drybox.stay_hot()
        print(f"Absorbing moistrue cycle at {self.drybox.target_temperature}")

        # What I expect to happen is that I will start with a very low humidity (probably below the target humidity)
        # and gradually increase the moisture as the warm air takes moisture out of the filament. 
        # Once we reach some kind of settled value, I'll return that value and let an outer loop handle the rest

        humidity_readings =  [0]*self._num_measurements
        for i in range(self._num_measurements): # The number of starting readings that I need
            humidity_readings[i] = self.humidity
            print(humidity_readings[:i+1])
            await asyncio.sleep(self.measurement_interval_s)

        # Do I need some smoothing?
        def get_slope(readings):
            return (readings[-1] - readings[0]) / self._num_measurements
        
        starting_slope = get_slope(humidity_readings)
        print(f"Initial humidity: {humidity_readings[0]}-{humidity_readings[-1]}, with a slope of {starting_slope} %/s")

        target_slope = self.slope_threshold * starting_slope
        current_slope = starting_slope
        current_time = utime.ticks_ms()
        while current_slope > target_slope and not did_timeout(start_time, current_time, timeout_s*1000):
            await asyncio.sleep(self.measurement_interval_s)
            
            humidity = self.humidity
            if humidity is not None:
                humidity_readings.pop(0)
                humidity_readings.append(humidity)
                current_slope = get_slope(humidity_readings)
            
            current_time = utime.ticks_ms()
            print(f"humidity: {humidity_readings}, slope: {current_slope}, target slope: {target_slope}")

        return humidity_readings[-1]



def did_timeout(ticks_start, ticks_end, timeout_ticks):
    return utime.ticks_diff(ticks_end, ticks_start) > timeout_ticks
            

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
    dehydrator = build()
    dehydrator.run()
    

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
