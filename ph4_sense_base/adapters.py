try:
    import gc

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

    def mem_stats():
        gc.collect()
        return gc.mem_alloc(), gc.mem_free()

except ImportError:
    import json  # type: ignore # noqa: F401
    import logging
    import time

    import psutil

    def const(val):
        """const() replacement for non-micropython environment"""
        return val

    def sleep_ms(val):
        return time.sleep(val / 1000.0)

    def getLogger(name):
        return logging.getLogger(name)

    def updateLogger(logger):
        return None  # does nothing, not supported outside ESP32

    def mem_stats():
        mem_info = psutil.virtual_memory()  # mem_info.total, mem_info.available,
        return mem_info.used, mem_info.free
