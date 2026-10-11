#!/usr/bin/env python3
"""Pull the authoritative Zigbee2MQTT device list straight from the
retained zigbee2mqtt/bridge/devices MQTT message, rather than trying to
scrape the Z2M web frontend (a single-page app that talks to MQTT
directly from the browser, not a REST API)."""
import json
import time

import paho.mqtt.client as mqtt

BROKER = "10.0.1.103"
PORT = 1883

received = {}


def on_message(client, userdata, msg):
    received[msg.topic] = msg.payload.decode("utf-8", errors="replace")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message
client.connect(BROKER, PORT, keepalive=10)
client.subscribe("zigbee2mqtt/bridge/devices")
client.subscribe("zigbee2mqtt/bridge/info")
client.loop_start()
time.sleep(3)
client.loop_stop()
client.disconnect()

devices_raw = received.get("zigbee2mqtt/bridge/devices")
if not devices_raw:
    print(
        "No retained message received on zigbee2mqtt/bridge/devices "
        "(wrong topic prefix, broker auth needed, or bridge not publishing retained)."
    )
else:
    devices = json.loads(devices_raw)
    print(f"{len(devices)} Zigbee2MQTT devices:\n")
    for d in devices:
        if d.get("type") == "Coordinator":
            print(f"[coordinator] {d.get('friendly_name')}")
            continue
        print(
            f"{d.get('friendly_name'):30s} model={d.get('model_id') or d.get('definition',{}).get('model')!s:20s} "
            f"vendor={(d.get('definition') or {}).get('vendor')!s:15s} "
            f"ieee={d.get('ieee_address')} interview={d.get('interview_completed')} "
            f"supported={d.get('supported')}"
        )

info_raw = received.get("zigbee2mqtt/bridge/info")
if info_raw:
    info = json.loads(info_raw)
    print(f"\nZ2M version: {info.get('version')}, coordinator: {info.get('coordinator', {}).get('type')}")
