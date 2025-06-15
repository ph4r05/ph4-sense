import json
import os
import socket
import subprocess
import time
from typing import Optional

import paho.mqtt.client as mqtt  # paho-mqtt
import psutil
from attr import dataclass


@dataclass
class Metrics:
    temp_zone0: Optional[float] = None
    temp_zone1: Optional[float] = None
    temp_ssd: Optional[float] = None
    load_avg_1: Optional[float] = None
    mem_percent: Optional[float] = None


def get_hostname():
    return socket.gethostname()


class MetricsCollector:
    def __init__(self):
        self.mqtt_client = None
        self.mqtt_broker = os.getenv("MQTT_BROKER", "localhost")
        self.mqtt_port = 1883
        self.mqtt_topic_sub = self.build_mqtt_topic()
        self.err_ssd_shown = False
        self.metrics = Metrics()

    @classmethod
    def build_mqtt_topic(cls) -> str:
        return os.getenv("MQTT_TOPIC", f"metrics/{get_hostname()}")

    def create_mqtt_client(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, self.mqtt_topic_sub)
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
            self.mqtt_topic_sub,
            {
                "temp_zone0": self.metrics.temp_zone0,
                "temp_zone1": self.metrics.temp_zone1,
                "temp_ssd": self.metrics.temp_ssd,
                "load_avg1": self.metrics.load_avg_1,
                "mem_percent": self.metrics.mem_percent,
            },
        )

    def read_temp(self, fname):
        if not os.path.exists(fname):
            return None
        with open(fname, "r") as f:
            dt = f.read()
            return float(dt.strip()) / 1000.0

    def read_ssd_temp(self):
        try:
            result = subprocess.run(
                ["sudo", "/usr/sbin/nvme", "smart-log", "/dev/nvme0", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise ValueError(f"Command failed with return code {result.returncode}: {result.stderr}")

            stdout = result.stdout
            js = json.loads(stdout.strip())
            return float(js["temperature"]) - 273.15 if "temperature" in js else None
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            if not self.err_ssd_shown:
                print(f"Error reading SSD temperature: {e}")
                self.err_ssd_shown = True
        return None

    def compute_metrics(self):
        try:
            self.metrics.temp_zone0 = self.read_temp("/sys/class/thermal/thermal_zone0/temp")
            self.metrics.temp_zone1 = self.read_temp("/sys/class/thermal/thermal_zone1/temp")
            self.metrics.temp_ssd = self.read_ssd_temp()

            load_avg = psutil.getloadavg()
            self.metrics.load_avg_1 = load_avg[0]

            memory = psutil.virtual_memory()
            self.metrics.mem_percent = memory.percent

        except Exception as e:
            print(f"Error in metrics collection {e}")

    def main_loop(self):
        print(f"Starting Metrics Collector, {self.mqtt_broker=}, {self.mqtt_port=}, {self.mqtt_topic_sub=}")
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
    worker = MetricsCollector()
    worker.main_loop()
