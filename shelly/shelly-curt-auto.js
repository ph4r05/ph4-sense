// State definitions
const State = {
  IDLE: "IDLE",
  STOPPING: "STOPPING",
  STOPPING_TILT: "STOPPING_TILT",
  MOVING_TO_POSITION: "MOVING_TO_POSITION",
  TILTING: "TILTING",
  TILTING2: "TILTING2"
};

let currentState = State.IDLE;
let currentOperation = null;
let currentCoverStatus = null;

function transitionState(newState, operation) {
  currentState = newState;
  currentOperation = operation;
  print("State transition to ", currentState, "with operation ", operation);
}

function performTiltClosing(){
  Shelly.call("Cover.Close", {
      id: 0,
      duration: 1.2,
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

      case State.MOVING_TO_POSITION:
        if (currentCoverStatus && currentCoverStatus.current_pos - currentOperation.pos >= 2) {
          transitionState(State.TILTING, currentOperation);
          return processEvent();
        } else {
          transitionState(State.TILTING, currentOperation);
          performTiltClosing();
        }
        break;

      case State.TILTING:
        if (currentOperation.tilt_duration < 0.05) {
          transitionState(State.TILTING2, currentOperation);
          return processEvent();
        }
        transitionState(State.TILTING2, currentOperation);
        performTilt(currentOperation.tilt_duration);
        break;

      case State.TILTING2:
        transitionState(State.IDLE, null);
        print("Tilting done.");
        break;
    }
}

// Set up a global event handler for all state transitions
Shelly.addEventHandler(function (event) {
  print("Global event handler: ", JSON.stringify(event));

  if (event.info && (event.info.event === "stopped" || event.info.event === "closed")) {
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
