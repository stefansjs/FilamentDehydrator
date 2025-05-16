"""
Executes a selected app from code deployed to the Pico by reading config.toml and running the main function requested.

Ideally this lets me or others choose which app to run by editing the config.toml file without needing to open anything 
in the editor or making code-changes.
"""

import tomli as toml

def main():
    config = read_config()
    main = config.get("main", "test")
    if main == "test":
        print("Running test")
        from test import main as test_main
        test_main()

    elif main == "blink":
        print("Running blink")
        from blink import main as blink_main
        blink_main()

    elif main == "hardware":
        print("Running hardware")
        from drybox.hardware import main as hardware_main
        hardware_main()

    elif main == "drybox":
        print("Running drybox")
        from drybox.drybox import build

        drybox = build(config)
        drybox.run()

    elif main == "drybox_test":
        print("Running drybox test app")
        from drybox.drybox import main as drybox_test_main
        drybox_test_main()

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
        print(e)
