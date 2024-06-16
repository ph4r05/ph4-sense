import hashlib
import os
import re
import secrets
import sys

import requests


class ShellyAuthClient:
    def __init__(self, base_url, password, username=None):
        self.base_url = base_url
        self.username = username or "admin"
        self.password = password
        self.token = None
        self.token_expiry = None

    def comp_ha(self, realm):
        return hashlib.sha256(f"{self.username}:{realm}:{self.password}".encode("utf-8")).hexdigest()

    def parse_www_auth(self, auth_string):
        pattern = re.compile(r'(\w+)="([^"]+)"')
        matches = pattern.findall(auth_string)
        digest_params = dict(matches)
        return digest_params

    def authenticate(self, response):
        hdr = response.headers["WWW-Authenticate"]
        m = re.match(r'.*\brealm="(.+?)".*\bnonce="(.+?)".*$', hdr)
        if not m:
            raise ValueError(f"Invalid header: {hdr}")

        realm = m.group(1)
        nonce = m.group(2)
        ha1 = self.comp_ha(realm)
        cnonce = secrets.randbelow(2**32)
        ha2 = hashlib.sha256(b"dummy_method:dummy_uri").hexdigest()
        auth_str = f"{ha1}:{nonce}:{1}:{cnonce}:auth:{ha2}"
        auth = hashlib.sha256(auth_str.encode("utf-8")).hexdigest()
        return {
            "realm": realm,
            "username": self.username,
            "nonce": nonce,
            "cnonce": cnonce,
            "response": auth,
            "algorithm": "SHA-256",
        }

    def get_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def call_rpc(self, method=None, params=None):
        method_part = f"/{method}" if method else ""
        rpc_url = f"{self.base_url}/rpc{method_part}"

        headers = {}
        response = requests.post(rpc_url, json=params, headers=headers)
        if response.status_code == 401:
            params["auth"] = self.authenticate(response)
            response = requests.post(rpc_url, json=params)

        js = response.json()
        print(js)
        return response.json()


if __name__ == "__main__":
    base_url = os.getenv("SHELLY_HOST")
    password = os.getenv("SHELLY_PASS")
    if not base_url:
        sys.exit(0)

    client = ShellyAuthClient(base_url, password=password)
    client.call_rpc(params={"id": 1, "method": "Script.Eval", "params": {"id": 2, "code": "switchTo(true)"}})

    # rpc_method = "Shelly.GetDeviceInfo"
    # response = client.call_rpc(rpc_method)
    # print(response)
