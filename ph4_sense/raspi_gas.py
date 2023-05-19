import time
from typing import Optional

import board  # adafruit-blinka
import busio
import json
from collections import deque
import statistics
import adafruit_sgp30  # adafruit-circuitpython-sgp30
import adafruit_ahtx0  # adafruit-circuitpython-ahtx0
import adafruit_ccs811  # adafruit-circuitpython-ccs811
import adafruit_scd4x  # adafruit-circuitpython-scd4x
import paho.mqtt.client as mqtt  # paho-mqtt


MQTT_CLIENT_NAME = 'SGP30_sensor_office'
MQTT_SERVER = '10.0.1.103'
MQTT_SERVER_PORT = 1883
MQTT_SENSOR_SUFFIX = '_office'
HAS_AHT = True
HAS_SGP30 = True
HAS_CCS811 = True
HAS_SCD4X = True


class ExpAverage:
    def __init__(self, alpha=0.1, default=None):
        self.alpha = alpha
        self.average = default

    def update(self, value):
        if self.average is None:
            self.average = value
        else:
            self.average = self.alpha * value + (1 - self.alpha) * self.average
        return self.average

    @property
    def cur(self):
        return self.average


class FloatingMedian:
    def __init__(self, window_size=5):
        self.window_size = window_size
        self.data = deque([], maxlen=window_size)
        self._median = None

    def add(self, value):
        if value is None:
            return
        self._median = None
        self.data.append(value)

    def update(self, value):
        self.add(value)
        return self.median()

    def median(self):
        if self._median is None:
            self._median = statistics.median(self.data) if self.data else None

        return self._median

    @property
    def cur(self):
        return self.median()


class SensorFilter:
    def __init__(self, median_window=5, alpha=0.1):
        self.floating_median = FloatingMedian(median_window)
        self.exp_average = ExpAverage(alpha)

    def update(self, value):
        r = self.floating_median.update(value)
        if r is not None:
            return self.exp_average.update(r)
        return None

    @property
    def cur(self):
        return self.exp_average.cur

    @property
    def cur_median(self):
        return self.floating_median.cur


class CCS811Custom(adafruit_ccs811.CCS811):
    MAX_TVOC = 32_768
    MAX_CO2 = 29_206

    def __init__(self, i2c_bus: busio.I2C, address: int = 0x5A):
        super().__init__(i2c_bus, address)
        self.r_status = None
        self.r_error_id = None
        self.r_raw_data = None
        self.r_raw_current = None
        self.r_raw_adc = None
        self.r_err_str = ''
        self.r_stat_str = ''
        self.r_error = None
        self.r_overflow = False
        self.r_orig_co2 = None
        self.r_orig_tvoc = None

    def reset_r(self):
        self.r_status = None
        self.r_error_id = None
        self.r_raw_data = None
        self.r_raw_current = None
        self.r_raw_adc = None
        self.r_err_str = ''
        self.r_stat_str = ''
        self.r_error = None
        self.r_overflow = False
        self.r_orig_co2 = None
        self.r_orig_tvoc = None

    @staticmethod
    def err_to_str(err: int) -> str:
        ret = ''
        err = err or 0
        if err & 0x1:
            ret += 'Wi '  # WRITE_REG_INVALID
        if err & 0x2:
            ret += 'Ri '  # READ_REG_INVALID
        if err & 0x4:
            ret += 'Mi '  # MEASMODE_INVALID
        if err & 0x8:
            ret += 'Mr '  # MAX_RESISTANCE
        if err & 0x10:
            ret += 'Hf '  # HEATER_FAULT
        if err & 0x20:
            ret += 'Hs '  # HEATER_SUPPLY
        return ret

    def read_data(self) -> (Optional[int], Optional[int]):
        self.reset_r()
        if self.data_ready and self.app_valid:
            buf = bytearray(9)
            buf[0] = adafruit_ccs811._ALG_RESULT_DATA
            with self.i2c_device as i2c:
                i2c.write_then_readinto(buf, buf, out_end=1, in_start=1)

            # https://cdn.sparkfun.com/assets/2/c/c/6/5/CN04-2019_attachment_CCS811_Datasheet_v1-06.pdf
            self.r_orig_co2 = self._eco2 = ((buf[1] << 8) | (buf[2]))  # & ~0x8000
            self.r_orig_tvoc = self._tvoc = ((buf[3] << 8) | (buf[4]))  # & ~0x8000
            self.r_status = buf[5]
            self.r_error_id = buf[6]
            self.r_raw_data = buf[7:9]
            self.r_raw_current = int((buf[7] & (~0x3)) >> 2)
            self.r_raw_adc = (1.65/1023) * (int(buf[7] & 0x3) << 8 | int(buf[8]))
            self.r_err_str = CCS811Custom.err_to_str(self.r_error_id)

            if self._eco2 > CCS811Custom.MAX_CO2:
                self.r_overflow = True
                self._eco2 = self._eco2 & ~0x8000

            if self._tvoc > CCS811Custom.MAX_TVOC:
                self.r_overflow = True
                self._tvoc = self._tvoc - CCS811Custom.MAX_TVOC

            if self.r_status & 0x1:
                self.r_stat_str += 'Er '  # Error
            if self.r_status & 0x8:
                self.r_stat_str += 'Dr '  # Data ready
            if self.r_status & 0x10:
                self.r_stat_str += 'F+ '  # Valid Fw loaded
            else:
                self.r_stat_str += 'F- '  # Valid Fw loaded

            if self.r_status & 0x80:
                self.r_stat_str += 'R+ '  # FW_MODE, 1 = ready to measure
            else:
                self.r_stat_str += 'R- '  # FW_MODE, 1 = ready to measure

            if self.error:
                self.r_error = self.error_code
                self.r_err_str = CCS811Custom.err_to_str(self.r_error)
                raise RuntimeError(f'Error: {str(self.r_error)} [{self.r_err_str}]')

            return (self._eco2, self._tvoc) # if not self.r_error_id else (None, None)

        return None, None


