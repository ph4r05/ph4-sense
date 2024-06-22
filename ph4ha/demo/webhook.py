import os

import requests

if __name__ == "__main__":
    host = os.getenv("HOST")
    url = f"http://{host}:8123/api/webhook/shelly_cor"
    headers = {
        "Content-Type": "application/json",
    }
    data = {"state": "off", "token": os.getenv("SECRET")}  # Or 'off', depending on your switch state

    response = requests.post(url, json=data, headers=headers, verify=True)
    print(response.text)
