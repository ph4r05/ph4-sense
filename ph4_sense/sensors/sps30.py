try:
    from typing import Any, Optional
except ImportError:
    Any = str


_SPS30_IMPORTED = False
_SPS30_IMPORTED_MP = False
SPS30_I2C = Any

# Machine-dependent import
if not _SPS30_IMPORTED:
    try:
        from ph4_sense_py.sensors.sps30_ada import SPS30_I2C  # type: ignore

        _SPS30_IMPORTED = True
    except ImportError:
        pass

if not _SPS30_IMPORTED:
    assert SPS30_I2C is Any
    try:
        from ph4_sense.sensors.sps30_mp import SPS30_I2C

        _SPS30_IMPORTED = True
        _SPS30_IMPORTED_MP = True
    except ImportError as e:
        print("SPS30 import error:", e)
        raise


def sps30_factory(bus, address: int = 0x69, **kwargs) -> Optional[SPS30_I2C]:
    if not _SPS30_IMPORTED:
        return None
    return SPS30_I2C(bus, address, **kwargs) if _SPS30_IMPORTED_MP else SPS30_I2C(bus, address)
