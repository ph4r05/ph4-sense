from ph4_sense.adapters import getLogger, json, mem_stats, sleep_ms, time
from ph4_sense.filters import ExpAverage, SensorFilter
from ph4_sense.sensors.common import ccs811_err_to_str
from ph4_sense.support.sensor_helper import SensorHelper
from ph4_sense.udplogger import UdpLogger
from ph4_sense.utils import dval, try_fnc

try:
    from typing import List
except ImportError:
    pass


class Sensei:
    def __init__(
        self,
        is_esp32=True,
        has_wifi=True,
        has_aht=True,
        has_sgp30=True,
        has_ccs811=True,
        has_scd4x=True,
        has_sps30=False,
        has_hdc1080=False,
        has_zh03b=False,
        has_sgp41=False,
        scl_pin=22,
        sda_pin=21,
    ):
        self.is_esp32 = is_esp32
        self.has_wifi = has_wifi
        self.has_aht = has_aht
        self.has_sgp30 = has_sgp30
        self.has_ccs811 = has_ccs811
        self.has_scd4x = has_scd4x
        self.has_sps30 = has_sps30
        self.has_hdc1080 = has_hdc1080
        self.has_zh03b = has_zh03b
        self.has_sgp41 = has_sgp41
        self.scl_pin = scl_pin
        self.sda_pin = sda_pin
        self.sps30_uart = None
        self.zh03b_uart = None

        self.wifi_ssid = None
        self.wifi_passphrase = None

        self.has_mqtt = False
        self.mqtt_broker = None
        self.mqtt_port = 1883
        self.mqtt_sensor_id = None
        self.mqtt_sensor_suffix = None
        self.mqtt_topic_sub = None
        self.mqtt_topic = None
        self.set_sensor_id("bed")

        self.sgp30_co2eq = 0
        self.sgp30_tvoc = 0
        self.eth = 0
        self.h2 = 0
        self.temp = 0
        self.humd = 0
        self.ccs_co2 = 0
        self.ccs_tvoc = 0
        self.eavg = ExpAverage(0.1)
        self.eavg_css811_co2 = SensorFilter(median_window=9, alpha=0.2)
        self.eavg_sgp30_co2 = SensorFilter(median_window=5, alpha=0.2)
        self.eavg_css811_tvoc = SensorFilter(median_window=9, alpha=0.2)
        self.eavg_sgp30_tvoc = SensorFilter(median_window=5, alpha=0.2)
        self.sgp41_filter_voc = None
        self.sgp41_filter_nox = None
        self.sgp41_sraw_voc = None
        self.sgp41_sraw_nox = None

        self.last_ccs811_co2 = 0
        self.last_ccs811_tvoc = 0
        self.last_sgp30_co2 = 0
        self.last_sgp30_tvoc = 0
        self.scd40_co2 = None
        self.scd40_temp = None
        self.scd40_hum = None
        self.sps30_data = None
        self.zh03b_data = None

        self.reconnect_attempts = 40
        self.reconnect_timeout = 500
        self.measure_attempts = 5
        self.measure_timeout = 150
        self.measure_loop_ms = 2_000
        self.temp_sync_timeout = 180
        self.mqtt_reconnect_timeout = 60 * 3
        self.wifi_reconnect_timeout = 60 * 3
        self.readings_publish_timeout = 60

        self.last_tsync = 0
        self.last_pub = time.time() + 30
        self.last_pub_sgp = time.time() + 30
        self.last_reconnect = time.time()
        self.last_wifi_reconnect = 0

        self.i2c = None
        self.sta_if = None
        self.mqtt_client = None
        self.udp_logger = None
        self.sgp30 = None
        self.sgp41 = None
        self.aht21 = None
        self.ccs811 = None
        self.scd4x = None
        self.sps30 = None
        self.hdc1080 = None
        self.zh03b = None
        self.logger = None
        self.sensor_helper = None

    def set_sensor_id(self, sensor_id):
        self.mqtt_sensor_id = sensor_id or ""
        self.mqtt_sensor_suffix = f"_{self.mqtt_sensor_id}" if self.mqtt_sensor_id else ""
        self.mqtt_topic_sub = f"sensors/esp32_{self.mqtt_sensor_id}_sub"
        self.mqtt_topic = f"sensors/esp32_{self.mqtt_sensor_id}_gas"

    def get_sensor_helper(self) -> SensorHelper:
        if not self.sensor_helper:
            self.sensor_helper = SensorHelper(logger=self.logger)

        return self.sensor_helper

    def load_config_data(self):
        with open("config.json") as fh:
            return json.load(fh)

    def load_config(self):
        js = self.load_config_data()
        if "wifi" in js:
            self.wifi_ssid = js["wifi"]["ssid"]
            self.wifi_passphrase = js["wifi"]["passphrase"]
            self.has_wifi = True

        if "mqtt" in js:
            self.mqtt_broker = js["mqtt"]["host"]
            self.has_mqtt = True

        if "udpLogger" in js:
            self.udp_logger = UdpLogger(js["udpLogger"], is_esp32=self.is_esp32)

        if "sensorId" in js:
            self.set_sensor_id(js["sensorId"])

        if "sensors" in js:
            self.load_config_sensors(js["sensors"])

        if "sps30_uart" in js:
            self.sps30_uart = js["sps30_uart"]

        if "zh03b_uart" in js:
            self.zh03b_uart = js["zh03b_uart"]  # {"type": "uart", "tx":  17, "rx": 16}

    def load_config_sensors(self, sensors: List[str]):
        self.has_aht = False
        self.has_sgp30 = False
        self.has_ccs811 = False
        self.has_scd4x = False
        self.has_sps30 = False
        self.has_hdc1080 = False
        self.has_zh03b = False
        self.has_sgp41 = False

        for sensor in sensors:
            sensor = sensor.lower()
            if sensor in ("sgp30", "spg30"):
                self.has_sgp30 = True
            elif sensor in ("aht", "ahtx0", "aht21"):
                self.has_aht = True
            elif sensor in ("ccs811", "ccs"):
                self.has_ccs811 = True
            elif sensor in ("scd4x", "scd41", "scd40"):
                self.has_scd4x = True
            elif sensor in ("sps30",):
                self.has_sps30 = True
            elif sensor in ("hdc1080",):
                self.has_hdc1080 = True
            elif sensor in ("zh03b",):
                self.has_zh03b = True
            elif sensor in ("sgp41", "spg41"):
                self.has_sgp41 = True

    def print(self, msg, *args):
        self.print_cli(msg, *args)
        self.print_logger(msg, *args)

    def print_cli(self, msg, *args):
        print(msg, *args)

    def print_logger(self, msg, *args):
        if self.udp_logger:
            self.udp_logger.log_msg(msg, *args)

    def mqtt_callback(self, topic=None, msg=None):
        self.print("Received MQTT message:", topic, msg)

    def connect_wifi(self, force=False):
        if not self.has_wifi:
            return
        raise NotImplementedError

    def check_wifi_ok(self):
        if not self.has_wifi:
            return
        raise NotImplementedError

    def create_mqtt_client(self):
        raise NotImplementedError

    def connect_mqtt(self):
        self.mqtt_client = self.create_mqtt_client()

    def get_uart_builder(self, desc):
        raise NotImplementedError

    def try_measure(self, fnc):
        for attempt in range(self.measure_attempts):
            try:
                return fnc()
            except Exception as e:
                if attempt + 1 >= self.measure_attempts:
                    self.logger.error(f"Could not measure sensor {fnc}, attempt {attempt}: {e}")
                    raise
                else:
                    self.logger.warn(f"Could not measure sensor {fnc}, attempt {attempt}: {e}")
                    sleep_ms(self.measure_timeout)

    def connect_sgp30(self):
        if not self.has_sgp30:
            return

        self.print(" - Connecting SGP30")
        from ph4_sense.sensors.sgp30 import sgp30_factory

        self.sgp30 = sgp30_factory(self.i2c, measure_test=True, iaq_init=False, sensor_helper=self.get_sensor_helper())
        if self.sgp30:
            # self.sgp30.set_iaq_baseline(0x8973, 0x8AAE)
            self.sgp30.set_iaq_relative_humidity(26, 45)
            self.sgp30.iaq_init()
        else:
            self.print("SGP30 not connected")
        self.log_memory()

    def connect_sgp41(self):
        if not self.has_sgp41:
            return

        self.print(" - Connecting SGP41")
        from ph4_sense.sensirion import NoxGasIndexAlgorithm, VocGasIndexAlgorithm
        from ph4_sense.sensors.sgp41 import sgp41_factory

        self.sgp41 = sgp41_factory(self.i2c, measure_test=True, iaq_init=True, sensor_helper=self.get_sensor_helper())
        if self.sgp41:
            self.sgp41_filter_voc = VocGasIndexAlgorithm(sampling_interval=self.measure_loop_ms / 1000.0)
            self.sgp41_filter_nox = NoxGasIndexAlgorithm(sampling_interval=self.measure_loop_ms / 1000.0)
        else:
            self.print("SGP41 not connected")
        self.log_memory()

    def connect_aht(self):
        if not self.has_aht:
            return

        self.print("\n - Connecting AHT21")
        from ph4_sense.sensors.athx0 import ahtx0_factory

        self.aht21 = ahtx0_factory(self.i2c, sensor_helper=self.get_sensor_helper())
        if not self.aht21:
            self.print("AHT21 not connected")
        self.log_memory()

    def connect_hdc1080(self):
        if not self.has_hdc1080:
            return
        self.print("\n - Connecting HDC1080")
        from ph4_sense.sensors.hdc1080 import hdc1080_factory

        self.hdc1080 = hdc1080_factory(self.i2c, sensor_helper=self.get_sensor_helper())
        if not self.hdc1080:
            self.print("HDC1080 not connected")
        self.log_memory()

    def connect_ccs811(self):
        if not self.has_ccs811:
            return

        self.print("\n - Connecting CCS811")
        from ph4_sense.sensors.ccs811 import css811_factory

        self.ccs811 = css811_factory(self.i2c, sensor_helper=self.get_sensor_helper())
        if self.ccs811:
            pass
        else:
            self.print("CCS811 not connected")
        self.log_memory()

    def connect_scd4x(self):
        if not self.has_scd4x:
            return

        self.print("\n - Connecting SCD40")
        from ph4_sense.sensors.scd4x import scd4x_factory

        self.scd4x = scd4x_factory(self.i2c, sensor_helper=self.get_sensor_helper())
        if self.scd4x:
            self.scd4x.start_periodic_measurement()
        else:
            self.print("SCD4x not connected")
        self.log_memory()

    def connect_sps30(self):
        if not self.has_sps30:
            return

        self.print("\n - Connecting SPS30")
        if self.sps30_uart:
            from ph4_sense_py.sensors.sps30_uart_ada import SPS30AdaUart

            self.sps30 = SPS30AdaUart(self.sps30_uart, sensor_helper=self.get_sensor_helper())
            self.sps30.start()
        else:
            from ph4_sense.sensors.sps30 import sps30_factory

            self.sps30 = sps30_factory(self.i2c, sensor_helper=self.get_sensor_helper())

        if self.sps30:
            pass
        else:
            self.print("SPS30 not connected")
        self.log_memory()

    def connect_zh03b(self):
        if not self.has_zh03b:
            return

        self.print("\n - Connecting ZH03b")
        if self.zh03b_uart:
            from ph4_sense.sensors.zh03b_uart_base import Zh03bUartBase

            self.zh03b = Zh03bUartBase(
                None, uart_builder=self.get_uart_builder(self.zh03b_uart), sensor_helper=self.get_sensor_helper()
            )
            self.zh03b.dormant_mode(to_dormant=False)
            self.zh03b.set_qa()
        else:
            self.print("ZH03b uart is required")

        if self.zh03b:
            pass
        else:
            self.print("ZH03b not connected")
        self.log_memory()

    def try_connect_sensor(self, fnc):
        for attempt in range(self.reconnect_attempts):
            try:
                return fnc()
            except Exception as e:
                if attempt + 1 >= self.reconnect_attempts:
                    self.logger.error(f"Could not connect sensor {fnc}, attempt {attempt}: {e}")
                    raise
                else:
                    self.logger.warn(f"Could not connect sensor {fnc}, attempt {attempt}: {e}")
                    sleep_ms(self.reconnect_timeout)

    def connect_sensors(self):
        self.print("\nConnecting sensors")
        try:
            self.try_connect_sensor(self.connect_sgp30)
            self.try_connect_sensor(self.connect_sgp41)
            self.try_connect_sensor(self.connect_aht)
            self.try_connect_sensor(self.connect_hdc1080)
            self.try_connect_sensor(self.connect_ccs811)
            self.try_connect_sensor(self.connect_scd4x)
            self.try_connect_sensor(self.connect_sps30)
            self.try_connect_sensor(self.connect_zh03b)

            self.print("\nSensors connected")
        except Exception as e:
            self.print("Exception in sensor init: ", e)
            self.logger.debug("Exception in sensor init: {}".format(e), exc_info=e)
            raise

    def measure_temperature(self):
        if not self.aht21 and not self.hdc1080:
            return

        try:
            cal_temp = self.scd40_temp
            cal_hum = self.scd40_hum

            if self.aht21:
                self.temp, self.humd = try_fnc(lambda: self.aht21.read_temperature_humidity())
            else:
                self.temp, self.humd = try_fnc(lambda: self.hdc1080.measurements)

            if not cal_temp or not cal_hum:
                cal_temp = self.temp
                cal_hum = self.humd

            self.calibrate_temps(cal_temp, cal_hum)

        except Exception as e:
            self.print("E: exc in temp", e)
            self.logger.debug("Temp exception err: {}".format(e), exc_info=e)

    def calibrate_temps(self, cal_temp, cal_hum):
        if cal_temp and cal_hum and time.time() - self.last_tsync > self.temp_sync_timeout:
            if self.sgp30:
                try_fnc(lambda: self.sgp30.set_iaq_relative_humidity(cal_temp, cal_hum))
                pass

            if self.ccs811:
                # try_fnc(lambda: self.ccs811.set_environmental_data(cal_hum, cal_temp))
                pass

            self.last_tsync = time.time()
            self.print("Temp sync", cal_temp, cal_hum)

    def measure_sqp30(self):
        if not self.sgp30:
            return

        try:
            self.sgp30_co2eq, self.sgp30_tvoc = self.sgp30.co2eq_tvoc()
            self.h2, self.eth = self.sgp30.raw_h2_ethanol()

            if self.sgp30_co2eq:
                self.last_sgp30_co2 = self.sgp30_co2eq
                self.eavg_sgp30_co2.update(self.sgp30_co2eq)

            if self.sgp30_tvoc:
                self.last_sgp30_tvoc = self.sgp30_tvoc
                self.eavg_sgp30_tvoc.update(self.sgp30_tvoc)

        except Exception as e:
            self.print("SGP30 err:", e)
            self.logger.error("SGP30 err: {}".format(e))
            self.logger.debug("SGP30 err: {}".format(e), exc_info=e)
            return

    def measure_sqp41(self):
        if not self.sgp41:
            return

        try:
            self.sgp41_sraw_voc, self.sgp41_sraw_nox = self.sgp41.measure_raw(self.humd, self.temp)
            self.sgp41_filter_voc.process(self.sgp41_sraw_voc)
            self.sgp41_filter_nox.process(self.sgp41_sraw_nox)

        except Exception as e:
            self.print("SGP41 err:", e)
            self.logger.error("SGP41 err: {}".format(e))
            self.logger.debug("SGP41 err: {}".format(e), exc_info=e)
            return

    def measure_ccs811(self):
        if not self.ccs811:
            return

        self.ccs_co2 = 0
        self.ccs_tvoc = 0
        try:
            if self.ccs811.get_fw_mode() != 1:
                self.print("CCS811 Not in App mode! Rebooting")
                self.ccs811.reboot_to_mode()
                return

            nccs_co2, nccs_tvoc = self.ccs811.read_data()
            inv_ctr = 0

            if nccs_co2 is not None and 400 <= nccs_co2 < 30_000:
                self.last_ccs811_co2 = self.ccs_co2 = nccs_co2
                self.eavg_css811_co2.update(nccs_co2)
            else:
                inv_ctr += 1

            if nccs_tvoc is not None and 0 <= nccs_tvoc < 30_000:
                self.last_ccs811_tvoc = self.ccs_tvoc = nccs_tvoc
                self.eavg_css811_tvoc.update(nccs_tvoc)
            else:
                inv_ctr += 1

            if inv_ctr or self.ccs811.r_overflow:
                flg = (nccs_co2 or 0) & ~0x8000
                raise RuntimeError(f"CCS overflow {inv_ctr}, flg: {flg}, orig co2: {nccs_co2}, tvoc: {nccs_tvoc}")

            if self.ccs811.r_error:
                self.print(
                    f"CCS811 logical-err: {self.ccs811.r_error_code} = {ccs811_err_to_str(self.ccs811.r_error_code)}"
                )
        except Exception as e:
            self.print("CCS error: ", e)
            try:
                self.print(
                    f"  CCS err, orig ({self.ccs811.r_orig_co2}, "
                    + f"{self.ccs811.r_orig_tvoc}), "
                    + f"status: {self.ccs811.r_status}, "
                    + f"error id: {self.ccs811.r_error_id} = [{self.ccs811.r_err_str}] [{self.ccs811.r_stat_str}], "
                    + f"raw I={self.ccs811.r_raw_current} uA, U={dval(self.ccs811.r_raw_adc):.5f} V, "
                    + f"Fw: {int(dval(self.ccs811.get_fw_mode()))} Dm: {self.ccs811.get_drive_mode()}"
                )
            except Exception:
                pass

            self.logger.error("CCS err: {}".format(e))
            self.logger.debug("CCS err: {}".format(e), exc_info=e)
            return

    def measure_scd4x(self):
        if not self.scd4x:
            return
        try:
            if self.scd4x.data_ready:
                self.scd40_co2 = self.scd4x.CO2
                self.scd40_temp = self.scd4x.temperature
                self.scd40_hum = self.scd4x.relative_humidity
        except Exception as e:
            self.print("Err SDC40: ", e)
            self.logger.error("SDC40 err: {}".format(e))
            self.logger.debug("SDC40 err: {}".format(e), exc_info=e)
            return

    def measure_sps30(self):
        if not self.has_sps30 or not self.sps30:
            return

        def sps30_measure_body():
            if self.sps30.data_available:
                self.sps30_data = self.sps30.read()

        try:
            self.try_measure(sps30_measure_body)

        except Exception as e:
            self.print("Err SPS30: ", e)
            self.logger.error("SPS30 err: {}".format(e))
            self.logger.debug("SPS30 err: {}".format(e), exc_info=e)
            return

    def measure_zh03b(self):
        if not self.has_zh03b or not self.zh03b:
            return

        try:
            reading = self.zh03b.qa_read_sample()
            if reading is None:
                return

            self.zh03b_data = reading
            self.print("ZH03b data {}".format(self.zh03b_data))

        except Exception as e:
            self.print("Err ZH03b: ", e)
            self.logger.error("ZH03b err: {}".format(e))
            self.logger.debug("ZH03b err: {}".format(e), exc_info=e)
            return

    def update_metrics(self):
        pass

    def publish_booted(self):
        self.publish_payload(
            f"sensors/esp32{self.mqtt_sensor_suffix}",
            {
                "booted": True,
            },
        )

    def publish(self):
        self.publish_common()
        self.publish_co2()

    def publish_common(self):
        t = time.time()
        if t - self.last_pub <= self.readings_publish_timeout:
            return

        try:
            self.check_wifi_ok()
            self.maybe_reconnect_mqtt()
            self.publish_sgp30()
            self.publish_sgp41()
            self.publish_ccs811()
            self.publish_sps30()
            self.publish_zh03b()
            self.last_pub = t
        except Exception as e:
            self.print("Error in pub:", e)

    def publish_co2(self):
        if not self.scd4x:
            return

        t = time.time()
        if t - self.last_pub_sgp > self.readings_publish_timeout and self.scd40_co2 is not None and self.scd40_co2 > 0:
            try:
                self.publish_scd40()
                self.last_pub_sgp = t
            except Exception as e:
                self.print("Error in pub:", e)

    def publish_msg(self, topic: str, message: str):
        raise NotImplementedError

    def publish_payload(self, topic: str, payload: dict):
        self.publish_msg(topic, json.dumps(payload))

    def publish_sgp30(self):
        if not self.sgp30:
            return

        self.publish_payload(
            f"sensors/sgp30{self.mqtt_sensor_suffix}",
            {
                "eCO2": self.eavg_sgp30_co2.cur,
                "TVOC": self.eavg_sgp30_tvoc.cur,
                "Eth": self.eth,
                "H2": self.h2,
                "temp": self.temp,
                "humidity": self.humd,
            },
        )

        self.publish_payload(
            f"sensors/sgp30_raw{self.mqtt_sensor_suffix}",
            {"eCO2": self.last_sgp30_co2, "TVOC": self.last_sgp30_tvoc},
        )

        self.publish_payload(
            f"sensors/sgp30_filt{self.mqtt_sensor_suffix}",
            {
                "eCO2": self.eavg_sgp30_co2.cur,
                "TVOC": self.eavg_sgp30_tvoc.cur,
            },
        )

    def publish_sgp41(self):
        if not self.sgp41:
            return

        self.publish_payload(
            f"sensors/sgp41{self.mqtt_sensor_suffix}",
            {
                "NOX": self.sgp41_filter_nox.get_gas_index(),
                "TVOC": self.sgp41_filter_voc.get_gas_index(),
                "sraw_voc": self.sgp41_sraw_voc,
                "sraw_nox": self.sgp41_sraw_nox,
                "temp": self.temp,
                "humidity": self.humd,
            },
        )

    def publish_ccs811(self):
        if not self.ccs811:
            return

        self.publish_payload(
            f"sensors/ccs811_raw{self.mqtt_sensor_suffix}",
            {
                "eCO2": self.last_ccs811_co2,
                "TVOC": self.last_ccs811_tvoc,
            },
        )

        self.publish_payload(
            f"sensors/ccs811_filt{self.mqtt_sensor_suffix}",
            {
                "eCO2": self.eavg_css811_co2.cur,
                "TVOC": self.eavg_css811_tvoc.cur,
            },
        )

    def publish_scd40(self):
        if not self.scd4x:
            return

        self.publish_payload(
            f"sensors/scd40{self.mqtt_sensor_suffix}",
            {
                "eCO2": self.scd40_co2,
                "temp": self.scd40_temp,
                "humidity": self.scd40_hum,
            },
        )

    def publish_sps30(self):
        if not self.sps30 or not self.sps30_data:
            return

        self.publish_payload(f"sensors/sps30{self.mqtt_sensor_suffix}", self.sps30_data)

    def publish_zh03b(self):
        if not self.zh03b or not self.zh03b_data or len(self.zh03b_data) < 3:
            return

        self.publish_payload(
            f"sensors/zh03b{self.mqtt_sensor_suffix}",
            {
                "pm10": self.zh03b_data[0],
                "pm25": self.zh03b_data[1],
                "pm100": self.zh03b_data[2],
            },
        )

    def on_wifi_reconnect(self):
        self.print("WiFi Reconnecting")
        self.connect_wifi(force=True)
        self.maybe_reconnect_mqtt(force=True)

    def maybe_reconnect_mqtt(self, force=False):
        t = time.time()

        if not force and (self.mqtt_client is not None and t - self.last_reconnect < self.mqtt_reconnect_timeout):
            return

        if self.mqtt_client:
            try_fnc(lambda: self.mqtt_client.disconnect())
            sleep_ms(1000)

        try:
            self.connect_mqtt()
            self.last_reconnect = t
        except Exception as e:
            self.print("MQTT connection error:", e)

    def start_bus(self):
        raise NotImplementedError

    def measure_loop_body(self):
        self.measure_temperature()
        self.measure_sqp30()
        self.measure_sqp41()
        self.measure_ccs811()
        self.measure_scd4x()
        self.measure_sps30()
        self.measure_zh03b()
        self.update_metrics()

        msg = self.combine_sensor_log()
        self.print(msg)
        self.publish()

    def combine_sensor_log(self):
        res = []
        if self.has_sgp30:
            res.append(
                f"CO2eq: {dval(self.sgp30_co2eq):4.1f} (r={dval(self.eavg_sgp30_co2.cur):4.1f}) ppm, "
                f"TVOC: {dval(self.sgp30_tvoc):4d} ppb"
            )

        if self.has_sgp41 and self.sgp41_filter_voc is not None:
            res.append(
                f"SGP41: {dval(self.sgp41_filter_voc.get_gas_index()):4d} (r={dval(self.sgp41_sraw_voc):5d}), "
                f"NOX: {dval(self.sgp41_filter_nox.get_gas_index()):4d} (r={dval(self.sgp41_sraw_nox):5d})"
            )

        if self.has_ccs811 and self.ccs_co2 is not None and self.eavg_css811_co2 is not None:
            res.append(
                f"CCS CO2: {dval(self.ccs_co2):4d} ({dval(self.eavg_css811_co2.cur):4.1f}), "
                f"TVOC2: {dval(self.ccs_tvoc):3d} ({dval(self.eavg_css811_tvoc.cur):3.1f})"
            )

        if self.has_sgp30 and self.eth is not None:
            res.append(f"Eth: {dval(self.eth):5d}, H2: {self.h2:5d}")

        if self.temp is not None:
            res.append(f"{dval(self.temp):4.2f} C, {dval(self.humd):4.2f} %%")

        if self.has_scd4x:
            res.append(
                f"SCD40: {dval(self.scd40_co2):4.2f}, {dval(self.scd40_temp):4.2f} C, {dval(self.scd40_hum):4.2f} %% "
            )

        if self.has_sps30 and self.sps30_data:
            res.append(f"SPS30: {self.sps30_data}")

        return ", ".join(res)

    def log_memory(self):
        stats = mem_stats()
        self.print("Memory alloc {}, free {}".format(stats[0], stats[1]))

    def base_init(self):
        self.logger = getLogger(__name__)

    def init_connections(self):
        self.base_init()
        self.log_memory()

        print("Starting bus")
        self.start_bus()
        self.log_memory()

        print("Loading config")
        self.load_config()
        self.log_memory()

        print("\nConnecting WiFi")
        self.connect_wifi()
        self.log_memory()

        self.print("\nConnecting MQTT")
        self.connect_mqtt()
        self.log_memory()

        self.connect_sensors()
        self.log_memory()

        self.publish_booted()
        self.log_memory()

    def main(self):
        self.init_connections()

        while True:
            self.maybe_reconnect_mqtt()
            self.measure_loop_body()
            sleep_ms(self.measure_loop_ms)


def main():
    sensei = Sensei()
    sensei.main()


# Run the main program
if __name__ == "__main__":
    main()
