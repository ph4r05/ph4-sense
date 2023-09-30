try:
    from typing import Any, Optional
except ImportError:
    Any = str


_SCD40X_IMPORTED = False
SCD4X = Any
SCD4X_DEFAULT_ADDR = 0x62

# Machine-dependent import
if not _SCD40X_IMPORTED:
    try:
        from adafruit_scd4x import SCD4X, SCD4X_DEFAULT_ADDR  # type: ignore

        _SCD40X_IMPORTED = True
    except ImportError:
        pass

if not _SCD40X_IMPORTED:
    assert SCD4X is Any
    try:
        from ph4_sense.sensors.scd4x_mp import SCD4X, SCD4X_DEFAULT_ADDR  # noqa: F811

        _SCD40X_IMPORTED = True
    except ImportError as e:
        print("SCD40X import error:", e)


def scd4x_factory(bus, address: int = SCD4X_DEFAULT_ADDR) -> Optional[SCD4X]:
    if not _SCD40X_IMPORTED:
        return None
    return SCD4X(bus, address)
