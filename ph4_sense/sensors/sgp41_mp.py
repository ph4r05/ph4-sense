from ph4_sense.adapters import const, sleep_ms
from ph4_sense.support.sensor_helper import SensorHelper

try:
    from machine import I2C
except ImportError:
    from busio import I2C

try:
    from typing import Optional
except ImportError:
    pass


# General SGP41 settings
SGP41_DEFAULT_I2C_ADDR = const(0x59)
SGP41_WORD_LEN = const(2)
SGP41_CRC8_POLYNOMIAL = const(0x31)
SGP41_CRC8_INIT = const(0xFF)
SGP41_CRC8_FINAL_XOR = const(0xFF)
SGP41_MEASURE_TEST_PASS = const(0xD400)

SGP41_DEFAULT_COMPENSATION_RH = 0x8000  # in ticks as defined by SGP41
SGP41_DEFAULT_COMPENSATION_T = 0x6666  # in ticks as defined by SGP41

# SGP41 feature set measurement commands (Hex Codes)
# Conditioning
SGP41_CMD_CONDITIONING_HEX = [0x26, 0x12]
SGP41_CMD_CONDITIONING_WORDS = const(2)
SGP41_CMD_CONDITIONING_MAX_MS = const(50)

# Raw data measure
SGP41_CMD_MEASURE_RAW_HEX = [0x26, 0x19]
SGP41_CMD_MEASURE_RAW_WORDS = const(2)
SGP41_CMD_MEASURE_RAW_MAX_MS = const(50)

# Self-test
SGP41_CMD_SELF_TEST_HEX = [0x28, 0x0E]
SGP41_CMD_SELF_TEST_WORDS = 1
SGP41_CMD_SELF_TEST_MAX_MS = const(320)

SGP41_CMD_TURN_OFF_HEATER_HEX = [0x36, 0x15]

# Obtaining Serial ID (datasheet section 6.5)
SGP41_CMD_GET_SERIAL_ID_HEX = [0x36, 0x82]
SGP41_CMD_GET_SERIAL_ID_WORDS = const(3)
SGP41_CMD_GET_SERIAL_ID_MAX_MS = const(10)


