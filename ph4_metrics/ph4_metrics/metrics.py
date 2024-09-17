import json
import os
import time
from typing import Optional

import paho.mqtt.client as mqtt  # paho-mqtt
import psutil
from attr import dataclass


@dataclass
class Metrics:
    temp_zone0: Optional[float] = None
    temp_zone1: Optional[float] = None
    load_avg_1: Optional[float] = None
    mem_percent: Optional[float] = None


class Bark:
    def __init__(self):
        self.mqtt_client = None
        self.mqtt_broker = "localhost"
        self.mqtt_port = 1883
        self.mqtt_topic_sub = "bark"
        self.metrics = Metrics()

    def create_mqtt_client(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "metrics/liv")
        client.on_message = self.mqtt_callback
        client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
        client.subscribe(self.mqtt_topic_sub)
        return client

    def mqtt_callback(self, topic=None, msg=None):
        print("Received MQTT message:", topic, msg)

    def publish_msg(self, topic: str, message: str):
        self.mqtt_client.publish(topic, message)
        print(f"Published {topic}:", message)

    def publish_payload(self, topic: str, payload: dict):
        self.publish_msg(topic, json.dumps(payload))

    def publish(self):
        self.publish_payload(
            "metrics/liv",
            {
                "temp_zone0": self.metrics.temp_zone0,
                "temp_zone1": self.metrics.temp_zone1,
                "load_avg1": self.metrics.load_avg_1,
                "mem_percent": self.metrics.mem_percent,
            },
        )

    def read_temp(self, fname):
        if not os.path.exists(fname):
            return None
        with open(fname, "r") as f:
            dt = f.read()
            return float(dt.strip())

    def compute_metrics(self):
        try:
            self.metrics.temp_zone0 = self.read_temp("/sys/class/thermal/thermal_zone0/temp")
            self.metrics.temp_zone1 = self.read_temp("/sys/class/thermal/thermal_zone1/temp")

            load_avg = psutil.getloadavg()
            self.metrics.load_avg_1 = load_avg[0]

            memory = psutil.virtual_memory()
            self.metrics.mem_percent = memory.percent

        except Exception as e:
            print(f"Error in metrics collection {e}")

    def main_loop(self):
        while True:
            try:
                self.mqtt_client = self.create_mqtt_client()
                print("MQTT client connected")
                break
            except Exception as e:
                print(f"Error in MQTT client {e}")
                time.sleep(60)

        while True:
            self.compute_metrics()
            self.publish()
            print(f"Published metrics to {self.mqtt_broker}:{self.mqtt_port}: {self.metrics}")
            time.sleep(60)


if __name__ == "__main__":
    bark = Bark()
    bark.main_loop()
