from datetime import datetime, timedelta

import hassapi as hass


class Venting(hass.Hass):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hum_sensor = None
        self.vent_switch = None

        # Timing control
        self.flip_history = []
        self.daily_flip_count = 0
        self.last_reset_time = datetime.now()
        self.next_possible_flip_time = datetime.now()

    def initialize(self):
        self.hum_sensor = self.args["hum_sensor"]
        self.vent_switch = self.args["vent_switch"]

        self.listen_state(self.humidity_changed, self.hum_sensor)
        self.log("initialized")

    def humidity_changed(self, entity, attribute, old, new, cb_args):
        self.log(f"Humidity change {entity} {old=} {new=}")

        current_time = datetime.now()

        # Reset daily count every 24 hours
        if current_time - self.last_reset_time >= timedelta(days=1):
            self.daily_flip_count = 0
            self.last_reset_time = current_time

        # Manage flip history for 10-minute window
        self.flip_history = [t for t in self.flip_history if current_time - t < timedelta(minutes=10)]

        if float(new) > 70:
            if (
                len(self.flip_history) < 3
                and current_time >= self.next_possible_flip_time
                and self.daily_flip_count < 15
            ):
                self.log(f"High humidity detected at {new}%! Venting.")
                self.turn_on(self.vent_switch)
                self.flip_history.append(current_time)
                self.daily_flip_count += 1

                if len(self.flip_history) >= 3:
                    self.next_possible_flip_time = current_time + timedelta(minutes=20)
                    self.log("Flip limit reached. Next possible flip time set.")

            elif current_time < self.next_possible_flip_time:
                self.log("Flip delayed: Cooling off period active.")
            elif self.daily_flip_count >= 15:
                self.log("Maximum daily flips reached, no more flipping allowed today.")
            elif float(new) <= self.humidity_threshold and self.get_state(self.switch) == "on":
                self.log(f"Humidity back to normal at {new}%. Turning off the dehumidifier.")
                self.turn_off(self.switch)
