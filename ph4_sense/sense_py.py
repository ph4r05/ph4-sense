import board  # adafruit-blinka
import busio
import paho.mqtt.client as mqtt  # paho-mqtt
from ph4monitlib.utils import load_config_file

from ph4_sense.sense import Sensei


class SenseiPy(Sensei):
    def __init__(
        self,
        is_esp32=False,
        has_wifi=False,
        has_aht=True,
        has_sgp30=True,
        has_ccs811=True,
        has_scd4x=True,
        scl_pin=board.SCL7,
        sda_pin=board.SDA7,
        config_file=None,
    ):
        super().__init__(
            is_esp32=is_esp32,
            has_wifi=has_wifi,
            has_aht=has_aht,
            has_sgp30=has_sgp30,
            has_ccs811=has_ccs811,
            has_scd4x=has_scd4x,
            scl_pin=scl_pin,
            sda_pin=sda_pin,
        )
        self.config_file = config_file

    def load_config_data(self):
        cfile = self.config_file or "config.json"
        return load_config_file(cfile)

    def start_bus(self):
        self.i2c = busio.I2C(self.scl_pin, self.sda_pin)

    def connect_wifi(self, force=False):
        pass  # Not used for now

    def check_wifi_ok(self):
        pass  # Not used for now

    def create_mqtt_client(self):
        client = mqtt.Client(f"esp32_client/{self.mqtt_sensor_id}")
        client.on_message = self.mqtt_callback
        client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
        client.subscribe(self.mqtt_topic_sub)
        return client

    def publish_msg(self, topic: str, message: str):
        self.mqtt_client.publish(topic, message)
        self.print(f"Published {topic}:", message)


def main(**kwargs):
    sensei = SenseiPy(**kwargs)
    sensei.main()


# Run the main program
if __name__ == "__main__":
    main()
