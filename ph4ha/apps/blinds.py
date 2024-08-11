import json

import hassapi as hass
import requests


class Blinds(hass.Hass):
    """
    TODO: collect manual state changes. manual state change cancels the next routine
    TODO: add pause automation toggle
    TODO: add sync - sets state appropriate for this time of a day
    """

    BLIND_LIV_BIG = "LivBig"
    BLIND_LIV_DOOR = "LivDoor"
    BLIND_BEDROOM = "Bedroom"
    BLIND_STUDY = "Study"
    BLIND_SKLAD = "Sklad"
    OPEN_HALF = 0.9

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.blinds = None
        self.weekdays_open_time = None

    def initialize(self):
        self.blinds = {x["name"]: x for x in self.args["blinds"]}
        self.weekdays_open_time = None  # self.get_state(self.args["weekdays_open_time"])

        self.listen_event(self.scene_activated, "call_service", domain="scene", service="turn_on")

        # # Schedule for weekdays
        # self.run_daily(self.open_blinds, time(hour=7, minute=30), weekdays="mon,tue,wed,thu,fri")
        #
        # # Schedule for weekends
        # self.run_daily(self.open_blinds_weekends, time(hour=11, minute=0), weekdays="sat,sun")
        #
        # # Schedule to raise blinds at 18:00 every day
        # self.run_daily(self.raise_blinds, time(hour=18, minute=0))
        #
        # # Schedule to lower blinds at 22:00 every day
        # self.run_daily(self.lower_blinds, time(hour=22, minute=0))
        #
        # # Schedule to lower and tilt blinds 1 hour after sunset
        # self.run_at_sunset(self.lower_and_tilt_blinds, offset=3600)  # offset in seconds

        self.log("initialized")

    def scene_activated(self, event_name, data, kwargs):
        # Extract the scene ID or entity ID
        scene_id = data.get("service_data", {}).get("entity_id")
        self.log(f"scene_activated: {scene_id}")

        if scene_id == "scene.blinds_vent":
            self.log("Scene: blinds_vent")
            self.handle_vent()
        elif scene_id == "scene.blinds_living_morning":
            self.log("Scene: blinds_living_morning")
            self.blinds_living_morning()
        elif scene_id == "scene.blinds_living_morning_hot":
            self.log("Scene: blinds_living_morning_hot")
            self.blinds_living_morning_hot()
        elif scene_id == "scene.blinds_living_privacy":
            self.log("Scene: blinds_living_privacy")
            self.blinds_living_privacy()
        elif scene_id == "scene.blinds_all_up":
            self.log("Scene: blinds_all_up")
            self.blinds_all_up()
        elif scene_id == "scene.blinds_all_down":
            self.log("Scene: blinds_all_down")
            self.blinds_all_down()
        elif scene_id == "scene.blinds_tilt_open":
            self.log("Scene: blinds_tilt_open")
            self.blinds_tilt_open()
        elif scene_id == "scene.blinds_tilt_close":
            self.log("Scene: blinds_tilt_close")
            self.blinds_tilt_close()
        elif scene_id == "scene.blinds_down_open":
            self.log("Scene: blinds_down_open")
            self.blinds_down_open()
        elif scene_id == "scene.blinds_all_down_open":
            self.log("Scene: blinds_all_down_open")
            self.blinds_all_down_open()
        elif scene_id == "scene.blinds_morning":
            self.log("Scene: blinds_morning")
            self.blinds_morning()
        elif scene_id == "scene.blinds_living_down_close":
            self.log("Scene: blinds_living_down_close")
            self.blinds_living_down_close()
        elif scene_id == "scene.blinds_living_down_open":
            self.log("Scene: blinds_living_down_open")
            self.blinds_living_down_open()
        elif scene_id == "scene.blinds_living_down_privacy":
            self.log("Scene: blinds_living_down_privacy")
            self.blinds_living_down_privacy()

    def handle_vent(self):
        self.log("Vent started")
        self.blinds_pos_tilt(self.BLIND_LIV_DOOR, 0, self.OPEN_HALF)
        self.blinds_pos_tilt(self.BLIND_BEDROOM, 0, self.OPEN_HALF)
        self.log("Vent ended")

    def blinds_living_morning(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 35, self.OPEN_HALF)

    def blinds_living_morning_hot(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 35, 0.2)

    def blinds_living_privacy(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 30, 0.1)

    def blinds_living_down_close(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 0, 0)

    def blinds_living_down_open(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 0, self.OPEN_HALF)

    def blinds_living_down_privacy(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 0, 0.7)

    def blinds_all_up(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 100, 0)
        self.blinds_pos_tilt(self.BLIND_LIV_DOOR, 100, 0)
        self.blinds_pos_tilt(self.BLIND_BEDROOM, 100, 0)
        self.blinds_pos_tilt(self.BLIND_SKLAD, 100, 0)
        self.blinds_pos_tilt(self.BLIND_STUDY, 100, 0)

    def blinds_all_down(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 0, 0)
        self.blinds_pos_tilt(self.BLIND_LIV_DOOR, 0, 0)
        self.blinds_pos_tilt(self.BLIND_BEDROOM, 0, 0)
        self.blinds_pos_tilt(self.BLIND_SKLAD, 0, 0)
        self.blinds_pos_tilt(self.BLIND_STUDY, 0, 0)

    def blinds_tilt_open(self):
        self.blinds_tilt(self.BLIND_LIV_BIG, self.OPEN_HALF)
        self.blinds_tilt(self.BLIND_LIV_DOOR, self.OPEN_HALF)
        self.blinds_tilt(self.BLIND_BEDROOM, self.OPEN_HALF)
        self.blinds_tilt(self.BLIND_SKLAD, self.OPEN_HALF)
        self.blinds_tilt(self.BLIND_STUDY, self.OPEN_HALF)

    def blinds_tilt_close(self):
        self.blinds_tilt(self.BLIND_LIV_BIG, 0)
        self.blinds_tilt(self.BLIND_LIV_DOOR, 0)
        self.blinds_tilt(self.BLIND_BEDROOM, 0)
        self.blinds_tilt(self.BLIND_SKLAD, 0)
        self.blinds_tilt(self.BLIND_STUDY, 0)

    def blinds_down_open(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 0, self.OPEN_HALF)
        self.blinds_pos_tilt(self.BLIND_BEDROOM, 0, self.OPEN_HALF)
        self.blinds_pos_tilt(self.BLIND_SKLAD, 0, self.OPEN_HALF)
        self.blinds_pos_tilt(self.BLIND_STUDY, 0, self.OPEN_HALF)

    def blinds_all_down_open(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 0, self.OPEN_HALF)
        self.blinds_pos_tilt(self.BLIND_LIV_DOOR, 0, self.OPEN_HALF)
        self.blinds_pos_tilt(self.BLIND_BEDROOM, 0, self.OPEN_HALF)
        self.blinds_pos_tilt(self.BLIND_SKLAD, 0, self.OPEN_HALF)
        self.blinds_pos_tilt(self.BLIND_STUDY, 0, self.OPEN_HALF)

    def blinds_morning(self):
        self.blinds_living_morning()
        self.blinds_pos_tilt(self.BLIND_LIV_DOOR, 100, 0)
        self.blinds_pos_tilt(self.BLIND_BEDROOM, 100, 0)
        self.blinds_pos_tilt(self.BLIND_SKLAD, 0, self.OPEN_HALF)
        self.blinds_pos_tilt(self.BLIND_STUDY, 0, self.OPEN_HALF)

    def blinds_pos_tilt(self, blind, pos, tilt):
        blind_rec = self.blinds[blind]
        blind_host = blind_rec["ip_address"]

        data = {"id": 1, "method": "Script.Eval", "params": {"id": 1, "code": f"posAndTilt({pos}, {tilt})"}}
        response = requests.post(
            f"http://{blind_host}/rpc", data=json.dumps(data), headers={"Content-Type": "application/json"}
        )
        self.log(f"Req: {blind_host}, data: {json.dumps(data)}, response: {response}")

    def blinds_tilt(self, blind, tilt):
        blind_rec = self.blinds[blind]
        blind_host = blind_rec["ip_address"]

        data = {"id": 1, "method": "Script.Eval", "params": {"id": 1, "code": f"tilt({tilt})"}}
        response = requests.post(
            f"http://{blind_host}/rpc", data=json.dumps(data), headers={"Content-Type": "application/json"}
        )
        self.log(f"Req: {blind_host}, data: {json.dumps(data)}, response: {response}")
