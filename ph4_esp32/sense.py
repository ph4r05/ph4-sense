import machine
import utime
import ujson as json
from umqtt.robust import MQTTClient
from utime import sleep_ms

from athx0 import AHTx0
from ccs811 import CCS811Custom
from scd4x import SCD4X
from spg30 import SGP30
from utils import try_fnc, dval
from filters import ExpAverage, SensorFilter

HAS_AHT = True
HAS_SGP30 = True
HAS_CCS811 = True
HAS_SCD4X = True

# Set up your SPG30 sensor pin connections
# https://randomnerdtutorials.com/esp32-i2c-communication-arduino-ide/
SPG30_SCL_PIN = 22
SPG30_SDA_PIN = 21


class Sensei:
    def __init__(self):
        self.wifi_ssid = None
        self.wifi_passphrase = None
        self.mqtt_broker = None
        self.mqtt_port = 1883
        self.mqtt_sensor_id = "bed"
        self.mqtt_sensor_suffix = f"_{self.mqtt_sensor_id}"
        self.mqtt_topic_sub = f"sensors/esp32_{self.mqtt_sensor_id}_sub"
        self.mqtt_topic = f"sensors/esp32_{self.mqtt_sensor_id}_gas"

        self.co2eq = 0
        self.co2eq_1 = 0
        self.tvoc = 0
        self.eth = 0
        self.h2 = 0
        self.temp = 0
        self.humd = 0
        self.ccs_co2 = 0
        self.ccs_tvoc = 0
        self.eavg = ExpAverage(0.1)
        self.eavg_css811_co2 = SensorFilter(median_window=7, alpha=0.2)
        self.eavg_sgp30_co2 = SensorFilter(median_window=5, alpha=0.2)
        self.eavg_css811_tvoc = SensorFilter(median_window=7, alpha=0.2)
        self.eavg_sgp30_tvoc = SensorFilter(median_window=5, alpha=0.2)

        self.last_ccs811_co2 = 0
        self.last_ccs811_tvoc = 0
        self.last_sgp30_co2 = 0
        self.last_sgp30_tvoc = 0
        self.last_tsync = 0
        self.scd40_co2 = None
        self.scd40_temp = None
        self.scd40_hum = None

        self.last_tsync = utime.time() + 60
        self.last_pub = utime.time() + 30
        self.last_pub_sgp = utime.time() + 30
        self.last_reconnect = utime.time()

        self.i2c = None
        self.sta_if = None
        self.mqtt_client = None
        self.sgp30 = None
        self.aht21 = None
        self.ccs811 = None
        self.scd4x = None

    def load_config(self):
        with open("config.json") as fh:
            js = json.load(fh)

        self.wifi_ssid = js["wifi"]["ssid"]
        self.wifi_passphrase = js["wifi"]["passphrase"]
        self.mqtt_broker = js["mqtt"]["host"]

    def mqtt_callback(self, topic, msg):
        print("Received MQTT message:", topic, msg)

    def connect_wifi(self):
        import network

        if not self.sta_if:
            self.sta_if = network.WLAN(network.STA_IF)
            self.sta_if.active(True)

        if not self.wifi_ssid:
            raise ValueError("WiFi is not configured")

        if not self.sta_if.isconnected():
            print("Not connected, scanning...")
            scan_res = self.sta_if.scan()
            if scan_res:
                for net in scan_res:
                    print(f" - ", net)

            print("Connecting to WiFi: " + self.wifi_ssid)
            self.sta_if.connect(self.wifi_ssid, self.wifi_passphrase)
            while not self.sta_if.isconnected():
                sleep_ms(500)

        print("WiFi connected:", self.sta_if.ifconfig())

    def connect_mqtt(self):
        # https://notebook.community/Wei1234c/Elastic_Network_of_Things_with_MQTT_and_MicroPython/notebooks/test/MQTT%20client%20test%20-%20MicroPython
        client = MQTTClient(
            f"esp32_client/{self.mqtt_sensor_id}",
            self.mqtt_broker,
            self.mqtt_port,
            keepalive=60,
            ssl=False,
            ssl_params={},
        )
        client.set_callback(self.mqtt_callback)
        client.connect()
        client.subscribe(self.mqtt_topic_sub)
        return client

    def connect_sensors(self):
        print("\nConnecting sensors")
        try:
            print(" - Connecting SGP30")
            self.sgp30 = SGP30(self.i2c) if HAS_SGP30 else None
            if HAS_SGP30:
                self.sgp30.set_iaq_relative_humidity(21, 0.45)
                self.sgp30.set_iaq_baseline(0x8973, 0x8AAE)
                self.sgp30.iaq_init()

            print("\n - Connecting AHT21")
            self.aht21 = AHTx0(self.i2c) if HAS_AHT else None

            print("\n - Connecting CCS811")
            self.ccs811 = CCS811Custom(self.i2c) if HAS_CCS811 else None

            print("\n - Connecting SCD40")
            self.scd4x = SCD4X(self.i2c) if HAS_SCD4X else None
            if HAS_SCD4X:
                self.scd4x.start_periodic_measurement()

            print("\n Sensors connected")
        except Exception as e:
            print("Exception in sensor init: ", e)
            raise

    def measure_temperature(self):
        if not HAS_AHT:
            return

        try:
            cal_temp = self.scd40_temp
            cal_hum = self.scd40_hum

            self.temp = try_fnc(lambda: self.aht21.temperature) if HAS_AHT else None
            self.humd = try_fnc(lambda: self.aht21.relative_humidity) if HAS_AHT else None
            if not cal_temp or not cal_hum:
                cal_temp = self.temp
                cal_hum = self.humd

            if cal_temp and cal_hum and utime.time() - self.last_tsync > 180:
                if HAS_SGP30:
                    try_fnc(lambda: self.sgp30.set_iaq_relative_humidity(cal_temp, cal_hum))
                if HAS_CCS811:
                    # try_fnc(lambda: self.ccs811.set_environmental_data(int(cal_hum), cal_temp))
                    pass

                self.last_tsync = utime.time()
                print("Temp sync", cal_temp, cal_hum)

        except Exception as e:
            print("E: exc in temp", e)

    def measure_sqp30(self):
        if not HAS_SGP30:
            return

        try:
            self.co2eq_1, self.tvoc = self.sgp30.co2eq_tvoc()
            self.h2, self.eth = self.sgp30.raw_h2_ethanol()

            if self.co2eq_1:
                self.eavg_sgp30_co2.update(self.co2eq_1)
                self.last_sgp30_co2 = self.co2eq_1

            if self.tvoc:
                self.last_sgp30_tvoc = self.tvoc
                self.eavg_sgp30_tvoc.update(self.tvoc)

        except Exception as e:
            print(f"SGP30 err:", e)
            return

    def measure_ccs811(self):
        if not HAS_CCS811:
            return

        self.ccs_co2 = 0
        self.ccs_tvoc = 0
        try:
            nccs_co2, nccs_tvoc = self.ccs811.read_data()
            inv_ctr = 0

            if nccs_co2 is not None and 400 < nccs_co2 < 30_000:
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
                print(
                    f"  CCS inv read {inv_ctr}, orig ({self.ccs811.r_orig_co2} {flg}, "
                    + f"{self.ccs811.r_orig_tvoc}), "
                    + f"status: {self.ccs811.r_status}, "
                    + f"error id: {self.ccs811.r_error_id} = [{self.ccs811.r_err_str}] [{self.ccs811.r_stat_str}], "
                    + f"raw I={self.ccs811.r_raw_current} uA, U={dval(self.ccs811.r_raw_adc):.5f} V, "
                    + f"Fw: {int(dval(self.ccs811.fw_mode.get()))} Dm: {self.ccs811.drive_mode.get()}"
                )

            if self.ccs811.error.get():
                print(f"Err: {self.ccs811.r_error} = {CCS811Custom.err_to_str(self.ccs811.r_error)}")
        except Exception as e:
            print(f"CCS error: ", e)
            raise

    def update_metrics(self):
        try:
            valid_cnt = 0
            if self.co2eq_1:
                valid_cnt += 1

            if HAS_CCS811 and self.last_ccs811_co2:
                valid_cnt += 1

            self.co2eq = (
                self.eavg.update((self.last_sgp30_co2 + self.last_ccs811_co2) / valid_cnt) if valid_cnt else 0.0
            )
        except Exception as e:
            print(f"Metrics update err:", e)
            return

    def measure_scd4x(self):
        if not HAS_SCD4X:
            return
        try:
            if self.scd4x.data_ready:
                self.scd40_co2 = self.scd4x.CO2
                self.scd40_temp = self.scd4x.temperature
                self.scd40_hum = self.scd4x.relative_humidity
        except Exception as e:
            print(f"Err SDC40: ", e)

    def publish_booted(self):
        self.mqtt_client.publish(
            f"sensors/esp32{self.mqtt_sensor_suffix}",
            json.dumps(
                {
                    "booted": True,
                }
            ),
        )

    def publish(self):
        t = utime.time()
        if t - self.last_pub <= 60:
            return

        try:
            self.maybe_reconnect_mqtt()
            if HAS_SGP30:
                print(
                    self.mqtt_client.publish(
                        f"sensors/sgp30{self.mqtt_sensor_suffix}",
                        json.dumps(
                            {
                                "eCO2": self.co2eq,
                                "TVOC": self.tvoc,
                                "Eth": self.eth,
                                "H2": self.h2,
                                "temp": self.temp,
                                "humidity": self.humd,
                            }
                        ),
                    )
                )

                print(
                    self.mqtt_client.publish(
                        f"sensors/sgp30_raw{self.mqtt_sensor_suffix}",
                        json.dumps({"eCO2": self.last_sgp30_co2, "TVOC": self.last_sgp30_tvoc}),
                    )
                )

                print(
                    self.mqtt_client.publish(
                        f"sensors/sgp30_filt{self.mqtt_sensor_suffix}",
                        json.dumps(
                            {
                                "eCO2": self.eavg_sgp30_co2.cur,
                                "TVOC": self.eavg_sgp30_tvoc.cur,
                            }
                        ),
                    )
                )

            if HAS_CCS811:
                print(
                    self.mqtt_client.publish(
                        f"sensors/ccs811_raw{self.mqtt_sensor_suffix}",
                        json.dumps(
                            {
                                "eCO2": self.last_ccs811_co2,
                                "TVOC": self.last_ccs811_tvoc,
                            }
                        ),
                    )
                )

                print(
                    self.mqtt_client.publish(
                        f"sensors/ccs811_filt{self.mqtt_sensor_suffix}",
                        json.dumps(
                            {
                                "eCO2": self.eavg_css811_co2.cur,
                                "TVOC": self.eavg_css811_tvoc.cur,
                            }
                        ),
                    )
                )

            self.last_pub = t
        except Exception as e:
            print(f"Error in pub:", e)

        if HAS_SCD4X and t - self.last_pub_sgp > 60 and self.scd40_co2 is not None and self.scd40_co2 > 0:
            try:
                print(
                    self.mqtt_client.publish(
                        f"sensors/scd40{self.mqtt_sensor_suffix}",
                        json.dumps(
                            {
                                "eCO2": self.scd40_co2,
                                "temp": self.scd40_temp,
                                "humidity": self.scd40_hum,
                            }
                        ),
                    )
                )

                self.last_pub_sgp = t
            except Exception as e:
                print(f"Error in pub:", e)

    def maybe_reconnect_mqtt(self):
        t = utime.time()
        if self.mqtt_client is not None and t - self.last_reconnect < 60 * 3:
            return

        if self.mqtt_client:
            try_fnc(lambda: self.mqtt_client.disconnect())
            sleep_ms(1000)

        try:
            self.mqtt_client = self.connect_mqtt()
            self.last_reconnect = t
        except Exception as e:
            print(f"MQTT connection error:", e)

    def main(self):
        print("Starting bus")
        self.i2c = machine.SoftI2C(scl=machine.Pin(SPG30_SCL_PIN), sda=machine.Pin(SPG30_SDA_PIN))
        self.i2c.start()

        print("Loading config")
        self.load_config()

        print("\nConnecting WiFi")
        self.connect_wifi()

        print("\nConnecting MQTT")
        self.maybe_reconnect_mqtt()

        self.connect_sensors()
        self.publish_booted()
        while True:
            self.maybe_reconnect_mqtt()

            # Measure temperature
            self.measure_temperature()
            self.measure_sqp30()
            self.measure_ccs811()
            self.measure_scd4x()
            self.update_metrics()

            print(
                f"CO2eq: {dval(self.co2eq):4.1f} (r={dval(self.co2eq_1):4d}) ppm, TVOC: {dval(self.tvoc):4d} ppb, "
                + f"CCS CO2: {dval(self.ccs_co2):4d} ({dval(self.eavg_css811_co2.cur):4.1f}), "
                + f"TVOC2: {dval(self.ccs_tvoc):3d} ({dval(self.eavg_css811_tvoc.cur):3.1f}), "
                + f"Eth: {dval(self.eth):5d}, H2: {self.h2:5d}, {dval(self.temp):4.2f} C, {dval(self.humd):4.2f} %%, "
                + f"SCD40: {dval(self.scd40_co2):4.2f}, {dval(self.scd40_temp):4.2f} C, {dval(self.scd40_hum):4.2f} %% "
            )

            self.publish()
            sleep_ms(2_000)


def main():
    sensei = Sensei()
    sensei.main()


# Run the main program
if __name__ == "__main__":
    main()
