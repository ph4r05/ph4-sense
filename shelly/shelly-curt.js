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
      inProgress = true;
    });
}

// tilt(duration);
// TODO: go to pos and tilt
