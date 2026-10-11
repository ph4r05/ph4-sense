"""Minimal Home Assistant API client for the Tuya->HA migration tooling.

Credentials are never hardcoded: the long-lived access token is read at
runtime from ~/.claude.env (key "HA"), never logged, printed, or embedded
in any generated file. HA_URL defaults to this household's instance but
can be overridden via the HA_URL env var.

This dev machine has two active interfaces on the same 10.0.1.0/24
subnet (en0 = 10.0.1.160, real; en13 = 10.0.1.27, appears dead/
unconnected). Raw-socket clients (Python's socket/requests, Node) pick
en13 by default and get EHOSTUNREACH; curl/nc land on en0 and work
fine. Not a permission/sandbox issue -- just interface selection. Fixed
here by explicitly binding outbound connections to the working address.
"""

import asyncio
import json
import os
from pathlib import Path

import requests
import websockets

HA_URL = os.environ.get("HA_URL", "http://10.0.1.103:8123")
LOCAL_BIND_IP = os.environ.get("HA_LOCAL_BIND_IP", "10.0.1.160")


class _SourceAddressAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, source_address, **kwargs):
        self.source_address = source_address
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["source_address"] = self.source_address
        return super().init_poolmanager(*args, **kwargs)


def _session():
    s = requests.Session()
    adapter = _SourceAddressAdapter((LOCAL_BIND_IP, 0))
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def _load_token():
    env_path = Path.home() / ".claude.env"
    for line in env_path.read_text().splitlines():
        if line.startswith("HA="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"No HA= line found in {env_path}")


def get_states():
    """REST: all entity states (entity_id, state, attributes)."""
    tok = _load_token()
    r = _session().get(f"{HA_URL}/api/states", headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    r.raise_for_status()
    return r.json()


async def _ws_fetch(commands):
    """Send a list of websocket commands after authenticating, return
    {command_id: result} for each."""
    tok = _load_token()
    ws_url = HA_URL.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
    results = {}
    async with websockets.connect(ws_url, max_size=None, local_addr=(LOCAL_BIND_IP, 0)) as ws:
        hello = json.loads(await ws.recv())
        assert hello["type"] == "auth_required", hello
        await ws.send(json.dumps({"type": "auth", "access_token": tok}))
        auth_resp = json.loads(await ws.recv())
        if auth_resp["type"] != "auth_ok":
            raise RuntimeError(f"HA websocket auth failed: {auth_resp}")

        for i, cmd in enumerate(commands, start=1):
            msg = {"id": i, **cmd}
            await ws.send(json.dumps(msg))

        received = 0
        while received < len(commands):
            resp = json.loads(await ws.recv())
            if resp.get("type") == "result":
                results[resp["id"]] = resp.get("result")
                received += 1
    return results


def get_registries():
    """WebSocket: entity_registry, device_registry, config_entries lists.
    This is what the HA frontend itself uses to know which integration
    (platform/config_entry) owns each entity -- not available via REST."""
    commands = [
        {"type": "config/entity_registry/list"},
        {"type": "config/device_registry/list"},
        {"type": "config_entries/get"},
    ]
    results = asyncio.run(_ws_fetch(commands))
    return {
        "entities": results[1],
        "devices": results[2],
        "config_entries": results[3],
    }


if __name__ == "__main__":
    # Smoke test: connectivity only, no token ever printed.
    states = get_states()
    print(f"REST OK: {len(states)} entities")
    reg = get_registries()
    print(
        f"WS OK: {len(reg['entities'])} registry entries, "
        f"{len(reg['devices'])} devices, {len(reg['config_entries'])} config entries"
    )
