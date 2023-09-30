try:
    from typing import Any, Optional
except ImportError:
    Any = str


_AHTX0_IMPORTED = False
AHTx0 = Any

# Machine-dependent import
if not _AHTX0_IMPORTED:
    try:
        from adafruit_ahtx0 import AHTx0  # type: ignore

        _AHTX0_IMPORTED = True
    except ImportError:
        pass

if not _AHTX0_IMPORTED:
    assert AHTx0 is Any
    try:
        from ph4_esp32.sensors.athx0_mp import AHTx0

        _AHTX0_IMPORTED = True
    except ImportError:
        pass


def ahtx0_factory(bus, address: int = 0x38) -> Optional[AHTx0]:
    if not _AHTX0_IMPORTED:
        return None
    return AHTx0(bus, address)
