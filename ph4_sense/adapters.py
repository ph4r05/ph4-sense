try:
    import ujson as json
    import utime as time
    from micropython import const
    from utime import sleep_ms

    class DummyLogger:
        def __init__(self):
            pass

        def __getattr__(self, name):
            return self.dummy()

        def dummy(self, *args, **kwargs):
            return None

    DUMMY_LOGGER = DummyLogger()
    MAIN_LOGGER = DUMMY_LOGGER

    def getLogger(name):
        return MAIN_LOGGER

    def updateLogger(logger):
        global MAIN_LOGGER
        MAIN_LOGGER = logger

except ImportError:
    import json  # type: ignore # noqa: F401
    import logging
    import time

    def const(val):
        """const() replacement for non-micropython environment"""
        return val

    def sleep_ms(val):
        return time.sleep(val / 1000.0)

    def getLogger(name):
        return logging.getLogger(name)

    def updateLogger(logger):
        return None  # does nothing, not supported outside ESP32
