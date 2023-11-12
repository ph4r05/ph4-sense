try:
    from typing import Any, Optional
except ImportError:
    Any = str


from ph4_sense.sensors.ccs811base import CCS811Custom

_CCS811_IMPORTED = False
CSS811Adapter = Any

# Machine-dependent import
# if not _CCS811_IMPORTED:
#     try:
#         from ph4_sense_py.sensors.ccs811_ada import AdaCCS811 as CSS811Adapter
#
#         _CCS811_IMPORTED = True
#     except ImportError:
#         pass

if not _CCS811_IMPORTED:
    assert CSS811Adapter is Any
    try:
        from ph4_sense.sensors.ccs811_mp import MicroCCS811 as CSS811Adapter

        _CCS811_IMPORTED = True
    except ImportError as e:
        print("CCS811 import error:", e)


def css811_factory(bus, address: int = 0x5A) -> Optional[CCS811Custom]:
    if not _CCS811_IMPORTED:
        return None

    return CCS811Custom(CSS811Adapter(bus, address))
