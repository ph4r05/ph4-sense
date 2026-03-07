#!/usr/bin/env python3
"""
provision.py — Configure the ph4_tuya_esp32bridge device.

Two modes:
  1. AP mode (device is acting as provisioning AP):
       python provision.py ap --config config/config.json
       Connect your laptop to the ESP32 AP (ph4-bridge-XXXXXX), then run this.
       It POSTs the config JSON to http://192.168.4.1/config.

  2. MQTT mode (device is already on WiFi):
       python provision.py mqtt --host 192.168.1.x --config config/config.json
       Publishes the config JSON fields individually via MQTT.
       Sends "reboot" command after upload.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# -----------------------------------------------------------------------
# AP mode provisioning
# -----------------------------------------------------------------------


def provision_ap(config_path: str, host: str = "192.168.4.1") -> None:
    print(f"[AP] Loading config from {config_path}")
    with open(config_path) as f:
        cfg = json.load(f)

    payload = json.dumps(cfg).encode()
    url = f"http://{host}/config"

    print(f"[AP] Posting config to {url}")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            print(f"[AP] Response: {body}")
    except urllib.error.URLError as e:
        print(f"[AP] ERROR: {e}")
        print("[AP] Make sure you are connected to the ESP32 AP (ph4-bridge-XXXXXX)")
        sys.exit(1)

    print("[AP] Config sent. Device will reboot and connect to WiFi.")


def status_ap(host: str = "192.168.4.1") -> None:
    url = f"http://{host}/status"
    print(f"[AP] GET {url}")
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            print(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"[AP] ERROR: {e}")


def get_config_ap(host: str = "192.168.4.1") -> None:
    url = f"http://{host}/config"
    print(f"[AP] GET {url}")
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            print(json.dumps(data, indent=2))
    except urllib.error.URLError as e:
        print(f"[AP] ERROR: {e}")


# -----------------------------------------------------------------------
# MQTT mode provisioning
# -----------------------------------------------------------------------


def provision_mqtt(
    config_path: str, host: str, port: int = 1883, user: str = "", password: str = "", prefix: str = "ph4/bridge"
) -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("ERROR: paho-mqtt not installed. Run: pip install paho-mqtt")
        sys.exit(1)

    print(f"[MQTT] Loading config from {config_path}")
    with open(config_path) as f:
        cfg = json.load(f)

    connected = [False]

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            connected[0] = True
            print(f"[MQTT] Connected to {host}:{port}")
        else:
            print(f"[MQTT] Connection failed: rc={rc}")

    client = mqtt.Client(client_id="ph4-provision-tool")
    client.on_connect = on_connect
    if user:
        client.username_pw_set(user, password)

    client.connect(host, port, keepalive=30)
    client.loop_start()

    deadline = time.time() + 10
    while not connected[0] and time.time() < deadline:
        time.sleep(0.1)

    if not connected[0]:
        print("[MQTT] ERROR: Could not connect to broker")
        sys.exit(1)

    # Publish config as a single JSON blob to {prefix}/config/set
    payload = json.dumps(cfg)
    topic = f"{prefix}/config/set"
    print(f"[MQTT] Publishing config to {topic}")
    client.publish(topic, payload, qos=1, retain=False)
    time.sleep(1)

    # Send reboot command
    print(f"[MQTT] Sending reboot command to {prefix}/cmd")
    client.publish(f"{prefix}/cmd", "reboot", qos=1)
    time.sleep(1)

    client.loop_stop()
    client.disconnect()
    print("[MQTT] Done. Device will reboot.")


def send_cmd_mqtt(
    cmd: str, host: str, port: int = 1883, user: str = "", password: str = "", prefix: str = "ph4/bridge"
) -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("ERROR: paho-mqtt not installed. Run: pip install paho-mqtt")
        sys.exit(1)

    connected = [False]

    def on_connect(client, userdata, flags, rc):
        connected[0] = rc == 0

    client = mqtt.Client(client_id="ph4-cmd-tool")
    client.on_connect = on_connect
    if user:
        client.username_pw_set(user, password)

    client.connect(host, port, keepalive=10)
    client.loop_start()

    deadline = time.time() + 5
    while not connected[0] and time.time() < deadline:
        time.sleep(0.1)

    if not connected[0]:
        print("[MQTT] ERROR: Could not connect to broker")
        sys.exit(1)

    topic = f"{prefix}/cmd"
    print(f"[MQTT] Publishing '{cmd}' to {topic}")
    client.publish(topic, cmd, qos=1)
    time.sleep(0.5)
    client.loop_stop()
    client.disconnect()


# -----------------------------------------------------------------------
# Switch control helper (for testing)
# -----------------------------------------------------------------------


def set_switch_mqtt(
    channel: int,
    value: bool,
    host: str,
    port: int = 1883,
    user: str = "",
    password: str = "",
    prefix: str = "ph4/bridge",
) -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("ERROR: paho-mqtt not installed.")
        sys.exit(1)

    connected = [False]

    def on_connect(client, userdata, flags, rc):
        connected[0] = rc == 0

    client = mqtt.Client(client_id="ph4-switch-tool")
    client.on_connect = on_connect
    if user:
        client.username_pw_set(user, password)
    client.connect(host, port, keepalive=10)
    client.loop_start()

    deadline = time.time() + 5
    while not connected[0] and time.time() < deadline:
        time.sleep(0.1)

    topic = f"{prefix}/switch/{channel}/set"
    payload = "ON" if value else "OFF"
    print(f"[MQTT] {topic} = {payload}")
    client.publish(topic, payload, qos=1)
    time.sleep(0.5)
    client.loop_stop()
    client.disconnect()


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="ph4_tuya_esp32bridge provisioning tool")
    sub = parser.add_subparsers(dest="mode", required=True)

    # --- AP subcommand ---
    ap_p = sub.add_parser("ap", help="Provision via AP mode HTTP")
    ap_p.add_argument("--config", "-c", default="config/config.json", help="Path to config JSON file")
    ap_p.add_argument("--host", default="192.168.4.1", help="ESP32 AP IP (default: 192.168.4.1)")
    ap_p.add_argument("--get", action="store_true", help="GET current config instead of posting")
    ap_p.add_argument("--status", action="store_true", help="GET device status")

    # --- MQTT subcommand ---
    mq_p = sub.add_parser("mqtt", help="Provision / control via MQTT")
    mq_p.add_argument("--host", required=True, help="MQTT broker host")
    mq_p.add_argument("--port", type=int, default=1883)
    mq_p.add_argument("--user", default="")
    mq_p.add_argument("--pass", dest="password", default="")
    mq_p.add_argument("--prefix", default="ph4/bridge")
    mq_p.add_argument("--config", "-c", default=None, help="Path to config JSON (if uploading config)")
    mq_p.add_argument("--cmd", default=None, help="Send a control command (reset|reboot|status|sync)")
    mq_p.add_argument("--switch", type=int, default=None, help="Set switch channel (1-16)")
    mq_p.add_argument("--on", action="store_true", help="Set switch ON")
    mq_p.add_argument("--off", action="store_true", help="Set switch OFF")

    args = parser.parse_args()

    if args.mode == "ap":
        if args.status:
            status_ap(args.host)
        elif args.get:
            get_config_ap(args.host)
        else:
            provision_ap(args.config, args.host)

    elif args.mode == "mqtt":
        kw = dict(host=args.host, port=args.port, user=args.user, password=args.password, prefix=args.prefix)
        if args.config:
            provision_mqtt(args.config, **kw)
        elif args.cmd:
            send_cmd_mqtt(args.cmd, **kw)
        elif args.switch is not None:
            value = args.on or not args.off
            set_switch_mqtt(args.switch, value, **kw)
        else:
            print("[MQTT] Specify --config, --cmd, or --switch")
            sys.exit(1)


if __name__ == "__main__":
    main()