def try_fnc(x, msg=None):
    try:
        return x()
    except Exception as e:
        print(f'Err {msg or ""}: {e}')


def dval(val, default=-1):
    return val if val is not None else default


# Initialize I2C bus
# i2c = busio.I2C(board.SCL7, board.SDA7)
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize sensors
sgp30 = adafruit_sgp30.Adafruit_SGP30(i2c) if HAS_SGP30 else None
aht21 = adafruit_ahtx0.AHTx0(i2c) if HAS_AHT else None
ccs811 = CCS811Custom(i2c) if HAS_CCS811 else None
scd4x = adafruit_scd4x.SCD4X(i2c) if HAS_SCD4X else None

client = mqtt.Client(MQTT_CLIENT_NAME)
client.connect(MQTT_SERVER, MQTT_SERVER_PORT)

# Measure air quality
if HAS_SGP30:
    sgp30.set_iaq_relative_humidity(21, 0.45)
    sgp30.set_iaq_baseline(0x8973, 0x8aae)
    sgp30.iaq_init()

if HAS_SCD4X:
    scd4x.start_periodic_measurement()

if HAS_CCS811:
    ccs811.drive_mode = adafruit_ccs811.DRIVE_MODE_1SEC
    # ccs811.drive_mode = adafruit_ccs811.DRIVE_MODE_60SEC
    # ccs811.drive_mode = adafruit_ccs811.DRIVE_MODE_250MS
    # ccs811.drive_mode = adafruit_ccs811.DRIVE_MODE_10SEC

# Initialize sensor measurements
co2eq = 0
tvoc = 0
eavg = ExpAverage(0.1)
eavg_css811_co2 = SensorFilter(median_window=7, alpha=0.2)
eavg_sgp30_co2 = SensorFilter(median_window=5, alpha=0.2)
eavg_css811_tvoc = SensorFilter(median_window=7, alpha=0.2)
eavg_sgp30_tvoc = SensorFilter(median_window=5, alpha=0.2)

last_ccs811_co2 = 0
last_ccs811_tvoc = 0
last_sgp30_co2 = 0
last_sgp30_tvoc = 0

last_tsync = time.time() + 60
last_pub = time.time() + 30
last_pub_sgp = time.time() + 30
last_reconnect = time.time()

