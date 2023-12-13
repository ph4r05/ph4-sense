from ph4_sense_base.adapters import sleep_ms, time
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.consts import Const
from ph4_sense_base.support.typing import Optional
from ph4_sense_base.utils import try_exec_method_cb, try_fnc


class MqttMod:
    def __init__(
        self,
        base: Optional[SenseiIface] = None,
        has_mqtt: bool = True,
        mqtt_reconnect_timeout: int = 60 * 3,
        last_reconnect: Optional[int] = None,
    ):
        self.base = base
        self.has_mqtt = has_mqtt
        self.mqtt_client = None
        self.last_reconnect = last_reconnect if last_reconnect is not None else time.time()
        self.mqtt_reconnect_timeout = mqtt_reconnect_timeout

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
        pass

    def publish_msg(self, topic: str, message: str):
        pass
