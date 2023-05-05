import time
from typing import Optional

import board  # adafruit-blinka
import busio
import json
import adafruit_sgp30  # adafruit-circuitpython-sgp30
import adafruit_ahtx0  # adafruit-circuitpython-ahtx0
import adafruit_ccs811  # adafruit-circuitpython-ccs811
import adafruit_scd4x  # adafruit-circuitpython-scd4x
import paho.mqtt.client as mqtt  # paho-mqtt


class ExpAverage:
    def __init__(self, alpha):
        self.alpha = alpha
        self.average = None

    def update(self, value):
        if self.average is None:
            self.average = value
        else:
            self.average = self.alpha * value + (1 - self.alpha) * self.average
        return self.average


class CCS811Custom(adafruit_ccs811.CCS811):
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

    def reset_r(self):
        self.r_status = None
        self.r_error_id = None
        self.r_raw_data = None
        self.r_raw_current = None
        self.r_raw_adc = None
        self.r_err_str = ''
        self.r_stat_str = ''
        self.r_error = None

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
            self._eco2 = (buf[1] << 8) | (buf[2])
            self._tvoc = (buf[3] << 8) | (buf[4])
            self.r_status = buf[5]
            self.r_error_id = buf[6]
            self.r_raw_data = buf[7:9]
            self.r_raw_current = int((buf[7] & (~0x3)) >> 2)
            self.r_raw_adc = (1.65/1023) * (int(buf[7] & 0x3) << 8 | int(buf[8]))
            self.r_err_str = CCS811Custom.err_to_str(self.r_error_id)

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
                raise RuntimeError("Error:" + str(self.r_error))

            return self._eco2, self._tvoc

        return None, None


def try_fnc(x, msg=None):
    try:
        return x()
    except Exception as e:
        print(f'Err {msg or ""}: {e}')


# Initialize I2C bus
# i2c = busio.I2C(board.SCL7, board.SDA7)
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize sensors
sgp30 = adafruit_sgp30.Adafruit_SGP30(i2c)
aht21 = adafruit_ahtx0.AHTx0(i2c)
ccs811 = CCS811Custom(i2c)
scd4x = adafruit_scd4x.SCD4X(i2c)

# Initialize sensor measurements
co2eq = 0
tvoc = 0

client = mqtt.Client("SGP30_sensor_office")
client.connect("10.0.1.103", 1883)

# Measure air quality
sgp30.set_iaq_relative_humidity(21, 0.45)
sgp30.set_iaq_baseline(0x8973, 0x8aae)
sgp30.iaq_init()
eavg = ExpAverage(0.1)
scd4x.start_periodic_measurement()
# ccs811.drive_mode = adafruit_ccs811.DRIVE_MODE_250MS
# ccs811.drive_mode = adafruit_ccs811.DRIVE_MODE_10SEC

last_ccs811_co2 = 0
last_ccs811_tvoc = 0
last_spg30_co2 = 0
last_spg30_tvoc = 0

last_pub = time.time() + 30
last_pub_spg = time.time() + 30
scd40_co2, scd40_temp, scd40_hum = None, None, None
while True:
    t = time.time()
    temp = None
    humd = None
    try:
        temp = try_fnc(lambda: aht21.temperature)
        humd = try_fnc(lambda: aht21.relative_humidity)
        if temp and humd and time.time() - last_pub > 3600:
            try_fnc(lambda: sgp30.set_iaq_relative_humidity(temp, humd))
            try_fnc(lambda: ccs811.set_environmental_data(int(humd), temp))
            print(f'Temp sync')

    except Exception as e:
        print(f'E: exc in temp {e}')

    try:
        sgp30.iaq_measure()
    except Exception as e:
        print(f'Exception measurement: {e}')
        time.sleep(1)
        continue

    ccs_co2, ccs_tvoc = 0, 0
    try:
        nccs_co2, nccs_tvoc = ccs811.read_data()
        inv_ctr = 0

        if nccs_co2 and 100 < nccs_co2 < 30_000:
            last_ccs811_co2 = ccs_co2 = nccs_co2
        else:
            inv_ctr += 1

        if nccs_tvoc and 0 <= nccs_tvoc < 30_000:
            last_ccs811_tvoc = ccs_tvoc = nccs_tvoc
        else:
            inv_ctr += 1

        if inv_ctr:
            print(f'  CCS inv read, orig ({nccs_co2}, {nccs_tvoc}), status: {ccs811.r_status}, '
                  f'error id: {ccs811.r_error_id} = [{ccs811.r_err_str}] [{ccs811.r_stat_str}], '
                  f'raw I={ccs811.r_raw_current} uA, U={ccs811.r_raw_adc} V, Fw: {ccs811.fw_mode} Dm: {ccs811.drive_mode}')

        if ccs811.error:
            print(f'Err: {ccs811.r_error} = {CCS811Custom.err_to_str(ccs811.r_error)}')
    except Exception as e:
        print(f'CCS error: {e}')

    try:
        valid_cnt = 0
        co2eq_1, tvoc, eth, h2 = sgp30.eCO2, sgp30.TVOC, sgp30.Ethanol, sgp30.H2
        if co2eq_1:
            last_spg30_co2 = co2eq_1
            valid_cnt += 1
        if tvoc:
            last_spg30_tvoc = tvoc
        if last_ccs811_co2:
            valid_cnt += 1

        co2eq = eavg.update((last_spg30_co2 + last_ccs811_co2) / valid_cnt) if valid_cnt else 0
    except Exception as e:
        print(f'SPG30 err: {e}')
        continue

    if scd4x.data_ready:
        try:
            scd40_co2, scd40_temp, scd40_hum = scd4x.CO2, scd4x.temperature, scd4x.relative_humidity
        except Exception as e:
            print(f'Err SDC40: {e}')

    print(
        "CO2eq: %4d (%4d) ppm, TVOC: %4d ppb, CO2: %4d, TVOC2: %4d, Eth: %5d, H2: %5d, %4.2f C, humd: %4.2f%%, SCD40: %4.2f, %4.2f C, %4.2f%%" % (
            co2eq, co2eq_1, tvoc, ccs_co2, ccs_tvoc, eth, h2, temp or -1, humd or -1, scd40_co2 or -1, scd40_temp or -1,
            scd40_hum or -1))

    if t - last_pub > 60:
        try:
            print(client.publish("sensors/sgp30_office", json.dumps(
                {'eCO2': co2eq, 'TVOC': tvoc, 'Eth': eth, 'H2': h2, 'temp': temp, 'humidity': humd})))

            print(client.publish("sensors/sgp30_raw_office", json.dumps(
                {'eCO2': last_spg30_co2, 'TVOC': last_spg30_tvoc})))

            print(client.publish("sensors/ccs811_raw_office", json.dumps(
                {'eCO2': last_ccs811_co2, 'TVOC': last_ccs811_tvoc})))

            last_pub = t
        except Exception as e:
            print(f'Error in pub: {e}')

    if t - last_pub_spg > 60 and scd40_co2 is not None and scd40_co2 > 0:
        try:
            print(client.publish("sensors/scd40_office", json.dumps(
                {'eCO2': scd40_co2, 'temp': scd40_temp, 'humidity': scd40_hum})))

            last_pub_spg = t
        except Exception as e:
            print(f'Error in pub: {e}')

    time.sleep(1)