scd40_co2, scd40_temp, scd40_hum = None, None, None
while True:
    t = time.time()
    temp = None
    humd = None

    if t - last_reconnect > 60 * 10:
        try_fnc(lambda: client.disconnect())
        time.sleep(1)
        try:
            client.connect(MQTT_SERVER, MQTT_SERVER_PORT)
            last_reconnect = t
        except Exception as e:
            print(f'MQTT connection error: {e}')

    try:
        cal_temp = scd40_temp
        cal_hum = scd40_hum

        temp = try_fnc(lambda: aht21.temperature) if HAS_AHT else None
        humd = try_fnc(lambda: aht21.relative_humidity) if HAS_AHT else None
        if not cal_temp or not cal_hum:
            cal_temp = temp
            cal_hum = humd

        if cal_temp and cal_hum and time.time() - last_tsync > 180:
            if HAS_SGP30:
                try_fnc(lambda: sgp30.set_iaq_relative_humidity(cal_temp, cal_hum))
            if HAS_CCS811:
                # try_fnc(lambda: ccs811.set_environmental_data(int(cal_hum), cal_temp))
                pass

            last_tsync = time.time()
            print(f'Temp sync')

    except Exception as e:
        print(f'E: exc in temp {e}')

    try:
        if HAS_SGP30:
            sgp30.iaq_measure()
    except Exception as e:
        print(f'Exception measurement: {e}')
        time.sleep(1)
        continue

    ccs_co2, ccs_tvoc = 0, 0
    if HAS_CCS811:
        try:
            nccs_co2, nccs_tvoc = ccs811.read_data()
            inv_ctr = 0

            if nccs_co2 is not None and 400 < nccs_co2 < 30_000:
                last_ccs811_co2 = ccs_co2 = nccs_co2
                eavg_css811_co2.update(nccs_co2)
            else:
                inv_ctr += 1

            if nccs_tvoc is not None and 0 <= nccs_tvoc < 30_000:
                last_ccs811_tvoc = ccs_tvoc = nccs_tvoc
                eavg_css811_tvoc.update(nccs_tvoc)
            else:
                inv_ctr += 1

            if inv_ctr or ccs811.r_overflow:
                print(f'  CCS inv read, orig ({ccs811.r_orig_co2} {(nccs_co2 or 0)& ~0x8000}, {ccs811.r_orig_tvoc}), '
                      f'status: {ccs811.r_status}, '
                      f'error id: {ccs811.r_error_id} = [{ccs811.r_err_str}] [{ccs811.r_stat_str}], '
                      f'raw I={ccs811.r_raw_current} uA, U={dval(ccs811.r_raw_adc):.5f} V, '
                      f'Fw: {int(dval(ccs811.fw_mode))} Dm: {ccs811.drive_mode}')

            if ccs811.error:
                print(f'Err: {ccs811.r_error} = {CCS811Custom.err_to_str(ccs811.r_error)}')
        except Exception as e:
            print(f'CCS error: {e}')

    try:
        valid_cnt = 0
        co2eq_1, tvoc, eth, h2 = sgp30.eCO2, sgp30.TVOC, sgp30.Ethanol, sgp30.H2
        if co2eq_1:
            eavg_sgp30_co2.update(co2eq_1)
            last_sgp30_co2 = co2eq_1
            valid_cnt += 1

        if tvoc:
            last_sgp30_tvoc = tvoc
            eavg_sgp30_tvoc.update(tvoc)

        if HAS_CCS811 and last_ccs811_co2:
            valid_cnt += 1

        co2eq = eavg.update((last_sgp30_co2 + last_ccs811_co2) / valid_cnt) if valid_cnt else 0.0
    except Exception as e:
        print(f'SGP30 err: {e}')
        continue

    try:
        if HAS_SCD4X and scd4x.data_ready:
            scd40_co2, scd40_temp, scd40_hum = scd4x.CO2, scd4x.temperature, scd4x.relative_humidity
    except Exception as e:
        print(f'Err SDC40: {e}')

    print(
        f"CO2eq: {dval(co2eq):4.1f} (r={dval(co2eq_1):4d}) ppm, TVOC: {dval(tvoc):4d} ppb, "
        f"CCS CO2: {dval(ccs_co2):4d} ({dval(eavg_css811_co2.cur):4.1f}), "
        f"TVOC2: {dval(ccs_tvoc):3d} ({dval(eavg_css811_tvoc.cur):3.1f}), "
        f"Eth: {dval(eth):5d}, H2: {h2:5d}, {dval(temp):4.2f} C, {dval(humd):4.2f} %%, "
        f"SCD40: {dval(scd40_co2):4.2f}, {dval(scd40_temp):4.2f} C, {dval(scd40_hum):4.2f} %% "
    )

    if t - last_pub > 60:
        try:
            if HAS_SGP30:
                print(client.publish(f"sensors/sgp30{MQTT_SENSOR_SUFFIX}", json.dumps(
                    {'eCO2': co2eq, 'TVOC': tvoc, 'Eth': eth, 'H2': h2, 'temp': temp, 'humidity': humd})))

                print(client.publish(f"sensors/sgp30_raw{MQTT_SENSOR_SUFFIX}", json.dumps(
                    {'eCO2': last_sgp30_co2, 'TVOC': last_sgp30_tvoc})))

                print(client.publish(f"sensors/sgp30_filt{MQTT_SENSOR_SUFFIX}", json.dumps(
                    {'eCO2': eavg_sgp30_co2.cur, 'TVOC': eavg_sgp30_tvoc.cur})))

            if HAS_CCS811:
                print(client.publish(f"sensors/ccs811_raw{MQTT_SENSOR_SUFFIX}", json.dumps(
                    {'eCO2': last_ccs811_co2, 'TVOC': last_ccs811_tvoc})))

                print(client.publish(f"sensors/ccs811_filt{MQTT_SENSOR_SUFFIX}", json.dumps(
                    {'eCO2': eavg_css811_co2.cur, 'TVOC': eavg_css811_tvoc.cur})))

            last_pub = t
        except Exception as e:
            print(f'Error in pub: {e}')

    if HAS_SCD4X and t - last_pub_sgp > 60 and scd40_co2 is not None and scd40_co2 > 0:
        try:
            print(client.publish(f"sensors/scd40{MQTT_SENSOR_SUFFIX}", json.dumps(
                {'eCO2': scd40_co2, 'temp': scd40_temp, 'humidity': scd40_hum})))

            last_pub_sgp = t
        except Exception as e:
            print(f'Error in pub: {e}')

    time.sleep(1)
