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

    There are two optional callbacks that do what you might expect
    :
      - `error_handler`
      - `cancel_callback`

    The error handler callback is passed as an argument to the constructor and it is called when an exception is caught.
    The return value of error_handler indicates to the application whether the error was "handled" such that the 
    application can continue operating. True indicates that the application can continue (aka, "exception is handled",
    aka, "error can be ignored"); False indicates that the application should halt and the exception is reraised.

    The arguments to error_handler are (func, exception). `func` is the underlying function of the asyncio task that 
    caught the function. `exception` was the raised exception. Note that asyncio may throw exceptions, in which the func
    argument corresponds to the function that asyncio is responsible for, not necessarily the actual thrower of the 
    exception.

    error example:
    >>> def handle_error(func, exception):
    >>>     if isinstance(exception, KeyboardInterrupt):
    >>>         shutdown()
    >>>         return True:
    >>>     return False
    >>> m = MicroApp(error_handler=handle_error)

    `cancel_callback` is the callback that is called *after* the application is cancelled. This might happen because of
    a KeyboardInterrupt, but it might not happen if the main function terminates abruptly. The motivation is to allow 
    the application to perform final cleanup, like setting output pins to LOW before exiting the application. Unhandled
    exceptions might not allow cancel_callback to be called. It is recommended to have an error handler to handle this
    case.

    cancel callback example:
    >>> heater = Heater()
    >>> def cancelled():
    >>>     heater.off()
    >>> a = MicroApp(cancel_callback=cancelled)
    >>> a.run()
    $ Heater is OFF
    $ terminated by user
    """

    CANCEL = True
    DONT_CANCEL = False

    @staticmethod
    def RESET_RUN_LOOP():
        asyncio.new_event_loop()

    def __init__(self, verbose=True, error_handler=None, cancel_callback=None):
        self._scheduled_funcs = []
        self.check_count = 0
        self.shutdown = False
        self.verbose = verbose
        self.error_handler = error_handler
        self.cancel_callback = cancel_callback

    def cancel(self):
        self.shutdown = True
        print("Cancelling all scheduled tasks")
        for task, _ in self._scheduled_funcs:
            task.cancel()

        if self.cancel_callback:
            self.cancel_callback()

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
        try:
            return asyncio.run(self._main(period_ms, main_func or MicroApp._default_main))
        except BaseException as e:
            self._handle_foreground_error(main_func or MicroApp._default_main, e)


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
            print("task(s) cancelled")
            raise exception  # don't try to cancel while I'm being cancelled

        if isinstance(exception, KeyboardInterrupt):
            print("Received keyboard interrupt. Cancelling all tasks.")
            self.cancel()
            return
        
        if self.error_handler:
            should_ignore = self.error_handler(func, exception)
            if should_ignore is True:
                return
        
        print(f"Error in scheduled function {func.__name__}: {exception}")
        sys.print_exception(exception)
        self.cancel()
        raise


    def _handle_foreground_error(self, main_func, exception):
        if isinstance(exception, KeyboardInterrupt):
            print("application cancelled.")
            if self.cancel_callback:
                self.cancel_callback()
            raise exception
        
        else:
            if self.error_handler:
                should_ignore = self.error_handler(main_func, exception)
                if should_ignore is True:
                    return
            
            raise exception


    async def _main(self, period_ms, func):
        if self.verbose:
            print(f"Running {func.__name__} every {period_ms}ms")
        
        while not self.shutdown:
            self.check_count += 1
        
            should_cancel = func(self)
            if should_cancel is MicroApp.CANCEL:
                print(f"Ending {func.__name__}")
                self.shutdown = True
                return
            
            await asyncio.sleep_ms(period_ms)

        print("Finishing _main.")
        if self.cancel_callback:
            self.cancel_callback()


    def _default_main(self):
        if self.verbose:
            print("alive: {} times. current time {}:{:02d}:{:02d}T{:02d}:{:02d}:{:02d}".format(
                self.check_count, *utime.localtime()
            ))
        return MicroApp.DONT_CANCEL
        
