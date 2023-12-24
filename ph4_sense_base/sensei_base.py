from ph4_sense_base.adapters import getLogger, json, mem_stats, sleep_ms, time
from ph4_sense_base.mods.gpio import GpioMod
from ph4_sense_base.mods.i2c import I2CMod
from ph4_sense_base.mods.mqtt import MqttMod
from ph4_sense_base.mods.uart import UartMod
from ph4_sense_base.mods.wifi import WifiMod
from ph4_sense_base.mods_mp.gpio import GpioModMp
from ph4_sense_base.mods_mp.i2c import I2CModMp
from ph4_sense_base.mods_mp.mqtt import MqttModMp
from ph4_sense_base.mods_mp.uart import UartModMp
from ph4_sense_base.mods_mp.wifi import WifiModMp
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.typing import Optional
from ph4_sense_base.utils import def_val


class SenseiBase(SenseiIface):
    def __init__(self, is_esp32=True, has_wifi=True, scl_pin=22, sda_pin=21):
        super().__init__()
        self.is_esp32 = is_esp32
        self.has_wifi = has_wifi
        self.has_i2c = False
        self.has_mqtt = False

        self.scl_pin = scl_pin
        self.sda_pin = sda_pin

        self.mod_wifi: Optional[WifiMod] = None
        self.mod_mqtt: Optional[MqttMod] = None
        self.mod_i2c: Optional[I2CMod] = None
        self.mod_uart: Optional[UartMod] = None
        self.mod_gpio: Optional[GpioMod] = None

        self.set_sensor_id("default")

        self.reconnect_attempts = 40
        self.reconnect_timeout = 500
        self.mqtt_reconnect_timeout = 60 * 3
        self.wifi_reconnect_timeout = 60 * 3
        self.readings_publish_timeout = 60

        self.last_reconnect = time.time()
        self.last_wifi_reconnect = 0

        self.i2c = None
        self.udp_logger = None
        self.logger = None

    def init_mods(self):
        if self.is_esp32:
            self.mod_wifi = WifiModMp(base=self, has_wifi=self.has_wifi)
            self.mod_mqtt = MqttModMp(base=self, has_mqtt=self.has_mqtt)
            self.mod_i2c = I2CModMp(base=self, has_i2c=self.has_i2c, scl_pin=self.scl_pin, sda_pin=self.sda_pin)
            self.mod_uart = UartModMp(base=self)
            self.mod_gpio = GpioModMp(base=self)

    def set_sensor_id(self, sensor_id):
        assert self.mod_mqtt is not None
        self.mod_mqtt.set_sensor_id(sensor_id)

    def load_config_data(self):
        with open("config.json") as fh:
            return json.load(fh)

    def load_config(self):
        js = self.load_config_data()
        sensor_id = def_val(js, "sensor_id")

        if sensor_id:
            self.set_sensor_id(sensor_id)

        self.load_mods_config(js)

    def load_mods_config(self, js):
        if self.mod_mqtt is not None:
            self.mod_mqtt.load_config(js)
        if self.mod_wifi is not None:
            self.mod_wifi.load_config(js)
        if self.mod_i2c is not None:
            self.mod_i2c.load_config(js)
        if self.mod_uart is not None:
            self.mod_uart.load_config(js)
        if self.mod_gpio is not None:
            self.mod_gpio.load_config(js)

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
        if self.mod_wifi is not None:
            self.mod_wifi.connect_wifi(force=force)

    def check_wifi_ok(self):
        if not self.has_wifi:
            return
        if self.mod_wifi is not None:
            return self.mod_wifi.check_wifi_ok()

    def create_mqtt_client(self):
        raise NotImplementedError

    def connect_mqtt(self):
        if self.mod_mqtt is not None:
            self.mod_mqtt.connect_mqtt()

    def get_uart_builder(self, desc):
        raise NotImplementedError

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

    def update_metrics(self):
        pass

    def publish_msg(self, topic: str, message: str):
        if self.mod_mqtt is not None:
            self.mod_mqtt.publish_msg(topic=topic, message=message)

    def publish_payload(self, topic: str, payload: dict):
        if not self.has_mqtt:
            return

        self.publish_msg(topic, json.dumps(payload))

    def publish_booted(self):
        self.publish_payload(
            self.mod_mqtt.mqtt_topic_base,
            {
                "booted": True,
            },
        )

    def on_wifi_reconnect(self):
        self.print("WiFi Reconnecting")
        self.connect_wifi(force=True)
        self.maybe_reconnect_mqtt(force=True)

    def maybe_reconnect_mqtt(self, force=False):
        if self.mod_mqtt:
            self.mod_mqtt.maybe_reconnect_mqtt(force=force)

    def start_bus(self):
        if self.mod_i2c:
            self.mod_i2c.start_bus()

    def log_memory(self):
        stats = mem_stats()
        self.print("Memory alloc {}, free {}".format(stats[0], stats[1]))

    def base_init(self):
        self.logger = getLogger(__name__)

    def post_start(self):
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
