"""
Creates an asyncio-based app that allows you to schedule some functions peridically without using threads/processes.
"""

import asyncio
import sys
import utime


class MicroApp:
    """
    The main design of this class is to provide a main function that performs tasks like safety checks, and that will
    handle interrupts like SIGTERM. The bulk of main() has to do things like checking for clean or panicked shutdowns,
    but it also requires interfacing with a client main loop.

    I guess the idea is to create an event-driven architecture where you don't have to worry very hard about the main loop.

    Example:
    >>> app = MicroApp()
    >>> app.schedule(2000, print, "every 2 seconds)
    >>> app.schedule(1000, print, "every 1 second")
    >>> app.run()

    You can schedule any function to be called periodically with MicroApp.schedule by passing subsequent args and kwargs.
    Run the whole application with run().

    Optionally, you can pass a function to run that can be used as a sanity check to cleanly (or not) shutdown the app.
    The only argument passed to the function passed in run is the MicroApp instance itself. This can be used to access 
    other scheduled tasks, or to cancel the entire application. To stop gently, return MicroApp.CANCEL.

    example:
    >>> def main(app):
    >>>     if overheated():
    >>>         app.cancel()
    >>>         return MicroApp.CANCEL
    >>>     else:
    >>>         print("alive")
    >>>         return MicroApp.DONT_CANCEL
    >>> app = MicroApp()
    >>> app.run(1000, main)

    That argument is the only difference between calling app.schedule(period, func) and app.run(period, func). 
    You do you.
    """

    CANCEL = True
    DONT_CANCEL = False

    @staticmethod
    def RESET_RUN_LOOP():
        asyncio.new_event_loop()

    def __init__(self, verbose=True):
        self._scheduled_funcs = []
        self.check_count = 0
        self.shutdown = False
        self.verbose = verbose
        self.error_handler = None

    def cancel(self):
        self.shutdown = True
        print("Cancelling all scheduled tasks")
        for task, _ in self._scheduled_funcs:
            task.cancel()

    def schedule(self, interval_ms, func, *args, **kwargs):
        """
        Schedule a function to be called periodically at a specified interval.
        No results will be returned. You will need to do your own parameter handling.
        
        Args:
            interval_ms (int): The interval in milliseconds between function calls.
            func (callable): The function to be called.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.
        """
        self.add_scheduled(self._do_periodic(interval_ms, func, *args, **kwargs))

    def add_scheduled(self, coroutine):
        task = asyncio.create_task(coroutine)
        self._scheduled_funcs.append([task, None])

    def run(self, period_ms=5000, main_func=None):
        return asyncio.run(self._main(period_ms, main_func or MicroApp._default_main))


    async def _do_periodic(self, interval_ms, func, *args, **kwargs):
        """
        Calls a function peridocally at a specified interval. Schedule overruns are not prevented.
        If you have a task that may occasionally take more time than the interval period you'll be fine, 
        but it is up to you to ensure this doesn't happen too often.
        """
        while True:
            start = utime.ticks_ms()
            try:
                func(*args, **kwargs)
            except BaseException as e:
                self._handle_background_error(func, e)
            
            delay_ms = interval_ms - utime.ticks_diff(utime.ticks_ms(), start)
            await asyncio.sleep_ms(delay_ms)

    async def _repeat_with_interval(self, interval_ms, func, *args, **kwargs):
        while True:
            try:
                func(*args, **kwargs)
            except BaseException as e:
                self._handle_background_error(func, e)

            await asyncio.sleep_ms(interval_ms)


    def _handle_background_error(self, func, exception):
        if isinstance(exception, asyncio.CancelledError):
            raise exception  # don't try to cancel while I'm being cancelled

        if isinstance(exception, KeyboardInterrupt):
            print("Received keyboard interrupt. Cancelling all tasks.")
            self.cancel()
            return
        
        if self.error_handler:
            should_ignore = self.error_handler(func, exception)
            if should_ignore:
                return
        
        print(f"Error in scheduled function {func.__name__}: {exception}")
        sys.print_exception(exception)
        self.cancel()
        raise

    async def _main(self, period_ms, func):
        if self.verbose:
            print(f"Running {func.__name__} every {period_ms}ms")
        
        while not self.shutdown:
            self.check_count += 1
        
            should_cancel = func(self)
            if should_cancel is MicroApp.CANCEL:
                self.shutdown = True
                return
            
            await asyncio.sleep_ms(period_ms)

    def _default_main(self):
        if self.verbose:
            print("alive: {} times. current time {}:{:02d}:{:02d}T{:02d}:{:02d}:{:02d}".format(
                self.check_count, *utime.localtime()
            ))
        return MicroApp.DONT_CANCEL
        
