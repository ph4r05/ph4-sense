import json
import time

import hassapi as hass
import requests


class ShellyHallway(hass.Hass):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.corr_token = None
        self.corr_pass = None
        self.corr_host = None
        self.last_update = 0

    def initialize(self):
        self.corr_token = self.args["shelly_cor_token"]
        self.corr_pass = self.args["shelly_cor_pass"]
        self.corr_host = self.args["shelly_cor_host"]

        self.listen_state(self.hallway_state_flip, "switch.hallway_switch", arg1="home assistant")
        self.register_endpoint(self.endpoint_shelly_cor, "shelly_cor")
        self.log("initialized")

    def hallway_state_flip(self, entity, attribute, old, new, cb_args):
        self.log(f"On hallway flip {entity} {old=} {new=}")
        if time.time() - self.last_update <= 1:
            return  # ignore

        to_switch = "false" if new == "false" or new == "off" else "true"
        data = {"id": 1, "method": "Script.Eval", "params": {"id": 2, "code": f"switchTo({to_switch})"}}
        response = requests.post(
            f"http://{self.corr_host}/rpc", data=json.dumps(data), headers={"Content-Type": "application/json"}
        )
        self.log(response)

    def run_daily_callback(self, cb_args):
        self.turn_on("light.porch")

    def endpoint_shelly_cor(self, data, cb_args):
        """
        curl -X POST -d '{"token":"token","state":"on"}' http://ha.local:5050/api/appdaemon/shelly_cor
        """
        if "token" not in data:
            self.log(f"No token in data: {data}")
            return "No token", 400
        if data["token"] != self.corr_token:
            self.log("Incorrect token")
            return "Incorrect token", 401
        if "state" not in data:
            self.log("No state in request")
            return "No state", 401

        # request = cb_args['request']
        self.last_update = time.time()
        self.call_service("input_text/set_value", entity_id="input_text.hallway_switch_state", value=data["state"])
        response = {"response": "ok"}
        return response, 200
