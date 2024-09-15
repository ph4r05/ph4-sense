// State definitions
const State = {
  IDLE: "IDLE",
  STOPPING: "STOPPING",
  MOVING_TO_POSITION: "MOVING_TO_POSITION",
  TILTING: "TILTING",
  TILTING2: "TILTING2",
  TILTING_UPWARDS: "TILTING_UPWARDS",
};

const MIN_MOVEMENT_TO_KNOWN_STATE = 2; // move x% to get to a known angle
const TIME_CLOSING_TO_KNOWN_STATE = 1.5;  // move x s downwards to get to a known state
const TIME_OPENING_TO_KNOWN_STATE = 1.5;  // move x s upwards to get to a known state
const TIME_TO_STRAIGHT_FROM_OPEN_STATE = 0.5;  // time to move down from open state to get blinds to straight angle
const TIME_TO_STRAIGHT_FROM_CLOSE_STATE = 0.9;  // time to move up from closed state to get blinds to straight angle
const ALLOW_DOWN_OPTIMIZATION = true;

let currentState = State.IDLE;
let currentOperation = null;
let currentCoverStatus = null;  // loaded by Cover.GetStatus, loadStatus() function
let logicalOpClock = 0;
let latestMovementEvent = null;

function max(a, b) {
  return a > b ? a : b;
}

function min(a, b) {
  return a < b ? a : b;
}

function recomputeTiltForSwitchedDirection(duration) {
  // TIME_TO_STRAIGHT_FROM_CLOSE_STATE -> TIME_TO_STRAIGHT_FROM_OPEN_STATE
  const x1 = TIME_TO_STRAIGHT_FROM_CLOSE_STATE, y1 = TIME_TO_STRAIGHT_FROM_OPEN_STATE;

  // Calculate slope (m) and intercept (b) for the line equation y = mx + b
  const slope = (0 - y1) / (TIME_OPENING_TO_KNOWN_STATE - x1);
  const intercept = y1 - slope * x1;

  // Use the linear equation to map the value
  const res = slope * duration + intercept;

  // Make sure movement is in the [0, TIME_OPENING_TO_KNOWN_STATE] interval
  return max(0, min(TIME_OPENING_TO_KNOWN_STATE, res))
}

function transitionState(newState, operation) {
  currentState = newState;
  currentOperation = operation;
  print("State transition to ", currentState, "with operation ", operation);
}

function performTiltClosing(){
  Shelly.call("Cover.Close", {
      id: 0,
      duration: TIME_CLOSING_TO_KNOWN_STATE,
    }, function (r, error_code, error_message, userdata1) {
      if (r !== null){
        transitionState(State.IDLE, {error: error_code})
      }
    });
}

function performTiltOpening(){
  Shelly.call("Cover.Open", {
      id: 0,
      duration: TIME_OPENING_TO_KNOWN_STATE,
    }, function (r, error_code, error_message, userdata1) {
      if (r !== null){
        transitionState(State.IDLE, {error: error_code})
      }
    });
}

function performTilt(duration) {
  Shelly.call("Cover.Open", {
    id: 0,
    duration: duration,
  }, function (r, error_code, error_message, userdata1) {
      if (r !== null){
        transitionState(State.IDLE, {error: error_code})
      }
    });
}

function performTiltDownwards(duration) {
  Shelly.call("Cover.Close", {
    id: 0,
    duration: duration,
  }, function (r, error_code, error_message, userdata1) {
      if (r !== null){
        transitionState(State.IDLE, {error: error_code})
      }
    });
}

function loadStatus(callback) {
  Shelly.call("Cover.GetStatus", { id: 0 }, function (r, error_code, error_message, userdata1) {
    print("posAndTilt status: ", JSON.stringify(r));
    currentCoverStatus = r
    callback()
  });
}

