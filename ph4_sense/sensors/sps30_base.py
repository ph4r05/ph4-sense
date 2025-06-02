from ph4_sense.adapters import const

# __version__ = "0.0.0-auto.0"
# __repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_SPS30.git"


class SPS30:
    """
    Super-class for Sensirion SPS30 particulate matter sensor.
    .. note::
        * Subclasses must implement _read_into_buffer and _read_parse_data
        * The dictionary returned by read will be changed by the next read.
        * The units for particles values are number per cubic centimetre (not ppm).
        * The units for Typical Particle Size (tps) are nm for integer
          and um for floating-point.
        * Field names follow the standard set by the adafruit_pm25 library
          omitting the decimal point in the numerical values, e.g.
          PM2.5 standard is represented by "pm25" and "25um",
          PM10 standard is represented by "pm100" and "100um".
    """

    FIELD_NAMES = (
        "pm10",
        "pm25",
        "pm40",
        "pm100",
        "pc05um",
        "pc10um",
        "pc25um",
        "pc40um",
        "pc100um",
        "tps",
    )
    DEFAULT_RETRIES = const(1)

    # SPS30 min firmware version in comments if not V1.0
    CMD_START_MEASUREMENT = const(0x0010)
    CMD_STOP_MEASUREMENT = const(0x0104)
    CMD_READ_DATA_READY_FLAG = const(0x0202)
    CMD_READ_MEASURED_VALUES = const(0x0300)
    CMD_SLEEP = const(0x1001)  # V2.0
    CMD_WAKEUP = const(0x1103)  # V2.0
    CMD_START_FAN_CLEANING = const(0x5607)
    CMD_RW_AUTO_CLEANING_INTERVAL = const(0x8004)
    CMD_READ_PRODUCT_TYPE = const(0xD002)
    CMD_READ_SERIAL_NUMBER = const(0xD033)
    CMD_READ_VERSION = const(0xD100)
    CMD_READ_DEVICE_STATUS_REG = const(0xD206)  # V2.2
    CMD_CLEAR_DEVICE_STATUS_REG = const(0xD210)  # V2.0
    CMD_SOFT_RESET = const(0xD304)

    # mask values for read_status_register()
    STATUS_FAN_ERROR = const(1 << 4)
    STATUS_LASER_ERROR = const(1 << 5)
    STATUS_FAN_CLEANING = const(1 << 19)  # undocumented
    STATUS_FAN_SPEED_WARNING = const(1 << 21)

    # time in mseconds for clean operation to complete
    FAN_CLEAN_TIME = const(15_000)
    _WRONG_CLASS_TXT = "Object must be instantiated as an SPS30_I2C or SPS30_UART"

    def __init__(self):
        if type(self) is SPS30:  # pylint: disable=unidiomatic-typecheck; noqa: E721
            raise TypeError(self._WRONG_CLASS_TXT)

        self.aqi_reading = {k: None for k in self.FIELD_NAMES}

    def _read_into_buffer(self):
        """Low level buffer filling function, to be overridden"""
        raise NotImplementedError(self._WRONG_CLASS_TXT)

    def _read_parse_data(self, output):
        """Low level buffer parsing function, to be overridden"""
        raise NotImplementedError(self._WRONG_CLASS_TXT)

    def read(self):
        """Read any available data from the air quality sensor and
        return a dictionary with available particulate/quality data"""
        self._read_into_buffer()
        self._read_parse_data(self.aqi_reading)
        return self.aqi_reading
