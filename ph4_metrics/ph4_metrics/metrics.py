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
    BIRTH_TOPIC = "homeassistant/status"

    def __init__(self):
        self.mqtt_client = None
        self.mqtt_broker = os.getenv("MQTT_BROKER", "localhost")
        self.mqtt_port = 1883
        self.mqtt_topic_recv = self.build_mqtt_topic()
        self.mqtt_topic_sub = self.mqtt_topic_recv + "/sub"
        self.err_ssd_shown = False
        self.discovery_sent = False
        self.metrics = Metrics()

    @classmethod
    def build_mqtt_topic(cls) -> str:
        return os.getenv("MQTT_TOPIC", f"metrics/{get_hostname()}")

    @classmethod
    def topic_normalize(cls, topic: str) -> str:
        return topic.replace("/", "_").replace("-", "_").replace(".", "_")

    def create_mqtt_client(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, self.mqtt_topic_recv)
        client.on_message = self.mqtt_callback
        client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
        client.subscribe(self.mqtt_topic_sub)
        client.subscribe(self.BIRTH_TOPIC)
        return client

    def mqtt_callback(self, client, userdata, message, *args, **kwargs):
        topic = message.topic
        payload = message.payload.decode()
        print(f"Received MQTT message: {client=}, {userdata=}, {message=}, {topic=}, {payload=}")
        if topic == self.BIRTH_TOPIC and payload == "online":
            self.discovery_sent = False

    def publish_msg(self, topic: str, message: str):
        self.mqtt_client.publish(topic, message)
        print(f"Published {topic}:", message)

    def publish_payload(self, topic: str, payload: dict):
        self.send_auto_discovery(topic, payload)
        self.publish_msg(topic, json.dumps(payload))

    def send_auto_discovery(self, topic: str, payload: dict):
        if self.discovery_sent:
            return

        for key in payload:
            unique_id = f"{self.topic_normalize(topic)}_{self.topic_normalize(key)}"
            discovery_topic = f"homeassistant/sensor/{unique_id}/config"
            unit = ""
            if key.startswith("temp_"):
                unit = "°C"
            elif key.startswith("mem"):
                unit = "%"

            discovery_payload = {
                "name": f"{key} {get_hostname()}",
                "state_topic": topic,
                "unit_of_measurement": unit,
                "value_template": "{{ value_json.%s }}" % key,
                "json_attributes_topic": topic,
                "unique_id": unique_id,
                "device": {
                    "identifiers": [get_hostname()],
                    "name": get_hostname(),
                    "manufacturer": "PH4",
                    "model": "Metrics Collector",
                },
            }
            self.publish_msg(discovery_topic, json.dumps(discovery_payload))
            print(f"Published auto-discovery to {discovery_topic}: {discovery_payload}")

        self.discovery_sent = True

    def publish(self):
        self.publish_payload(
            self.mqtt_topic_recv,
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
        print(
            f"Starting Metrics Collector, {self.mqtt_broker=}, {self.mqtt_port=}, {self.mqtt_topic_recv=}, {self.mqtt_topic_sub=}"
        )
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
            tstart = time.time()
            while time.time() - tstart < 60:
                try:
                    self.mqtt_client.loop(timeout=1.0)  # Process network events
                except Exception as e:
                    print(f"Error in MQTT loop {e}")
                    break
                time.sleep(0.0001)  # Yield to allow other tasks to run

            # self.mqtt_client.loop(timeout=60.0)  # Process network events
            # time.sleep(60)


if __name__ == "__main__":
    worker = MetricsCollector()
    worker.main_loop()
