try:
    from typing import Any, Optional
except ImportError:
    Any = str


_SPS30_IMPORTED = False
_SPS30_IMPORTED_MP = False
SPS30 = Any

# Machine-dependent import
if not _SPS30_IMPORTED:
    try:
        from ph4_sense_py.sensors.sps30_ada import SPS30_I2C as SPS30  # type: ignore

        _SPS30_IMPORTED = True
    except ImportError:
        pass

if not _SPS30_IMPORTED:
    assert SPS30 is Any
    try:
        from ph4_sense.sensors.sps30_mp import SPS30

        _SPS30_IMPORTED = True
        _SPS30_IMPORTED_MP = True
    except ImportError as e:
        print("SPS30 import error:", e)


def sps30_factory(bus, address: int = 0x69, **kwargs) -> Optional[SPS30]:
    if not _SPS30_IMPORTED:
        return None
    return SPS30(bus, address, **kwargs) if _SPS30_IMPORTED_MP else SPS30(bus, address)
