try:
    from typing import Any, Optional
except ImportError:
    Any = str


_SGP41_IMPORTED = False
_SGP41_IMPORTED_MP = False
SGP41 = Any

# Machine-dependent import
# if not _SGP41_IMPORTED:
#     try:
#         from ph4_sense_py.sensors.sgp41_ada import AdaSGP41 as SGP41  # type: ignore
#
#         _SGP41_IMPORTED = True
#     except ImportError:
#         pass

if not _SGP41_IMPORTED:
    assert SGP41 is Any
    try:
        from ph4_sense.sensors.sgp41_mp import SGP41

        _SGP41_IMPORTED = True
        _SGP41_IMPORTED_MP = True
    except ImportError as e:
        print("SGP32 import error:", e)


def sgp41_factory(bus, address: int = 0x59, **kwargs) -> Optional[SGP41]:
    if not _SGP41_IMPORTED:
        return None
    return SGP41(bus, address, **kwargs) if _SGP41_IMPORTED_MP else SGP41(bus, address)
