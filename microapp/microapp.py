

import asyncio


class MicroApp:

    def __init__(self, heartbeat_interval_ms=10000):
        self._scheduled_funcs = []
        self._delayed_funcs = []
        self.check_count = 0
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self.check = None


    def schedule(self, interval_ms, func, *args, **kwargs):
        """
        Schedule a function to be called at a specified interval.
        
        Args:
            interval_ms (int): The interval in milliseconds between function calls.
            func (callable): The function to be called.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.
        """
        bound_func = Functor(func, *args, **kwargs)
        return


    def delay(self, interval_ms, func, *args, **kwargs):
        """
        Delay the execution of a function by a specified interval.
        
        Args:
            interval_ms (int): The delay in milliseconds before the function is called.
            func (callable): The function to be called.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.
        """
        bound_func = Functor(func, *args, **kwargs)
        return


    async def run(self, main_func, *args, **kwargs):
        """
        Main function to run the microapp.
        
        Args:
            main_func (callable): The main function to run.
            *args: Positional arguments to pass to the main function.
            **kwargs: Keyword arguments to pass to the main function.
        """
        while True:
            self.check_count = self.check_count + 1
            if self.check is not None:
                if not self.check():
                    print("Panicing because check() returned a Falsey value")
                    Functor.panic()
                    return
            await asyncio.sleep_ms(self.heartbeat_interval_ms)


class Functor:
    PANIC = False

    @classmethod
    def panic(cls):
        cls.PANIC = True

    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.name = func.__name__

    def __call__(self):
        if self.PANIC:
            print(f"Shutting down {self} due to PANIC")
            return
        
        return self.func(*self.args, **self.kwargs)
    
    def __str__(self) -> str:
        return self.name
