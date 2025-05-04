from external import tomli as toml

def main():
    config = read_config()
    main = config.get("main", "test")
    if main == "test":
        print("Running test")
        from test import main as test_main
        test_main()

    elif main == "drybox":
        print("Running drybox")
        from drybox.hardware import Heater
        from microapp.microapp import MicroApp

        heater = Heater(pin=1)
        # hygrometer = Hygrometer()
        app = MicroApp()
        app()

    else:
        print("no known main; running test")
        from test import main as test_main
        test_main()

def read_config(path="config.toml"):
    try:
        with open(path, "rb") as f:
            return toml.load(f)
    except OSError as e:
        print("Config file error: ", e)
        return {}

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("terminated by user")
    except BaseException as e:
        import sys
        sys.print_exception(e)
