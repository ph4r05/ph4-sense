try:
    from typing import Any, Optional
except ImportError:
    Any = str


_HDC1080_IMPORTED = False
HDC1080 = Any

# Machine-dependent import
# if not _HDC1080_IMPORTED:
#     try:
#         from ph4_sense_py.sensors.hdc1080_ada import HDC1080
#
#         _HDC1080_IMPORTED = True
#     except ImportError:
#         pass

if not _HDC1080_IMPORTED:
    assert HDC1080 is Any
    try:
        from ph4_sense.sensors.hdc1080_mp import HDC1080

        _HDC1080_IMPORTED = True
    except ImportError as e:
        print("HDC1080 import error:", e)


def hdc1080_factory(bus, address: int = 0x40, **kwargs) -> Optional[HDC1080]:
    if not _HDC1080_IMPORTED:
        return None
    return HDC1080(bus, address, **kwargs)
