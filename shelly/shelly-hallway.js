let CONFIG = {
  /**
   * main switch id
   */
  INPUT_ID: 0,
};

let switching = false;
let started = false;
let swState = [null, null];
let swPower = [0, 0];

//{"id":0,"source":"loopback","output":false,"apower":0,"voltage":241.6,"freq":50,"current":0,"pf":0,"aenergy":{"total":0,"by_minute":[0,0,0],"minute_ts":1708285515},"temperature":{"tC":53.8,"tF":128.9}}

let onBootCheck = function (r, error_code, error_message, userdata1) {
    print("onBootCheck: ", JSON.stringify(r));

    swState[r["id"]] = r["output"];
    swPower[r["id"]] = r["apower"];
    if (r["id"] === 0){
        print("Asking for Sw1");
        Shelly.call("Switch.GetStatus", {id: 1}, onBootCheck);
        return r;
    }

    // const sm = 1 // swState[0] + swState[1]
    const sm = swState[0] + swState[1]
    if (sm !== 1) {
        print("Invalid switch state, reset", swState)
        Shelly.call("Switch.Set", {id: 0, on: true}, function (r, e, m, d) {
            Shelly.call("Switch.Set", {id: 1, on: false}, function (r, e, m, d) {
                print("State corrected")
                switching = false;
                started = true;
            });
        });
    } else {
        print("State OK")
        switching = false;
        started = true;
    }

    print("onBootCheck done");
    return r;
}

let powerReader = function (r, error_code, error_message, userdata1) {
    print("r:", JSON.stringify(r));
    swPower[r["id"]] = r["apower"];

    if (r["id"] === 0){
        print("Asking for Sw1 power");
        Shelly.call("Switch.GetStatus", {id: 1}, powerReader);
    } else {
        print("Power reading done");
    }
    return r;
}

let toggleThem = function() {
    switching = true;
    Shelly.call("Switch.toggle", {'id': 0}, function(r, e, m ,d) {
        Shelly.call("Switch.toggle", {'id': 1}, function(r, e, m ,d) {
            Shelly.call("Switch.GetStatus", {"id": 0}, onBootCheck);
        })
    });
}

let onSwitch = function(id, state) {
    print("onSwitch", id, state)
    switching = true;
    let otherId = id === 0 ? 1 : 0;

    Shelly.call("Switch.Set", {id: otherId, on: !state,}, function (r, e, m, d) {
        print("onSwitchSet")
        switching = false;
    });
}

let setup = function () {
    Shelly.call("Input.SetConfig", { id: CONFIG.INPUT_ID, config: { type: "button" } }, function (r, e, m, d) {
        Shelly.call("Switch.SetConfig", { id: 0, config: { in_mode: "momentary", initial_state: "restore_last", auto_on: false}}, function (r, e, m, d) {
            Shelly.call("Switch.SetConfig", { id: 1,  config: { in_mode: "momentary", initial_state: "restore_last", auto_on: false}}, function (r, e, m, d) {  // restore_last
                print("HW configured");

                Shelly.addEventHandler(function (event) {
                    print("event handler: ", JSON.stringify(event));

                    if (event.name === "input" && event.id === CONFIG.INPUT_ID) {
                        if (event.info.state !== false) {
                            // print("btn clicked");
                            // toggleThem();
                        }
                    }

                    if (started && !switching && event.name === "switch" && event.info.event === "toggle") {
                        onSwitch(event.id, event.info.state)
                    }

                }, null);

                switching = true;
                Timer.set(1000, false, function(){
                    // Ensure correct state
                    print("Setting correct state")
                    Shelly.call("Switch.GetStatus", {"id": 0}, onBootCheck);
                });
            })
        })
  });

  // Ensure correct state
  // switching = true;
  // Shelly.call("Switch.GetStatus", {"id": 0}, onBootCheck);
};

setup();