class SGP41:
    """
    A driver for the SGP41 gas sensor.
    https://sensirion.com/media/documents/5FE8673C/61E96F50/Sensirion_Gas_Sensors_Datasheet_SGP41.pdf

    :param i2c: The "I2C" object to use. This is the only required parameter.
    :param int addr: (optional) The I2C address of the device.
    :param boolean measure_test: (optional) Whether to run on-chip test during initialisation.
    :param boolean iaq_init: (optional) Whether to initialise SGP41 algorithm / baseline.
    """

    def __init__(self, i2c: I2C, addr=SGP41_DEFAULT_I2C_ADDR, measure_test=False, iaq_init=True, sensor_helper=None):
        """Initialises the sensor and display stats"""
        self._i2c = i2c
        # if addr not in self._i2c.scan():
        #     raise IOError("No SGP41 device found on I2C bus")

        self.addr = addr
        self.cmd_buf_2 = bytearray(2)
        self.resp_buf_8 = bytearray(8)
        self.repl_buf_2 = [0, 0]
        self.sensor_helper = sensor_helper or SensorHelper()

        self.serial = self.get_serial()
        if measure_test:
            test_result = self.self_test()
            if SGP41_MEASURE_TEST_PASS != test_result:
                self.sensor_helper.log_error("Err: Device failed the on-chip test: ", hex(test_result))
                # raise RuntimeError("Device failed the on-chip test")

        self.sensor_helper.log_info(
            "SGP41 device discovered...\n"
            + "I2C address: "
            + str(self.addr)
            + "\n"
            + "Serial ID: "
            + str(self.serial)
            + "\n"
            + "Initialise algo: "
            + str(iaq_init)
        )
        if iaq_init:
            self.sensor_helper.log_info("Initializing...")
            self.execute_conditioning()
            sleep_ms(10_000)
            self.measure_raw()

    def measure_raw(self, rh: Optional[float] = None, temp: Optional[float] = None):
        """
        sgp41_measure_raw_signals() - This command starts/continues the VOC+NOx
        measurement mode

        :param rh: Leaves humidity compensation disabled by sending the
        default value 0x8000 (50%RH) or enables humidity compensation when sending
        the relative humidity in ticks (ticks = %RH * 65535 / 100)

        :param temp: Leaves humidity compensation disabled by sending the
        default value 0x6666 (25 degC) or enables humidity compensation when sending
        the temperature in ticks (ticks = (degC + 45) * 65535 / 175)

        :return: sraw_voc: u16 unsigned integer directly provides the raw signal
        SRAW_VOC in ticks which is proportional to the logarithm of the resistance of
        the sensing element.
                 sraw_nox: u16 unsigned integer directly provides the raw signal
        SRAW_NOX in ticks which is proportional to the logarithm of the resistance of
        the sensing element.
        """
        tick_rh, tick_t = convert_to_ticks(rh, temp)
        cmd_buff = [
            SGP41_CMD_MEASURE_RAW_HEX[0],
            SGP41_CMD_MEASURE_RAW_HEX[1],
            (tick_rh >> 8) & 0xFF,
            tick_rh & 0xFF,
            0,
            (tick_t >> 8) & 0xFF,
            tick_t & 0xFF,
            0,
        ]
        cmd_buff[4] = generate_crc(cmd_buff, 2, 4)
        cmd_buff[7] = generate_crc(cmd_buff, 5, 7)

        return self._i2c_read_words_from_cmd(
            cmd_buff,
            SGP41_CMD_MEASURE_RAW_MAX_MS,
            SGP41_CMD_MEASURE_RAW_WORDS,
        )

    def execute_conditioning(self, default_rh: Optional[float] = None, default_t: Optional[float] = None):
        """
        This command starts the conditioning, i.e.,
        the VOC pixel will be operated at the same temperature as it is by calling
        the sgp41_measure_raw command while the NOx pixel will be operated at a
        different temperature for conditioning. This command returns only the
        measured raw signal of the VOC pixel SRAW_VOC as 2 bytes (+ 1 CRC byte).
        Warning, cannot stay in this state longer than 10s, chip can be damaged

        :param default_rh: Default conditions for relative humidty.
        :param default_t: Default conditions for temperature.
        :return: sraw_voc u16 unsigned integer directly provides the raw signal
        SRAW_VOC in ticks which is proportional to the logarithm of the resistance of
        the sensing element.
        """
        tick_rh, tick_t = convert_to_ticks(default_rh, default_t)
        buffer = [
            (tick_rh >> 8) & 0xFF,
            tick_rh & 0xFF,
            0,
            (tick_t >> 8) & 0xFF,
            tick_t & 0xFF,
            0,
        ]
        buffer[2] = generate_crc(buffer, 0, 2)
        buffer[5] = generate_crc(buffer, 3, 5)

        sraw_voc = self._i2c_read_words_from_cmd(
            SGP41_CMD_CONDITIONING_HEX + buffer,
            SGP41_CMD_CONDITIONING_MAX_MS,
            SGP41_CMD_CONDITIONING_WORDS,
        )
        return sraw_voc[0]

    def self_test(self):  # OK
        """
        sgp41_execute_self_test() - This command triggers the built-in self-test
        checking for integrity of both hotplate and MOX material and returns the
        result of this test as 2 bytes

        :return: test_result 0xXX 0xYY: ignore most significant byte 0xXX. The four
        least significant bits of the least significant byte 0xYY provide information
        if the self-test has or has not passed for each individual pixel. All zero
        mean all tests passed successfully. Check the datasheet for more detailed
        information.
        """
        r = self._i2c_read_words_from_cmd(
            SGP41_CMD_SELF_TEST_HEX,
            SGP41_CMD_SELF_TEST_MAX_MS,
            SGP41_CMD_SELF_TEST_WORDS,
        )
        return r[0]

    def turn_off_heater(self):  # OK
        """
        sgp41_turn_heater_off() - This command turns the hotplate off and stops the
        measurement. Subsequently, the sensor enters the idle mode.
        """
        self._i2c_read_words_from_cmd(
            SGP41_CMD_TURN_OFF_HEATER_HEX,
            SGP41_CMD_GET_SERIAL_ID_MAX_MS,
            0,
        )

    def get_serial(self):  # OK
        """
        sgp41_get_serial_number() - This command provides the decimal serial number
        of the SGP41 chip by returning 3x2 bytes.

        :return: serial_number 48-bit unique serial number
        """
        serial = self.serial = self._i2c_read_words_from_cmd(
            SGP41_CMD_GET_SERIAL_ID_HEX,
            SGP41_CMD_GET_SERIAL_ID_MAX_MS,
            SGP41_CMD_GET_SERIAL_ID_WORDS,
        )
        return serial

    def _i2c_read_words_from_cmd(self, command, delay, reply_size):
        """Runs an SGP command query, gets a reply and CRC results if necessary"""
        if len(command) == 2:
            self.cmd_buf_2[0] = command[0]
            self.cmd_buf_2[1] = command[1]
            cmd_buf = self.cmd_buf_2
        else:
            cmd_buf = bytes(command)

        self._i2c.writeto(self.addr, cmd_buf)
        sleep_ms(delay)
        if not reply_size:
            return None

        buf_size = reply_size * (SGP41_WORD_LEN + 1)
        crc_result = self.resp_buf_8 if buf_size == len(self.resp_buf_8) else bytearray(buf_size)
        self._i2c.readfrom_into(self.addr, crc_result)

        result = self.repl_buf_2 if reply_size == len(self.repl_buf_2) else [0] * reply_size
        for i in range(reply_size):
            if generate_crc(crc_result, 3 * i, 3 * i + 2) != crc_result[3 * i + 2]:
                raise RuntimeError("CRC Error")
            result[i] = (crc_result[3 * i] << 8) | crc_result[3 * i + 1]
        return result


def generate_crc(data, offset=0, limit=None):
    """
    8-bit CRC algorithm for checking data.
    Calculation described in section 6.6 of SGP41 datasheet
    """
    crc = SGP41_CRC8_INIT
    # Calculates 8-Bit CRC checksum with given polynomial
    for idx in range(offset, len(data) if limit is None else limit):
        byte = data[idx]
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ SGP41_CRC8_POLYNOMIAL
            else:
                crc <<= 1
    return crc & 0xFF


def convert_to_ticks(s_rh: Optional[float], s_temp: Optional[float]):
    s_rh = s_rh if s_rh is not None else 50.001
    s_temp = s_temp if s_temp is not None else 25.0
    compensation_rh = int(s_rh * 65535 / 100.0)
    compensation_t = int((s_temp + 45) * 65535 / 175.0)
    return compensation_rh, compensation_t
