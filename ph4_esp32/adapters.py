try:
    import ujson as json
    import utime as time
    from micropython import const
    from utime import sleep_ms

except ImportError:
    import json  # type: ignore # noqa: F401
    import time

    def const(val):
        """const() replacement for non-micropython environment"""
        return val

    def sleep_ms(val):
        return time.sleep(val / 1000.0)
