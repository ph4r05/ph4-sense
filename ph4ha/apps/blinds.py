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
    DUSK_MODE = auto()
    PRIVACY_MODE = auto()
    NIGHT_VENT = auto()
    NIGHT_MODE = auto()
    PRE_DAWN_MODE = auto()


class Blinds(hass.Hass):
    """
    TODO: collect manual state changes. manual state change cancels the next routine
    TODO: add pause automation toggle
    TODO: add sync - sets state appropriate for this time of a day
    TODO: is weekend? disable morning automation till 11:30, but how to detect if it was triggered already?
    TODO: add new webhook to listen for all manual blinds movements. collect it
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
        self.weekdays_open_time: Optional[datetime.time] = None
        self.guest_weekdays_open_time: Optional[datetime.time] = None
        self.guest_mode: bool = False
        self.automation_enabled: bool = True
        self.bedroom_automation_enabled: bool = True
        self.night_venting_enabled: bool = True
        self.close_on_dawn_enabled: bool = True
        self.next_dawn_time: Optional[datetime.datetime] = None
        self.next_dusk_time: Optional[datetime.datetime] = None
        self.next_noon_time: Optional[datetime.datetime] = None
        self.next_sunrise_time: Optional[datetime.datetime] = None
        self.next_sunset_time: Optional[datetime.datetime] = None
        self.next_midnight_time: Optional[datetime.datetime] = None
        self.dusk_offset: datetime.time = datetime.time(hour=12)
        self.pre_dusk_offset: datetime.time = datetime.time(hour=12)
        self.pre_dawn_offset: datetime.time = datetime.time(hour=12)
        self.dusk_automation_enabled = True
        self.current_state = BlindsState.INITIAL
        self.full_open_automation_enabled = None
        self.dusk_timer = None
        self.pre_dusk_timer = None
        self.dawn_timer = None

        self.field_weekdays_open_time = None
        self.field_guest_mode = None
        self.field_automation_enabled = None
        self.field_guest_weekdays_open_time = None
        self.field_bedroom_automation_enabled = None
        self.field_dusk_offset = None
        self.field_dusk_automation_enabled = None
        self.field_full_open_automation_enabled = None
        self.field_night_venting_enabled = None
        self.field_close_on_dawn_enabled = None
        self.field_blinds_pre_dusk_offset = None
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
        self.field_bedroom_automation_enabled = self.args["bedroom_automation_enabled_input"]
        self.field_night_venting_enabled = self.args["night_venting_enabled_input"]
        self.field_close_on_dawn_enabled = self.args["close_on_dawn_enabled_input"]
        self.field_dusk_offset = self.args["dusk_offset_input"]
        self.field_dusk_automation_enabled = self.args["dusk_automation_enabled_input"]
        self.field_full_open_automation_enabled = self.args["full_open_automation_enabled_input"]
        self.field_blinds_pre_dusk_offset = self.args["blinds_pre_dusk_offset_input"]

        # self.field_weekend_open_time = self.args["weekend_open_time_input"]
        # self.field_sunset_offset_time = self.args["sunset_offset_time_input"]
        # self.field_full_open_time = self.args["full_open_time_input"]
        # self.field_full_close_time = self.args["full_close_time_input"]

        # Set initial blind open time
        self.update_blind_open_time()
        self.update_blind_open_time_guest()
        self.update_blind_guest_mode()
        self.update_blind_automation_enabled()
        self.update_blind_dusk_automation_enabled()
        self.update_blind_bedroom_automation_enabled()
        self.update_blind_full_open_automation_enabled()
        self.update_blind_night_venting_enabled()
        self.update_blind_close_on_dawn_enabled()
        self.update_blind_dusk_offset()
        self.update_blind_pre_dusk_offset()
        self.update_sun_times()

        # Listen for changes to the input_datetime entity
        self.listen_state(self.update_blind_open_time, self.field_weekdays_open_time)
        self.listen_state(self.update_blind_open_time_guest, self.field_guest_weekdays_open_time)
        self.listen_state(self.update_blind_guest_mode, self.field_guest_mode)
        self.listen_state(self.update_blind_automation_enabled, self.field_automation_enabled)
        self.listen_state(self.update_blind_dusk_automation_enabled, self.field_dusk_automation_enabled)
        self.listen_state(self.update_blind_bedroom_automation_enabled, self.field_bedroom_automation_enabled)
        self.listen_state(self.update_blind_full_open_automation_enabled, self.field_full_open_automation_enabled)
        self.listen_state(self.update_blind_night_venting_enabled, self.field_night_venting_enabled)
        self.listen_state(self.update_blind_close_on_dawn_enabled, self.field_close_on_dawn_enabled)
        self.listen_state(self.update_blind_dusk_offset, self.field_dusk_offset)
        self.listen_state(self.update_blind_pre_dusk_offset, self.field_blinds_pre_dusk_offset)

        # Listen to scene changes
        self.listen_event(self.scene_activated, "call_service", domain="scene", service="turn_on")

        # Daily update new dusk time
        self.run_daily(self.update_sun_times, time(hour=1, minute=30))

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

        self.log(
            f"initialized, {self.weekdays_open_time=}, {self.guest_mode=}, now: {datetime.datetime.now()}"
            f", {self.full_open_automation_enabled=}, {self.dusk_automation_enabled=}"
            f", {self.bedroom_automation_enabled=}, {self.automation_enabled=}"
            f", {self.dusk_offset=}, {self.pre_dusk_offset=}"
        )

    def transition_function(self):
        pass

    def on_change_to_dusk(self):
        pass

    def on_change_to_morning(self):
        pass

    def on_change_to_night(self):
        pass

    def on_change_from_time(self):
        # Determine current state from the current time
        # E.g. if automation was disabled for a while or system is reconfigured
        # Find the next state in the timeline
        pass

    def update_sun_times(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")

        dusk_time_str = self.get_state("sensor.sun_next_dusk")
        if dusk_time_str is None:
            self.log("Failed to retrieve dusk time state.")
            return

        sun_next_noon_str = self.get_state("sensor.sun_next_noon")
        sun_next_midnight_str = self.get_state("sensor.sun_next_midnight")
        sun_next_dawn_str = self.get_state("sensor.sun_next_dawn")
        sun_next_sunrise_str = self.get_state("sensor.sun_next_rising")
        sun_next_sunset_str = self.get_state("sensor.sun_next_setting")
        try:
            self.next_dusk_time = datetime.datetime.fromisoformat(dusk_time_str.replace("Z", "+00:00"))
            self.next_noon_time = (
                datetime.datetime.fromisoformat(sun_next_noon_str.replace("Z", "+00:00"))
                if sun_next_noon_str is not None
                else self.next_noon_time
            )
            self.next_midnight_time = (
                datetime.datetime.fromisoformat(sun_next_midnight_str.replace("Z", "+00:00"))
                if sun_next_midnight_str is not None
                else self.next_midnight_time
            )
            self.next_dawn_time = (
                datetime.datetime.fromisoformat(sun_next_dawn_str.replace("Z", "+00:00"))
                if sun_next_dawn_str is not None
                else self.next_dawn_time
            )
            self.next_sunrise_time = (
                datetime.datetime.fromisoformat(sun_next_sunrise_str.replace("Z", "+00:00"))
                if sun_next_sunrise_str is not None
                else self.next_sunrise_time
            )
            self.next_sunset_time = (
                datetime.datetime.fromisoformat(sun_next_sunset_str.replace("Z", "+00:00"))
                if sun_next_sunset_str is not None
                else self.next_sunset_time
            )

            self.log(f"{self.next_dusk_time=}")
            self.log(f"{self.next_midnight_time=}")
            self.log(f"{self.next_noon_time=}")
            self.log(f"{self.next_dawn_time=}")
            self.log(f"{self.next_sunrise_time=}")
            self.log(f"{self.next_sunset_time=}")
            self.on_dusk_recompute()
            self.on_pre_dusk_recompute()
            self.on_dawn_recompute()
        except Exception as e:
            self.log(f"Failed to retrieve dusk time state: {e}, {dusk_time_str=}")

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
        self.automation_enabled = self.to_bool(self.get_state(self.field_automation_enabled))
        self.log(f"{self.automation_enabled=}")

    def update_blind_bedroom_automation_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.bedroom_automation_enabled = self.to_bool(self.get_state(self.field_bedroom_automation_enabled))
        self.log(f"{self.bedroom_automation_enabled=}")

    def update_blind_night_venting_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.night_venting_enabled = self.to_bool(self.get_state(self.field_night_venting_enabled))
        self.log(f"{self.night_venting_enabled=}")

    def update_blind_close_on_dawn_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.close_on_dawn_enabled = self.to_bool(self.get_state(self.field_close_on_dawn_enabled))
        self.log(f"{self.close_on_dawn_enabled=}")

    def update_blind_dusk_offset(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        value = self.get_state(self.field_dusk_offset)

        if value is None:
            self.log("Failed to retrieve field_dusk_offset state.")
            return

        self.dusk_offset = self.parse_time(value)
        self.log(f"{self.dusk_offset=}")
        self.on_dusk_recompute()

    def update_blind_dusk_automation_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.dusk_automation_enabled = self.to_bool(self.get_state(self.field_dusk_automation_enabled))
        self.log(f"{self.dusk_automation_enabled=}")

    def update_blind_full_open_automation_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.full_open_automation_enabled = self.to_bool(self.get_state(self.field_full_open_automation_enabled))
        self.log(f"{self.full_open_automation_enabled=}")

    def update_blind_pre_dusk_offset(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        value = self.get_state(self.field_blinds_pre_dusk_offset)

        if value is None:
            self.log("Failed to retrieve field_blinds_pre_dusk_offset state.")
            return

        self.pre_dusk_offset = self.parse_time(value)
        self.log(f"{self.pre_dusk_offset=}")
        self.on_pre_dusk_recompute()

    def on_dusk_recompute(self):
        try:
            # TODO: maybe to dusk + (midnight - dusk) / 2
            total_offset = datetime.timedelta(
                hours=self.dusk_offset.hour, minutes=self.dusk_offset.minute
            ) - datetime.timedelta(hours=12, minutes=0)
            adjusted_dusk_time = self.next_dusk_time + total_offset
            self.log(
                f"Scheduling event for dusk at {adjusted_dusk_time} with offset of {total_offset}"
                f", {self.dusk_automation_enabled=}, {self.automation_enabled}"
            )

            if self.dusk_timer is not None:
                self.cancel_timer(self.dusk_timer)
                self.log("Previous dusk timer canceled.")

            self.dusk_timer = self.run_at(self.blinds_on_dusk_event, adjusted_dusk_time)
            self.set_state("input_datetime.blinds_dusk_final", state=self.fmt_datetime(adjusted_dusk_time))
        except Exception as e:
            self.log(f"Error in dusk recomputation: {e}")

    def on_pre_dusk_recompute(self):
        try:
            total_offset = datetime.timedelta(
                hours=self.pre_dusk_offset.hour, minutes=self.pre_dusk_offset.minute
            ) - datetime.timedelta(hours=12, minutes=0)
            time_diff = (
                datetime.datetime(
                    year=2000, day=1, month=1, hour=self.next_dusk_time.hour, minute=self.next_dusk_time.minute
                )
                - datetime.datetime(
                    year=2000, day=1, month=1, hour=self.next_noon_time.hour, minute=self.next_noon_time.minute
                )
            ) / 2
            adjusted_pre_dusk_time = self.next_noon_time + time_diff + total_offset
            self.log(
                f"Scheduling event for pre-dusk at {adjusted_pre_dusk_time}, {total_offset=}, {time_diff=}"
                f", {self.full_open_automation_enabled=}, {self.automation_enabled=}"
            )

            if self.pre_dusk_timer is not None:
                self.cancel_timer(self.pre_dusk_timer)
                self.log("Previous pre-dusk timer canceled.")

            self.pre_dusk_timer = self.run_at(self.blinds_on_pre_dusk_event, adjusted_pre_dusk_time)
            self.set_state("input_datetime.blinds_pre_dusk_final", state=self.fmt_datetime(adjusted_pre_dusk_time))
        except Exception as e:
            self.log(f"Error in pre-dusk recomputation: {e}")

    def on_dawn_recompute(self):
        try:
            total_offset = datetime.timedelta(
                hours=self.pre_dawn_offset.hour, minutes=self.pre_dawn_offset.minute
            ) - datetime.timedelta(hours=12, minutes=0)
            adjusted_pre_dawn_time = self.next_dawn_time + total_offset
            self.log(
                f"Scheduling event for pre-dawn at {adjusted_pre_dawn_time}, {total_offset=}"
                f", {self.full_open_automation_enabled=}, {self.automation_enabled=}"
            )

            if self.dawn_timer is not None:
                self.cancel_timer(self.dawn_timer)
                self.log("Previous dawn_timer timer canceled.")

            self.dawn_timer = self.run_at(self.blinds_on_pre_dawn_event, adjusted_pre_dawn_time)
        except Exception as e:
            self.log(f"Error in pre-dusk recomputation: {e}")

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

    def blinds_on_dusk_event(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        if not self.dusk_automation_enabled or not self.automation_enabled:
            self.log(f"Dusk automation disabled, {self.dusk_automation_enabled=}, {self.automation_enabled=}")
            return
        self.blinds_living_down_privacy()

    def blinds_on_pre_dusk_event(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        if not self.full_open_automation_enabled or not self.automation_enabled:
            self.log(f"Pre Dusk automation disabled, {self.full_open_automation_enabled=}, {self.automation_enabled=}")
            return
        self.blinds_all_up()

    def blinds_on_pre_dawn_event(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        if not self.close_on_dawn_enabled or not self.automation_enabled:
            self.log(f"Pre Dawn automation disabled, {self.close_on_dawn_enabled=}, {self.automation_enabled=}")
            return
        self.blinds_all_down()

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

    def fmt_datetime(self, dtime):
        return dtime.strftime("%Y-%m-%d %H:%M:%S")
