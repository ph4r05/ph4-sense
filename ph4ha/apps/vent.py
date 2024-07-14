from datetime import datetime, timedelta

import hassapi as hass


class Venting(hass.Hass):
    """
    TODO: threshold + diff of two hum sensors.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hum_sensor = None
        self.vent_switch = None

        # Timing control
        self.flip_history = []
        self.humidity_threshold_value = 68
        self.segment_max_flips = 15
        self.segment_flip_count = 0
        self.last_reset_time = datetime.now()
        self.next_possible_flip_time = datetime.now()
        self.latest_measurement_time = None
        self.latest_measurement_value = None

    def initialize(self):
        self.hum_sensor = self.args["hum_sensor"]
        self.vent_switch = self.args["vent_switch"]

        self.run_every(self.timer_event, "now", 4 * 60)
        self.listen_state(self.humidity_changed, self.hum_sensor)
        self.log("initialized")

    def timer_event(self, kwargs):
        if self.latest_measurement_value is None or self.latest_measurement_time is None:
            return

        current_time = datetime.now()
        diff_last_measured = current_time - self.latest_measurement_time
        if diff_last_measured < timedelta(minutes=3):
            return

        self.on_humidity(self.latest_measurement_value)

    def humidity_changed(self, entity, attribute, old, new, cb_args):
        self.log(f"Humidity change {entity} {old=} {new=}")

        current_time = datetime.now()
        self.latest_measurement_time = current_time
        self.latest_measurement_value = new
        self.on_humidity(new)

    def on_humidity(self, humidity):
        current_time = datetime.now()

        # Reset daily count every 24 hours
        if current_time - self.last_reset_time >= timedelta(hours=8):
            self.segment_flip_count = 0
            self.last_reset_time = current_time

        # Manage flip history for 30-minute window
        self.flip_history = [t for t in self.flip_history if current_time - t < timedelta(minutes=30)]

        if float(humidity) > self.humidity_threshold_value:
            if self.flip_history and current_time - self.flip_history[-1] < timedelta(seconds=3 * 60 + 15):
                self.log(f"Not venting, previous is still in progress {current_time - self.flip_history[-1]}")

            elif len(self.flip_history) >= 10:
                self.next_possible_flip_time = current_time + timedelta(minutes=10)
                self.log("Flip limit reached. Next possible flip time set.")

            elif current_time >= self.next_possible_flip_time and self.segment_flip_count < self.segment_max_flips:
                self.log(f"High humidity detected at {humidity}%! Venting.")
                self.turn_on(self.vent_switch)
                self.flip_history.append(current_time)
                self.segment_flip_count += 1

            elif current_time < self.next_possible_flip_time:
                self.log("Flip delayed: Cooling off period active.")
            elif self.segment_flip_count >= self.segment_max_flips:
                self.log("Maximum segment flips reached, no more flipping allowed.")
            else:
                self.log("Flip limit reached. No more flipping allowed.")
