let duration = 0.95;
let inProgress = false;

function tilt(tilt_duration) {
  print("tilt called")
  if (inProgress){
    return
  }

  let subscription = 0;
  let handler = function (event) {
      print("event handler: ", JSON.stringify(event));
      if (inProgress && event && event.info && event.info.event === "stopped") {
        inProgress = false
        print("tilting")
        Shelly.call("Cover.Open", {
          id: 0,
          duration: tilt_duration,
        }, function (r, error_code, error_message, userdata1) {
          print("Done")
          Shelly.removeEventHandler(subscription);
        });
      }
  };

  subscription = Shelly.addEventHandler(handler, null);
  Shelly.call("Cover.Close", {
      id: 0,
      duration: 1.2,
    }, function (r, error_code, error_message, userdata1) {
      inProgress = r === null;
    });
}

function posAndTilt(pos, duration) {
  print("posAndTilt called")
  if (inProgress){
    return
  }

  let stopped = false
  let subscription = -1;
  let subscriptionEvent= -1;

  Shelly.call("Cover.Stop", { id: 0 }, function (r, error_code, error_message, userdata1) {
    Shelly.call("Cover.GetStatus", { id: 0 }, function (r, error_code, error_message, userdata1) {
      print("posAndTilt status: ", JSON.stringify(r));
      if (r == null) {
        return
      }
      if (r.current_pos === pos) {
        print("posAndTilt already at pos, just tilt")
        tilt(duration)
        return
      }

      let unreg = function () {
        print("unreg now")
        if (subscription >= 0) {
          Shelly.removeStatusHandler(subscription);
          subscription = -1;
        }
        if (subscriptionEvent >= 0) {
          Shelly.removeEventHandler(subscriptionEvent);
          subscriptionEvent = -1;
        }
      }

      let handler = function (event) {
        // print("posAndTilt status handler: ", JSON.stringify(event));
        if (event && event.delta && (event.delta.state === "stopped" || event.delta.state === "closed" || event.delta.state === "open")) {
          print("posAndTilt status, Go to pos done, now tilt")
          unreg()
          tilt(duration);
        }
      };
      let handlerEvent = function (event) {
        // print("posAndTilt event handler: ", JSON.stringify(event));
        if (event && event.info && (event.info.event === "stopped" || event.info.event === "closed" || event.info.event === "open")) {
          print("posAndTilt evt, Go to pos done, now tilt")
          unreg()
          tilt(duration)
        }
      };

      subscription = Shelly.addStatusHandler(handler, null);
      subscriptionEvent = Shelly.addEventHandler(handlerEvent, null);
      Timer.set(60000, false, function(){
          print("Failsafe unreg")
          unreg()
      });
      Shelly.call("Cover.GoToPosition", {
        id: 0,
        pos: pos,
      }, function (r, error_code, error_message, userdata1) {
        print("posAndTilt Cover.GoToPosition done", r)
        if (r !== null) {
          unreg()
        }
      })
    })
  })
}

// posAndTilt(26, 1)
