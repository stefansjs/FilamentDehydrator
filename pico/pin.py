from machine import ADC, PinLike

class Analog:
    """
    a wrapper for ADC that converts to float
    """

    TO_FLOAT = 1/65535

    def __init__(self, pin: PinLike, min_output: float = 0, max_output: float = 1):
        self.adc = ADC(pin)
        self.scale = (max_output - min_output) * self.TO_FLOAT
        self.offset = min_output 

    def read_float(self):
        # read an analog value as an int and convert to float
        return self.adc.read_u16() * self.scale + self.offset