function processEvent() {
    if (currentOperation && currentOperation.clock) {
      if (currentOperation.clock < logicalOpClock) {
        print("Event for older operation, ignoring");
        return;
      }
    }

    switch (currentState) {
      case State.STOPPING:
      case State.IDLE:
        if (currentOperation) {
          const pos = currentOperation.pos;
          if (currentCoverStatus && Math.abs(currentCoverStatus.current_pos - pos) <= 1) {
            // We are in the position already
            print("[idle] In position already");
            transitionState(State.MOVING_TO_POSITION, currentOperation);
            processEvent();
          } else {
            // Move to the desired position
            print("[idle] Go to position");
            transitionState(State.MOVING_TO_POSITION, currentOperation);
            Shelly.call("Cover.GoToPosition", { id: 0, pos: pos });
          }
        }
        break;

      case State.MOVING_TO_POSITION:  // was moving to the position X and stopped, what next?
        const movementDiff = currentCoverStatus ? currentCoverStatus.current_pos - currentOperation.pos : null;
        if (movementDiff !== null && movementDiff >= MIN_MOVEMENT_TO_KNOWN_STATE) {
          // if blinds moved at least 2% downwards, TILTING will be skipped as the blinds angle is already known
          print("[mov] go to tilt; already down");
          transitionState(State.TILTING, currentOperation);
          return processEvent();
        } else if (ALLOW_DOWN_OPTIMIZATION && movementDiff !== null && movementDiff <= -2*MIN_MOVEMENT_TO_KNOWN_STATE) {
          // if blinds moved at least 2% upwards, TILTING will be skipped as the blinds angle is already known
          print("[mov] go to tilt up; already up");
          transitionState(State.TILTING_UPWARDS, currentOperation);
          return processEvent();
        } else {
          if (ALLOW_DOWN_OPTIMIZATION && movementDiff !== null && movementDiff < 0) { // went up
            print("[mov] tilting opening");
            transitionState(State.TILTING_UPWARDS, currentOperation);
            performTiltOpening();
          } else {
            print("[mov] tilting closing");
            transitionState(State.TILTING, currentOperation);
            performTiltClosing();
          }
        }
        break;

      case State.TILTING:  // was tilting and stopped, what next?
        if (currentOperation.tilt_duration < 0.05) {
          // Tilt is under the minimal threshold, no tilting will be done. Switch to the terminal state
          transitionState(State.TILTING2, currentOperation);
          return processEvent();
        }
        // Tilt by moving upwards from closed position given amount of time
        transitionState(State.TILTING2, currentOperation);
        performTilt(currentOperation.tilt_duration);
        break;

      case State.TILTING_UPWARDS:  // was tilting and stopped, what next?
        const newDuration = recomputeTiltForSwitchedDirection(currentOperation.tilt_duration);
        print("Optimizing by tilt down, original duration ", currentOperation.tilt_duration, ", recomputed ", newDuration);
        if (newDuration < 0.05) {
          // Tilt is under the minimal threshold, no tilting will be done. Switch to the terminal state
          transitionState(State.TILTING2, currentOperation);
          return processEvent();
        }
        // Tilt by moving downwards from open position given amount of time
        transitionState(State.TILTING2, currentOperation);
        performTiltDownwards(newDuration);
        break;

      case State.TILTING2:  // final tilt finished, what next?
        transitionState(State.IDLE, null);
        print("Tilting done.");
        break;
    }
}

// Set up a global event handler for all state transitions
Shelly.addEventHandler(function (event) {
  print("Global event handler: ", JSON.stringify(event));

  // Store last operation
  if (event.info) {
    if (event.info.event === "opening" || event.info.event === "closing") {
      print("Detected ongoing event", event.info.event)
      latestMovementEvent = event;
    } else if (event.info.event === "stopped" || event.info.event === "closed" || event.info.event === "opened") {
      print("Detected stopping event", event.info.event)
      latestMovementEvent = null;
    }
  }

  // Automation processing
  if (event.info && (event.info.event === "stopped" || event.info.event === "closed" || event.info.event === "opened")) {
    processEvent();
  }
}, null);

function isActiveMovementOngoing() {
  if (latestMovementEvent == null || !latestMovementEvent.info) {
    return false;
  }

  const ts = latestMovementEvent.info.ts;
  const curTime = Shelly.getComponentStatus("sys").unixtime;

  if (!ts || !curTime) {
    print("Invalid times", ts, curTime);
    return false;
  }

  return (curTime - ts) < 60;
}

function entryPoint(stop_state, transition_state, data) {
    loadStatus(function() {
      // Increment logical clock to ignore instructions from older calls
      logicalOpClock += 1;
      data.clock = logicalOpClock;

      // In the middle of the operation?
      if (currentState !== State.IDLE || isActiveMovementOngoing()) {
        print("entry: Active operation detected, stopping");
        transitionState(stop_state, data);
        const r = Shelly.call("Cover.Stop", { id: 0 }, function (r, error_code, error_message, userdata1) {
          // Callback to signalize finish. Let main handler handle this stopping event.
          print("Stop callback", r, error_code, error_message);
          if (currentCoverStatus && currentCoverStatus.state) {
            if (currentCoverStatus.state === 'open' || currentCoverStatus.state === 'closed') {
              // Callback won't be triggered
              print("Callback wont be triggered, transitioning")
              processEvent()
            }
          }
        });
        if (r != null) {
          print("Error on stop call");
          transitionState(transition_state, data);
          processEvent();
        }
      } else {
        transitionState(transition_state, data);
        processEvent();
      }
    })
}

function tilt(tilt_duration) {
  entryPoint(State.STOPPING, State.MOVING_TO_POSITION, {tilt_duration: tilt_duration})
}

function posAndTilt(pos, tilt_duration) {
  entryPoint(State.STOPPING, State.IDLE, { pos:pos, tilt_duration:tilt_duration })
}
