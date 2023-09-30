try:
    from micropython import const

except ImportError:

    def const(val):
        """const() replacement for non-micropython environment"""
        return val
