from ph4_sense_base.adapters import sleep_ms, time
from ph4_sense_base.mods import BaseMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.consts import Const
from ph4_sense_base.support.typing import Optional
from ph4_sense_base.utils import try_exec_method_cb, try_fnc


class MqttMod(BaseMod):
    def __init__(
        self,
        base: Optional[SenseiIface] = None,
        has_mqtt: bool = True,
        mqtt_reconnect_timeout: int = 60 * 3,
        last_reconnect: Optional[int] = None,
    ):
        super().__init__()
        self.base = base
        self.has_mqtt = has_mqtt
        self.mqtt_client = None
        self.last_reconnect = last_reconnect if last_reconnect is not None else time.time()
        self.mqtt_reconnect_timeout = mqtt_reconnect_timeout

        self.mqtt_sensor_id = ""
        self.mqtt_sensor_suffix = ""
        self.mqtt_topic_sub = ""
        self.mqtt_topic_base = ""
        self.mqtt_topic = ""

    def set_sensor_id(self, sensor_id):
        self.mqtt_sensor_id = sensor_id or ""
        self.mqtt_sensor_suffix = f"_{self.mqtt_sensor_id}" if self.mqtt_sensor_id else ""
        self.mqtt_topic_sub = f"sensors/esp32_{self.mqtt_sensor_id}_sub"
        self.mqtt_topic_base = f"sensors/esp32_{self.mqtt_sensor_id}"
        self.mqtt_topic = f"sensors/esp32_{self.mqtt_sensor_id}_gas"

    def maybe_reconnect_mqtt(self, force=False):
        if not self.has_mqtt:
            return

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
            try_exec_method_cb(self.base, Const.PRINT, "MQTT connection error:", e)

    def connect_mqtt(self):
        self.mqtt_client = self.create_mqtt_client()

    def create_mqtt_client(self):
        raise NotImplementedError()

    def publish_msg(self, topic: str, message: str):
        raise NotImplementedError()
