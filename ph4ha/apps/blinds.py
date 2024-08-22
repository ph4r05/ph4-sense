import datetime
import json
from datetime import time
from enum import Enum, auto
from typing import Optional

import hassapi as hass
import requests


class BlindsState(Enum):
    INITIAL = auto()
    MORNING_SCHEME = auto()
    AFTERNOON_UP = auto()
    PRIVACY_MODE = auto()
    NIGHT_MODE = auto()


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
    ALL_BLINDS = [BLIND_LIV_BIG, BLIND_LIV_DOOR, BLIND_BEDROOM, BLIND_STUDY, BLIND_SKLAD]
    OPEN_HALF = 0.9

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.blinds = None
        self.weekdays_open_time = None
        self.guest_weekdays_open_time = None
        self.guest_mode: bool = False
        self.automation_enabled: bool = True
        self.bedroom_automation_enabled: bool = True
        self.next_dusk_time = None

        self.field_weekdays_open_time = None
        self.field_guest_mode = None
        self.field_automation_enabled = None
        self.field_guest_weekdays_open_time = None
        self.field_bedroom_automation_enabled = None
        self.field_weekend_open_time = None
        self.field_sunset_offset_time = None
        self.field_full_open_time = None
        self.field_full_close_time = None

    def initialize(self):
        self.blinds = {x["name"]: x for x in self.args["blinds"]}
        self.field_weekdays_open_time = self.args["weekdays_open_time"]
        self.field_guest_weekdays_open_time = self.args["guest_weekdays_open_time_input"]
        self.field_guest_mode = self.args["guest_mode_input"]
        self.field_automation_enabled = self.args["automation_enabled_input"]
        self.field_bedroom_automation_enabled = self.args["bedroom_automation_enabled"]
        # self.field_weekend_open_time = self.args["weekend_open_time_input"]
        # self.field_sunset_offset_time = self.args["sunset_offset_time_input"]
        # self.field_full_open_time = self.args["full_open_time_input"]
        # self.field_full_close_time = self.args["full_close_time_input"]

        # Set initial blind open time
        self.update_blind_open_time()
        self.update_blind_open_time_guest()
        self.update_blind_guest_mode()
        self.update_blind_automation_enabled()
        self.update_blind_bedroom_automation_enabled()
        self.update_dusk_time()

        # Listen for changes to the input_datetime entity
        self.listen_state(self.update_blind_open_time, self.field_weekdays_open_time)
        self.listen_state(self.update_blind_open_time_guest, self.field_guest_weekdays_open_time)
        self.listen_state(self.update_blind_guest_mode, self.field_guest_mode)
        self.listen_state(self.update_blind_automation_enabled, self.field_automation_enabled)
        self.listen_state(self.update_blind_bedroom_automation_enabled, self.field_bedroom_automation_enabled)

        # Listen to scene changes
        self.listen_event(self.scene_activated, "call_service", domain="scene", service="turn_on")

        # Daily update new dusk time
        self.run_daily(self.update_dusk_time(), time(hour=0, minute=0))

        # TODO: separate bedroom - add another timer, bedroom mode.
        # TODO: dusk timer, sensor.sun_next_dusk

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

        self.log(f"initialized, {self.weekdays_open_time=}, {self.guest_mode=}")

    def update_dusk_time(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")

        dusk_time_str = self.get_state("sensor.sun_next_dusk")
        if dusk_time_str is None:
            self.log("Failed to retrieve dusk time state.")
            return

        try:
            self.log(f"{dusk_time_str=}")
            self.next_dusk_time = datetime.datetime.fromisoformat(dusk_time_str.replace("Z", "+00:00"))
            self.log(f"{self.next_dusk_time=}")
        except Exception as e:
            self.log(f"Failed to retrieve dusk time state: {e}")

    def update_blind_open_time(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        weekday_blind_open_time = self.get_state(self.field_weekdays_open_time)

        if weekday_blind_open_time is None:
            self.log("Failed to retrieve weekday_blind_open_time state.")
        else:
            self.log(f"Weekday Blind Open Time updated: {weekday_blind_open_time}")

            self.weekdays_open_time = self.parse_time(weekday_blind_open_time)
            self.log(f"{self.weekdays_open_time=}")

            # Cancel any previously scheduled runs to avoid duplication
            # self.cancel_timers()

            # Schedule the blind open event at the new time
            # self.run_daily(self.open_blinds, self.weekdays_open_time)

    def update_blind_open_time_guest(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        open_time = self.get_state(self.field_guest_weekdays_open_time)

        if open_time is None:
            self.log(f"Failed to retrieve {self.field_guest_weekdays_open_time} state.")
        else:
            self.guest_weekdays_open_time = self.parse_time(open_time)
            self.log(f"{self.guest_weekdays_open_time=}")

    def update_blind_guest_mode(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.guest_mode = self.to_bool(self.get_state(self.field_guest_mode))
        self.log(f"{self.guest_mode=}")

    def update_blind_automation_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.automation_enabled = self.to_bool(self.get_state(self.field_guest_mode))
        self.log(f"{self.automation_enabled=}")

    def update_blind_bedroom_automation_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.bedroom_automation_enabled = self.to_bool(self.get_state(self.field_guest_mode))
        self.log(f"{self.bedroom_automation_enabled=}")

    def scene_activated(self, event_name, data, kwargs):
        # Extract the scene ID or entity ID
        scene_id = data.get("service_data", {}).get("entity_id")
        self.log(f"scene_activated: {scene_id}")

        scenes = scene_id if isinstance(scene_id, list) else [scene_id]
        for scene in scenes:
            self.handle_scene(scene)

    def handle_scene(self, scene_id):
        if scene_id == "scene.blinds_vent":
            self.handle_vent()
        elif scene_id == "scene.blinds_vent_bedroom":
            self.blinds_vent_bedroom()
        elif scene_id == "scene.blinds_vent_livingroom":
            self.blinds_vent_livingroom()
        elif scene_id == "scene.blinds_living_morning":
            self.blinds_living_morning()
        elif scene_id == "scene.blinds_living_morning_hot":
            self.blinds_living_morning_hot()
        elif scene_id == "scene.blinds_living_privacy":
            self.blinds_living_privacy()
        elif scene_id == "scene.blinds_all_up":
            self.blinds_all_up()
        elif scene_id == "scene.blinds_all_down":
            self.blinds_all_down()
        elif scene_id == "scene.blinds_tilt_open":
            self.blinds_tilt_open()
        elif scene_id == "scene.blinds_tilt_close":
            self.blinds_tilt_close()
        elif scene_id == "scene.blinds_down_open":
            self.blinds_down_open()
        elif scene_id == "scene.blinds_all_down_open":
            self.blinds_all_down_open()
        elif scene_id == "scene.blinds_morning":
            self.blinds_morning()
        elif scene_id == "scene.blinds_morning_context":
            self.blinds_morning_context()
        elif scene_id == "scene.blinds_living_down_close":
            self.blinds_living_down_close()
        elif scene_id == "scene.blinds_living_down_open":
            self.blinds_living_down_open()
        elif scene_id == "scene.blinds_living_down_privacy":
            self.blinds_living_down_privacy()
        elif scene_id.startswith("scene.blinds_vent_"):
            self.handle_scene_template(scene_id, 0, self.OPEN_HALF)
        elif scene_id.startswith("scene.blinds_close_"):
            self.handle_scene_template(scene_id, 0, 0)
        elif scene_id.startswith("scene.blinds_open_"):
            self.handle_scene_template(scene_id, 100, 0)
        elif scene_id.startswith("scene.blinds_tilt_open_"):
            self.handle_scene_template(scene_id, None, self.OPEN_HALF)
        elif scene_id.startswith("scene.blinds_tilt_close_"):
            self.handle_scene_template(scene_id, None, 0)
        else:
            self.log(f"Scene {scene_id} not found")

    def handle_scene_template(self, scene_id, pos: Optional[float], tilt: Optional[float]):
        for bld in self.ALL_BLINDS:
            bld_low = bld.lower()
            if scene_id.endswith(f"_{bld_low}"):
                self.blind_move(bld, pos, tilt)

    def handle_vent(self):
        self.blinds_pos_tilt(self.BLIND_LIV_DOOR, 0, self.OPEN_HALF)
        self.blinds_pos_tilt(self.BLIND_BEDROOM, 0, self.OPEN_HALF)

    def blinds_vent_bedroom(self):
        self.blinds_pos_tilt(self.BLIND_BEDROOM, 0, self.OPEN_HALF)

    def blinds_vent_livingroom(self):
        self.blinds_pos_tilt(self.BLIND_LIV_DOOR, 0, self.OPEN_HALF)

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
        self.blinds_pos_tilt(self.BLIND_STUDY, 0, self.OPEN_HALF)
        if not self.guest_mode:
            self.blinds_pos_tilt(self.BLIND_SKLAD, 0, self.OPEN_HALF)

    def blinds_morning_context(self):
        if not self.automation_enabled:
            self.log("Automation disabled")
            return

        self.blinds_living_morning()
        self.blinds_pos_tilt(self.BLIND_LIV_DOOR, 100, 0)
        self.blinds_pos_tilt(self.BLIND_STUDY, 0, self.OPEN_HALF)

        if not self.guest_mode:
            self.blinds_pos_tilt(self.BLIND_SKLAD, 0, self.OPEN_HALF)

        if self.bedroom_automation_enabled:
            self.blinds_pos_tilt(self.BLIND_BEDROOM, 100, 0)

    def blind_move(self, blind, pos: Optional[float], tilt: float):
        if pos is None:
            self.blinds_tilt(blind, tilt)
        else:
            self.blinds_pos_tilt(blind, pos, tilt)

    def blinds_pos_tilt(self, blind, pos, tilt):
        data = {"id": 1, "method": "Script.Eval", "params": {"id": 1, "code": f"posAndTilt({pos}, {tilt})"}}
        return self.blinds_req(blind, data)

    def blinds_tilt(self, blind, tilt):
        data = {"id": 1, "method": "Script.Eval", "params": {"id": 1, "code": f"tilt({tilt})"}}
        return self.blinds_req(blind, data)

    def blinds_req(self, blind, data):
        blind_rec = self.blinds[blind]
        blind_host = blind_rec["ip_address"]
        response = requests.post(
            f"http://{blind_host}/rpc", data=json.dumps(data), headers={"Content-Type": "application/json"}
        )
        self.log(f"Req: {blind_host}, data: {json.dumps(data)}, response: {response}")
        return response

    def to_bool(self, inp):
        return inp == "on"
