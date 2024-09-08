// State definitions
const State = {
  IDLE: "IDLE",
  STOPPING: "STOPPING",
  STOPPING_TILT: "STOPPING_TILT",
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
let currentCoverStatus = null;

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
    switch (currentState) {
      case State.STOPPING:
        if (currentOperation) {
          const pos = currentOperation.pos;
          if (currentCoverStatus && currentCoverStatus.current_pos === pos) {
            transitionState(State.MOVING_TO_POSITION, currentOperation);
            processEvent();
          } else {
            transitionState(State.MOVING_TO_POSITION, currentOperation);
            Shelly.call("Cover.GoToPosition", { id: 0, pos: pos });
          }
        } else {
          transitionState(State.IDLE, null);
        }
        break;

      case State.MOVING_TO_POSITION:  // was moving to the position X and stopped, what next?
        const movementDiff = currentCoverStatus ? currentCoverStatus.current_pos - currentOperation.pos : null;
        if (movementDiff !== null && movementDiff >= MIN_MOVEMENT_TO_KNOWN_STATE) {
          // if blinds moved at least 2% downwards, TILTING will be skipped as the blinds angle is already known
          transitionState(State.TILTING, currentOperation);
          return processEvent();
        } else if (ALLOW_DOWN_OPTIMIZATION && movementDiff !== null && movementDiff <= -2*MIN_MOVEMENT_TO_KNOWN_STATE) {
          // if blinds moved at least 2% upwards, TILTING will be skipped as the blinds angle is already known
          transitionState(State.TILTING_UPWARDS, currentOperation);
          return processEvent();
        } else {
          transitionState(State.TILTING, currentOperation);
          performTiltClosing();
        }
        break;

      case State.TILTING:  // was tilting and stopped, what next?
        if (currentOperation.tilt_duration < 0.05) {
          transitionState(State.TILTING2, currentOperation);
          return processEvent();
        }
        transitionState(State.TILTING2, currentOperation);
        performTilt(currentOperation.tilt_duration);
        break;

      case State.TILTING_UPWARDS:  // was tilting and stopped, what next?
        const newDuration = recomputeTiltForSwitchedDirection(currentOperation.tilt_duration);
        print("Optimizing by tilt down, original duration ", currentOperation.tilt_duration, ", recomputed ", newDuration);
        if (newDuration < 0.05) {
          transitionState(State.TILTING2, currentOperation);
          return processEvent();
        }
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

  if (event.info && (event.info.event === "stopped" || event.info.event === "closed" || event.info.event === "opened")) {
    processEvent();
  }
}, null);

function entryPoint(stop_state, transition_state, data) {
    loadStatus(function() {
      if (currentState !== State.IDLE) {
        transitionState(stop_state, data);
        Shelly.call("Cover.Stop", { id: 0 }, function (r, error_code, error_message, userdata1) {
            print("Stop callback", r, error_code, error_message)
            processEvent();
        });
      } else {
        transitionState(transition_state, data);
        processEvent();
      }
    })
}

function tilt(tilt_duration) {
  entryPoint(State.STOPPING_TILT, State.MOVING_TO_POSITION, {tilt_duration: tilt_duration})
}

function posAndTilt(pos, tilt_duration) {
  entryPoint(State.STOPPING, State.STOPPING, { pos:pos, tilt_duration:tilt_duration })
}
