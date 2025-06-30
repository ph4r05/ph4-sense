import datetime
import json
from datetime import time
from enum import Enum, auto
from typing import Any, Dict, Optional

import appdaemon.plugins.hass.hassapi as hass
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
    TODO: add new webhook to listen for all manual blinds movements. collect it
    """

    BLIND_LIV_BIG = "LivBig"
    BLIND_LIV_DOOR = "LivDoor"
    BLIND_BEDROOM = "Bedroom"
    BLIND_STUDY = "Study"
    BLIND_SKLAD = "Sklad"
    ALL_BLINDS = [BLIND_LIV_BIG, BLIND_LIV_DOOR, BLIND_BEDROOM, BLIND_STUDY, BLIND_SKLAD]
    OPEN_HALF = 0.9
    OPEN_PRIVACY = 0.7

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.blinds = None
        self.weekdays_open_time: Optional[datetime.time] = None
        self.weekends_open_time: Optional[datetime.time] = None
        self.guest_weekdays_open_time: Optional[datetime.time] = None
        self.guest_weekends_open_time: Optional[datetime.time] = None
        self.guest_mode: bool = False
        self.automation_enabled: bool = True
        self.bedroom_automation_enabled: bool = True
        self.night_venting_enabled: bool = True
        self.close_on_dawn_enabled: bool = True
        self.dusk_automation_enabled = True
        self.full_open_automation_enabled = None
        self.morning_automation_enabled = None
        self.morning_weekend_automation_enabled = None
        self.winter_mode: bool = False
        self.living_position: int = 40
        self.living_tilt: float = 0.2
        self.tilt: float = 0.9

        self.next_dawn_time: Optional[datetime.datetime] = None
        self.next_dusk_time: Optional[datetime.datetime] = None
        self.next_noon_time: Optional[datetime.datetime] = None
        self.next_sunrise_time: Optional[datetime.datetime] = None
        self.next_sunset_time: Optional[datetime.datetime] = None
        self.next_midnight_time: Optional[datetime.datetime] = None
        self.dusk_offset: datetime.time = datetime.time(hour=12)
        self.pre_dusk_offset: datetime.time = datetime.time(hour=12)
        self.pre_dawn_offset: datetime.time = datetime.time(hour=12)
        self.current_state = BlindsState.INITIAL
        self.morning_adjusted_time = None
        self.morning_timer = None
        self.pre_dusk_timer = None
        self.pre_dusk_adjusted_time = None
        self.dusk_timer = None
        self.dusk_adjusted_time = None
        self.dawn_timer = None
        self.dawn_adjusted_time = None
        self.last_morning_event: Optional[datetime.time] = None
        self.last_morning_context_event: Optional[datetime.time] = None

        self.field_weekdays_open_time = None
        self.field_weekends_open_time = None
        self.field_guest_mode = None
        self.field_automation_enabled = None
        self.field_guest_weekdays_open_time = None
        self.field_guest_weekends_open_time = None
        self.field_bedroom_automation_enabled = None
        self.field_dusk_offset = None
        self.field_dusk_automation_enabled = None
        self.field_full_open_automation_enabled = None
        self.field_night_venting_enabled = None
        self.field_close_on_dawn_enabled = None
        self.field_morning_automation_enabled = None
        self.field_morning_weekend_automation_enabled = None
        self.field_blinds_pre_dusk_offset = None
        self.field_sunset_offset_time = None
        self.field_full_open_time = None
        self.field_full_close_time = None
        self.field_winter_mode = None
        self.field_living_position = None
        self.field_living_tilt = None
        self.field_tilt = None

        self.holiday_checker = CzechHolidayChecker()

    def initialize(self):
        self.blinds = {x["name"]: x for x in self.args["blinds"]}
        self.field_weekdays_open_time = self.args["weekdays_open_time"]
        self.field_weekends_open_time = "input_datetime.blinds_weekends_open_time"
        self.field_guest_weekdays_open_time = self.args["guest_weekdays_open_time_input"]
        self.field_guest_weekends_open_time = "input_datetime.blinds_weekends_guest_open_time"
        self.field_guest_mode = self.args["guest_mode_input"]
        self.field_automation_enabled = self.args["automation_enabled_input"]
        self.field_bedroom_automation_enabled = self.args["bedroom_automation_enabled_input"]
        self.field_night_venting_enabled = self.args["night_venting_enabled_input"]
        self.field_close_on_dawn_enabled = self.args["close_on_dawn_enabled_input"]
        self.field_dusk_offset = self.args["dusk_offset_input"]
        self.field_dusk_automation_enabled = self.args["dusk_automation_enabled_input"]
        self.field_full_open_automation_enabled = self.args["full_open_automation_enabled_input"]
        self.field_blinds_pre_dusk_offset = self.args["blinds_pre_dusk_offset_input"]
        self.field_morning_automation_enabled = "input_boolean.blinds_morning_automation_enabled"
        self.field_morning_weekend_automation_enabled = "input_boolean.blinds_morning_weekend_automation_enabled"
        self.field_winter_mode = "input_boolean.blinds_winter_mode_enabled"
        self.field_living_position = "input_number.blinds_living_position"
        self.field_living_tilt = "input_number.blinds_living_tilt"
        self.field_tilt = "input_number.blinds_tilt"

        # self.field_sunset_offset_time = self.args["sunset_offset_time_input"]
        # self.field_full_open_time = self.args["full_open_time_input"]
        # self.field_full_close_time = self.args["full_close_time_input"]

        # Set initial blind open time
        self.update_weekdays_open_time()
        self.update_weekends_open_time()
        self.update_guest_weekdays_open_time_guest()
        self.update_guest_weekends_open_time_guest()
        self.update_blind_guest_mode()
        self.update_blind_automation_enabled()
        self.update_blind_dusk_automation_enabled()
        self.update_blind_bedroom_automation_enabled()
        self.update_blind_full_open_automation_enabled()
        self.update_blind_night_venting_enabled()
        self.update_blind_close_on_dawn_enabled()
        self.update_blind_dusk_offset()
        self.update_blind_pre_dusk_offset()
        self.update_blinds_morning_automation_enabled()
        self.update_blinds_morning_weekend_automation_enabled()
        self.update_winter_mode()
        self.update_living_position()
        self.update_living_tilt()
        self.update_tilt()
        self.update_sun_times()

        # Listen for changes to the input_datetime entity
        self.listen_state(self.update_weekdays_open_time, self.field_weekdays_open_time)
        self.listen_state(self.update_weekends_open_time, self.field_weekends_open_time)
        self.listen_state(self.update_guest_weekdays_open_time_guest, self.field_guest_weekdays_open_time)
        self.listen_state(self.update_guest_weekends_open_time_guest, self.field_guest_weekends_open_time)

        self.listen_state(self.update_blind_guest_mode, self.field_guest_mode)
        self.listen_state(self.update_blind_automation_enabled, self.field_automation_enabled)
        self.listen_state(self.update_blind_dusk_automation_enabled, self.field_dusk_automation_enabled)
        self.listen_state(self.update_blind_bedroom_automation_enabled, self.field_bedroom_automation_enabled)
        self.listen_state(self.update_blind_full_open_automation_enabled, self.field_full_open_automation_enabled)
        self.listen_state(self.update_blind_night_venting_enabled, self.field_night_venting_enabled)
        self.listen_state(self.update_blind_close_on_dawn_enabled, self.field_close_on_dawn_enabled)
        self.listen_state(self.update_blinds_morning_automation_enabled, self.field_morning_automation_enabled)
        self.listen_state(
            self.update_blinds_morning_weekend_automation_enabled, self.field_morning_weekend_automation_enabled
        )
        self.listen_state(self.update_winter_mode, self.field_winter_mode)
        self.listen_state(self.update_living_position, self.field_living_position)
        self.listen_state(self.update_living_tilt, self.field_living_tilt)
        self.listen_state(self.update_tilt, self.field_tilt)
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
            f", {self.dusk_offset=}, {self.pre_dusk_offset=}, {self.winter_mode=}"
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
            self.on_sun_recompute()
        except Exception as e:
            self.log(f"Failed to retrieve dusk time state: {e}, {dusk_time_str=}")

    def on_sun_recompute(self):
        self.on_morning_recompute()
        self.on_pre_dusk_recompute()
        self.on_dusk_recompute()
        self.on_dawn_recompute()

    def get_time_attribute(self, field: str) -> Optional[datetime.time]:
        try:
            val = self.get_state(field)
            return self.parse_time(val) if val is not None else None
        except Exception as e:
            self.log(f"Error parsing time attribute {field}, e: {e}")
        return None

    def update_weekdays_open_time(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update update_weekdays_open_time: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        parsed_time = self.get_time_attribute(self.field_weekdays_open_time)
        if parsed_time is None:
            self.log("Failed to retrieve weekday_blind_open_time state.")
            return

        self.weekdays_open_time = parsed_time
        self.log(f"{self.weekdays_open_time=}")
        self.on_morning_recompute()

    def update_weekends_open_time(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update update_weekends_open_time: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        parsed_time = self.get_time_attribute(self.field_weekends_open_time)
        if parsed_time is None:
            self.log("Failed to retrieve weekday_blind_open_time state.")
            return

        self.weekends_open_time = parsed_time
        self.log(f"{self.weekdays_open_time=}")
        self.on_morning_recompute()

    def update_guest_weekdays_open_time_guest(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update update_guest_weekdays_open_time_guest: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        open_time = self.get_time_attribute(self.field_guest_weekdays_open_time)

        if open_time is None:
            self.log(f"Failed to retrieve {self.field_guest_weekdays_open_time} state.")
            return

        self.guest_weekdays_open_time = open_time
        self.log(f"{self.guest_weekdays_open_time=}")
        self.on_morning_recompute()

    def update_guest_weekends_open_time_guest(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        open_time = self.get_time_attribute(self.field_guest_weekends_open_time)

        if open_time is None:
            self.log(f"Failed to retrieve {self.field_guest_weekends_open_time} state.")
            return

        self.guest_weekends_open_time = open_time
        self.log(f"{self.guest_weekends_open_time=}")
        self.on_morning_recompute()

    def update_blind_guest_mode(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update update_blind_guest_mode: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.guest_mode = self.to_bool(self.get_state(self.field_guest_mode))
        self.log(f"{self.guest_mode=}")

    def update_blind_automation_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update update_blind_automation_enabled: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.automation_enabled = self.to_bool(self.get_state(self.field_automation_enabled))
        self.log(f"{self.automation_enabled=}")
        self.on_morning_recompute()

    def update_blind_bedroom_automation_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(
            f"on_update update_blind_bedroom_automation_enabled: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}"
        )
        self.bedroom_automation_enabled = self.to_bool(self.get_state(self.field_bedroom_automation_enabled))
        self.log(f"{self.bedroom_automation_enabled=}")

    def update_blind_night_venting_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update update_blind_night_venting_enabled: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.night_venting_enabled = self.to_bool(self.get_state(self.field_night_venting_enabled))
        self.log(f"{self.night_venting_enabled=}")

    def update_blind_close_on_dawn_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update update_blind_close_on_dawn_enabled: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.close_on_dawn_enabled = self.to_bool(self.get_state(self.field_close_on_dawn_enabled))
        self.log(f"{self.close_on_dawn_enabled=}")

    def update_blind_dusk_offset(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update update_blind_dusk_offset: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        value = self.get_state(self.field_dusk_offset)

        if value is None:
            self.log("Failed to retrieve field_dusk_offset state.")
            return

        self.dusk_offset = self.parse_time(value)
        self.log(f"{self.dusk_offset=}")
        self.on_dusk_recompute()

    def update_blind_dusk_automation_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update update_blind_dusk_automation_enabled: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.dusk_automation_enabled = self.to_bool(self.get_state(self.field_dusk_automation_enabled))
        self.log(f"{self.dusk_automation_enabled=}")

    def update_blind_full_open_automation_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(
            f"on_update update_blind_full_open_automation_enabled: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}"
        )
        self.full_open_automation_enabled = self.to_bool(self.get_state(self.field_full_open_automation_enabled))
        self.log(f"{self.full_open_automation_enabled=}")

    def update_blinds_morning_automation_enabled(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(
            f"on_update update_blinds_morning_automation_enabled: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}"
        )
        self.morning_automation_enabled = self.to_bool(self.get_state(self.field_morning_automation_enabled))
        self.log(f"{self.morning_automation_enabled=}")
        self.on_morning_recompute()

    def update_blinds_morning_weekend_automation_enabled(
        self, entity=None, attribute=None, old=None, new=None, kwargs=None
    ):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.morning_weekend_automation_enabled = self.to_bool(
            self.get_state(self.field_morning_weekend_automation_enabled)
        )
        self.log(f"{self.morning_weekend_automation_enabled=}")
        self.on_morning_recompute()

    def update_blind_pre_dusk_offset(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        value = self.get_state(self.field_blinds_pre_dusk_offset)

        if value is None:
            self.log("Failed to retrieve field_blinds_pre_dusk_offset state.")
            return

        self.pre_dusk_offset = self.parse_time(value)
        self.log(f"{self.pre_dusk_offset=}")
        self.on_pre_dusk_recompute()

    def update_winter_mode(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        self.winter_mode = self.to_bool(self.get_state(self.field_winter_mode))
        self.log(f"{self.winter_mode=}")
        self.on_sun_recompute()

    def update_living_position(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        tmp_pos = try_fnc(lambda: self.get_state(self.field_living_position))
        if tmp_pos is not None:
            self.living_position = tmp_pos
        self.log(f"{self.living_position=}")

    def update_living_tilt(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        tmp_pos = try_fnc(lambda: self.get_state(self.field_living_tilt))
        if tmp_pos is not None:
            self.living_tilt = tmp_pos
        self.log(f"{self.living_tilt=}")

    def update_tilt(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        self.log(f"on_update: {entity=}, {attribute=}, {old=}, {new=}, {kwargs=}")
        tmp = try_fnc(lambda: self.get_state(self.field_tilt))
        if tmp is not None:
            self.tilt = tmp
        self.log(f"{self.tilt=}")

    def on_morning_recompute(self):
        """Automation for mornings"""
        # TODO: implement, weekend mode, guest mode, away mode
        try:
            # Scheduling can happen in any time, it is needed to determine if the scheduling is for today or tomorrow.
            # by the given day it is needed to determine if it is holiday or not and use corresponding open times
            now = datetime.datetime.now()
            tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
            is_holiday = [  # today, tomorrow
                self.holiday_checker.is_weekend_or_holiday(now),
                self.holiday_checker.is_weekend_or_holiday(tomorrow),
            ]

            open_times_all = [  # today, tomorrow
                self.weekends_open_time if is_holiday[0] else self.weekdays_open_time,
                self.weekends_open_time if is_holiday[1] else self.weekdays_open_time,
            ]

            # open_times_guest = (
            #     [  # today, tomorrow
            #         self.guest_weekends_open_time if is_holiday[0] else self.guest_weekdays_open_time,
            #         self.guest_weekends_open_time if is_holiday[1] else self.guest_weekdays_open_time,
            #     ]
            #     if self.guest_mode
            #     else open_times_all
            # )

            open_datetimes_all = [  # today, tomorrow
                self.get_datetimes(open_times_all[0]),
                self.get_datetimes(open_times_all[1], tomorrow),
            ]

            # open_datetimes_guest = [  # today, tomorrow
            #     self.get_datetimes(open_times_guest[0]),
            #     self.get_datetimes(open_times_guest[1], tomorrow),
            # ]

            plan_all_idx = int(open_datetimes_all[0] < now)
            # plan_guest_idx = int(open_datetimes_all[0] < now)

            adjusted_time = open_datetimes_all[plan_all_idx]
            self.log(
                f"Scheduling event for morning at {plan_all_idx=}, {adjusted_time=}, {self.morning_automation_enabled=},"
                f" {self.automation_enabled=}"
            )

            if self.morning_timer is not None:
                self.try_cancel_timer(self.morning_timer)
                self.log("Previous morning timer canceled.")

            self.morning_adjusted_time = adjusted_time
            self.morning_timer = self.run_at(self.blinds_morning_context_automated, adjusted_time)
            # self.set_state("input_datetime.blinds_morning_final", state=self.fmt_datetime(adjusted_time))
        except Exception as e:
            self.log(f"Error in morning recomputation: {e}")

    def compute_evening_mode_dusk_timer(self):
        # TODO: maybe (dusk + (midnight - dusk) / 2) in summer
        target_time = self.next_sunset_time if self.winter_mode else self.next_dusk_time
        total_offset = self.get_timedelta_offset(self.dusk_offset)
        adjusted_dusk_time = target_time + total_offset
        return adjusted_dusk_time, total_offset

    def on_dusk_recompute(self):
        try:
            adjusted_dusk_time, total_offset = self.compute_evening_mode_dusk_timer()
            self.log(
                f"Scheduling event for dusk at {adjusted_dusk_time}, {total_offset=}"
                f", {self.dusk_automation_enabled=}, {self.automation_enabled}"
            )

            if self.dusk_timer is not None:
                self.try_cancel_timer(self.dusk_timer)
                self.log("Previous dusk timer canceled.")

            self.dusk_adjusted_time = adjusted_dusk_time
            self.dusk_timer = self.run_at(self.blinds_on_dusk_event, adjusted_dusk_time)
            self.set_state("input_datetime.blinds_dusk_final", state=self.fmt_datetime(adjusted_dusk_time))
        except Exception as e:
            self.log(f"Error in dusk recomputation: {e}")

    def compute_noon_full_open_theme_pre_dusk_timer(self):
        target_time = self.next_sunset_time if self.winter_mode else self.next_dusk_time
        total_offset = self.get_timedelta_offset(self.pre_dusk_offset)
        time_diff = (
            datetime.datetime(year=2000, day=1, month=1, hour=target_time.hour, minute=target_time.minute)
            - datetime.datetime(
                year=2000, day=1, month=1, hour=self.next_noon_time.hour, minute=self.next_noon_time.minute
            )
        ) / 2

        adjusted_pre_dusk_time = target_time - time_diff + total_offset
        return adjusted_pre_dusk_time, time_diff, total_offset

    def on_pre_dusk_recompute(self):
        """Pre-dusk theme to full open blinds to maximize natural light"""
        try:
            adjusted_pre_dusk_time, time_diff, total_offset = self.compute_noon_full_open_theme_pre_dusk_timer()
            self.log(
                f"Scheduling event for pre-dusk at {adjusted_pre_dusk_time}, {total_offset=}, {time_diff=}"
                f", {self.full_open_automation_enabled=}, {self.automation_enabled=}"
            )

            if self.pre_dusk_timer is not None:
                self.try_cancel_timer(self.pre_dusk_timer)
                self.log("Previous pre-dusk timer canceled.")

            self.pre_dusk_adjusted_time = adjusted_pre_dusk_time
            self.pre_dusk_timer = self.run_at(self.blinds_on_pre_dusk_event, adjusted_pre_dusk_time)
            self.set_state("input_datetime.blinds_pre_dusk_final", state=self.fmt_datetime(adjusted_pre_dusk_time))
        except Exception as e:
            self.log(f"Error in pre-dusk recomputation: {e}")

    def compute_adjusted_pre_dawn_time(self):
        total_offset = self.get_timedelta_offset(self.pre_dawn_offset)
        adjusted_pre_dawn_time = self.next_dawn_time + total_offset
        return adjusted_pre_dawn_time, total_offset

    def on_dawn_recompute(self):
        """Full close to prevent morning light from waking people up"""
        try:
            adjusted_pre_dawn_time, total_offset = self.compute_adjusted_pre_dawn_time()
            self.log(
                f"Scheduling event for pre-dawn at {adjusted_pre_dawn_time},"
                f", {self.full_open_automation_enabled=}, {self.automation_enabled=}"
            )

            if self.dawn_timer is not None:
                self.try_cancel_timer(self.dawn_timer)
                self.log("Previous dawn_timer timer canceled.")

            self.dawn_adjusted_time = adjusted_pre_dawn_time
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
        elif scene_id == "scene.blinds_living_morning_tilt":
            self.blinds_living_morning_tilt()
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
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, self.living_position, self.OPEN_HALF)

    def blinds_living_morning_hot(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, self.living_position, 0.2)

    def blinds_living_morning_tilt(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, self.living_position, self.living_tilt)

    def blinds_living_privacy(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 30, 0.1)

    def blinds_living_down_close(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 0, 0)

    def blinds_living_down_open(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 0, self.OPEN_HALF)

    def blinds_living_down_privacy(self):
        self.blinds_pos_tilt(self.BLIND_LIV_BIG, 0, self.OPEN_PRIVACY)

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
        self.last_morning_event = datetime.datetime.now()
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

        self.last_morning_context_event = datetime.datetime.now()
        self.blinds_living_morning()
        self.blinds_pos_tilt(self.BLIND_LIV_DOOR, 100, 0)
        self.blinds_pos_tilt(self.BLIND_STUDY, 0, self.OPEN_HALF)

        if not self.guest_mode:
            self.blinds_pos_tilt(self.BLIND_SKLAD, 0, self.OPEN_HALF)

        if self.bedroom_automation_enabled:
            self.blinds_pos_tilt(self.BLIND_BEDROOM, 100, 0)

    def blinds_morning_context_automated(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        if not self.morning_automation_enabled:
            self.log("Morning automation disabled")
            return

        if self.happened_already(self.last_morning_context_event):
            self.log("Morning context already happened")
            return

        if self.happened_already(self.last_morning_event):
            self.log("Morning already happened")
            return

        return self.blinds_morning_context()

    def blinds_on_dusk_event(self, entity=None, attribute=None, old=None, new=None, kwargs=None):
        if not self.dusk_automation_enabled or not self.automation_enabled:
            self.log(f"Dusk automation disabled, {self.dusk_automation_enabled=}, {self.automation_enabled=}")
            return
        self.blinds_living_down_privacy()
        self.blinds_pos_tilt(self.BLIND_SKLAD, 0, self.OPEN_PRIVACY)
        self.blinds_pos_tilt(self.BLIND_STUDY, 0, self.OPEN_PRIVACY)
        if self.winter_mode:
            self.blinds_pos_tilt(self.BLIND_BEDROOM, 0, self.OPEN_PRIVACY)

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

    def blinds_tilt(self, blind, tilt):
        if self.is_blind_v2(blind):
            return self.blinds_pos_tilt_v2(blind, tilt=self.tilt2slat(tilt))
        else:
            return self.blinds_tilt_v1(blind, tilt=tilt)

    def blinds_pos_tilt(self, blind, pos, tilt):
        if self.is_blind_v2(blind):
            return self.blinds_pos_tilt_v2(blind, pos=pos, tilt=self.tilt2slat(tilt))
        else:
            return self.blinds_pos_tilt_v1(blind, pos=pos, tilt=tilt)

    def is_blind_v2(self, blind):
        blind_rec = self.blinds[blind]
        return bool(blind_rec.get("tilt", 0))

    def blinds_pos_tilt_v1(self, blind, pos, tilt):
        data = {"id": 1, "method": "Script.Eval", "params": {"id": 1, "code": f"posAndTilt({pos}, {tilt})"}}
        return self.blinds_req(blind, data)

    def blinds_tilt_v1(self, blind, tilt):
        data = {"id": 1, "method": "Script.Eval", "params": {"id": 1, "code": f"tilt({tilt})"}}
        return self.blinds_req(blind, data)

    @classmethod
    def tilt2slat(cls, tilt: Optional[float]) -> Optional[float]:
        if tilt is None:
            return None
        middle = 60.0
        res = middle + ((tilt - cls.OPEN_HALF) / cls.OPEN_HALF) * middle
        return int(max(0.0, min(100.0, res)))

    def blinds_pos_tilt_v2(self, blind, pos: Optional[float] = None, tilt: Optional[float] = None):
        payload: Dict[str, Any] = {"id": 0}
        if pos is not None:
            payload["pos"] = int(float(pos))
        if tilt is not None:
            payload["slat_pos"] = int(float(tilt))
        data = {"id": 1, "method": "Cover.GoToPosition", "params": payload}
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

    def get_timedelta_offset(self, offset: datetime.time) -> datetime.timedelta:
        """Computes timedelta from a datetime.time, centered around 12:00, i.e., 13:00 -> +1h, 11:00 -> -1h"""
        return datetime.timedelta(minutes=60 * offset.hour + offset.minute - 12 * 60)

    def get_datetimes(self, inp: datetime.time, now: Optional[datetime.datetime] = None) -> datetime.datetime:
        now = now or datetime.datetime.now()
        return datetime.datetime(year=now.year, month=now.month, day=now.day, hour=inp.hour, minute=inp.minute)

    def try_cancel_timer(self, timer):
        try:
            self.cancel_timer(timer)
        except Exception as e:
            self.log(f"Try cancel timer failed: {timer=}, {e=}")

    def happened_already(self, event_time: Optional[datetime.datetime]) -> bool:
        return event_time < datetime.datetime.now() if event_time else False


def try_fnc(x, msg=None):
    try:
        return x()
    except Exception as e:
        print(f'Err {msg or ""}: {e}')


class CzechHolidayChecker:
    def __init__(self):
        # Define fixed-date public holidays in the Czech Republic
        self.fixed_holidays = {
            (1, 1),  # New Year's Day / Restoration Day of the Independent Czech State
            (5, 1),  # Labour Day
            (5, 8),  # Liberation Day
            (7, 5),  # Saints Cyril and Methodius Day
            (7, 6),  # Jan Hus Day
            (9, 28),  # Czech Statehood Day
            (10, 28),  # Independent Czechoslovak State Day
            (11, 17),  # Struggle for Freedom and Democracy Day
            (12, 24),  # Christmas Eve
            (12, 25),  # Christmas Day
            (12, 26),  # St. Stephen's Day
        }

    def is_weekend(self, date: datetime.date) -> bool:
        """Check if the date is a Saturday (5) or Sunday (6)."""
        return date.weekday() >= 5

    def is_fixed_holiday(self, date: datetime.date) -> bool:
        """Check if the date is a fixed-date public holiday."""
        return (date.month, date.day) in self.fixed_holidays

    def calculate_easter(self, year: int) -> datetime.date:
        """
        Calculate the date of Easter Sunday for a given year using the Anonymous Gregorian algorithm.
        """
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        holl = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * holl) // 451
        month = (h + holl - 7 * m + 114) // 31
        day = ((h + holl - 7 * m + 114) % 31) + 1
        return datetime.date(year, month, day)

    def is_easter_related_holiday(self, date: datetime.date) -> bool:
        """Check if the date is Good Friday or Easter Monday."""
        easter_sunday = self.calculate_easter(date.year)
        good_friday = easter_sunday - datetime.timedelta(days=2)
        easter_monday = easter_sunday + datetime.timedelta(days=1)
        return date in {good_friday, easter_monday}

    def is_weekend_or_holiday(self, date: datetime.date) -> bool:
        """
        Check if a given date is a weekend or a public holiday in the Czech Republic.
        """
        return self.is_weekend(date) or self.is_fixed_holiday(date) or self.is_easter_related_holiday(date)
