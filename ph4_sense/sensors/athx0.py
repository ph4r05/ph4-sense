try:
    from typing import Any, Optional
except ImportError:
    Any = str


_AHTX0_IMPORTED = False
AHTx0 = Any

# Machine-dependent import
# if not _AHTX0_IMPORTED:
#     try:
#         from ph4_sense_py.sensors.athx0_ada import AdaAHTx0 as AHTx0  # type: ignore
#
#         _AHTX0_IMPORTED = True
#     except ImportError:
#         pass

if not _AHTX0_IMPORTED:
    assert AHTx0 is Any
    try:
        from ph4_sense.sensors.athx0_mp import AHTx0

        _AHTX0_IMPORTED = True
    except ImportError as e:
        print("AHTx0 import error:", e)


def ahtx0_factory(bus, address: int = 0x38) -> Optional[AHTx0]:
    if not _AHTX0_IMPORTED:
        return None
    return AHTx0(bus, address)
