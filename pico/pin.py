from machine import ADC

class Analog:
    """
    a wrapper for ADC that converts to float
    """
    TO_FLOAT = 1/65535

    @staticmethod
    def build(pin, min_output, max_output):
        """ Maps a [0 1] range to a [min_output max_output] range """
        scale = (max_output - min_output)
        offset = min_output
        return Analog(pin, scale, offset)

    def __init__(self, pin, scale:float = 1, offset:float=0):
        self.adc = ADC(pin)
        self.scale = scale * self.TO_FLOAT 
        self.offset = offset

    def read_float(self):
        # read an analog value as an int and convert to float
        return self.adc.read_u16() * self.scale + self.offset
    
    def read_int(self):
        # read an analog value as an int
        return self.adc.read_u16()
