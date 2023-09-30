try:
    from typing import Any, Optional
except ImportError:
    Any = str


_SGP30_IMPORTED = False
_SGP30_IMPORTED_MP = False
SGP30 = Any

# Machine-dependent import
if not _SGP30_IMPORTED:
    try:
        from adafruit_sgp30 import Adafruit_SGP30 as SGP30  # type: ignore

        _SGP30_IMPORTED = True
    except ImportError:
        pass

if not _SGP30_IMPORTED:
    assert SGP30 is Any
    try:
        from ph4_esp32.sensors.sgp30_mp import SGP30

        _SGP30_IMPORTED = True
        _SGP30_IMPORTED_MP = True
    except ImportError as e:
        print("SGP32 import error:", e)


def sgp30_factory(bus, address: int = 0x58, **kwargs) -> Optional[SGP30]:
    if not _SGP30_IMPORTED:
        return None
    return SGP30(bus, address, **kwargs) if _SGP30_IMPORTED_MP else SGP30(bus, address)
