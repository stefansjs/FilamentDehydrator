import asyncio
from drybox.hardware import Heater
from microapp.microapp import MicroApp

def main():
    heater = Heater(pin=1)
    # hygrometer = Hygrometer()

if __name__ == "__main__":
    app = MicroApp()
    asyncio.run(app.run(main))
