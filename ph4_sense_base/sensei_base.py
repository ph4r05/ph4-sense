from ph4_sense_base.adapters import getLogger, json, mem_stats, sleep_ms, time
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.utils import try_fnc

try:
    from typing import List
except ImportError:
    pass


class SenseiBase(SenseiIface):
    def __init__(self, is_esp32=True, has_wifi=True, scl_pin=22, sda_pin=21):
        super().__init__()
        self.is_esp32 = is_esp32
        self.has_wifi = has_wifi
        self.scl_pin = scl_pin
        self.sda_pin = sda_pin

        self.wifi_ssid = None
        self.wifi_passphrase = None

        self.has_mqtt = False
        self.mqtt_broker = None
        self.mqtt_port = 1883
        self.mqtt_sensor_id = None
        self.mqtt_sensor_suffix = None
        self.mqtt_topic_sub = None
        self.mqtt_topic = None
        self.set_sensor_id("default")

        self.reconnect_attempts = 40
        self.reconnect_timeout = 500
        self.mqtt_reconnect_timeout = 60 * 3
        self.wifi_reconnect_timeout = 60 * 3
        self.readings_publish_timeout = 60

        self.last_reconnect = time.time()
        self.last_wifi_reconnect = 0

        self.i2c = None
        self.sta_if = None
        self.mqtt_client = None
        self.udp_logger = None
        self.logger = None

    def set_sensor_id(self, sensor_id):
        self.mqtt_sensor_id = sensor_id or ""
        self.mqtt_sensor_suffix = f"_{self.mqtt_sensor_id}" if self.mqtt_sensor_id else ""
        self.mqtt_topic_sub = f"sensors/esp32_{self.mqtt_sensor_id}_sub"
        self.mqtt_topic = f"sensors/esp32_{self.mqtt_sensor_id}_gas"

    def load_config_data(self):
        with open("config.json") as fh:
            return json.load(fh)

    def load_config(self):
        return self.load_config_data()

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
        raise NotImplementedError

    def publish_payload(self, topic: str, payload: dict):
        if not self.has_mqtt:
            return

        self.publish_msg(topic, json.dumps(payload))

    def publish_booted(self):
        self.publish_payload(
            f"sensors/esp32{self.mqtt_sensor_suffix}",
            {
                "booted": True,
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
        """Template method, empty by default"""
        pass

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
