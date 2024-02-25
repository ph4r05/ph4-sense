let CONFIG = {
  /**
   * Pick your desired Input to be used for triggering the cycling (note: this input would be changed
   * to detached!)
   */
  INPUT_ID: 0,

  /**
   * List (in the expected order) the operations that you want this script to cycle through.
   * E.g. [switchId, "on" or "off"]
   */
  CYCLES: [
    [0, "on"],
    [0, "off"],
    [0, "on"],
    [0, "off"],
    [0, "on"],
    [0, "off"],
  ],
};

let cycled = 0;
let currentCycle = 0;
let timer = null;

let runCycle = function () {
  let currentOperation = CONFIG.CYCLES[currentCycle];
  if (!currentOperation) {
    print("Terminating cycle");
    cycled = 0;
    currentCycle = 0;
    currentOperation = CONFIG.CYCLES[currentCycle];
    Timer.clear(timer);
    return;
  }
  cycled = 1;

  print("Running cycle: " + currentOperation[1]);
  Shelly.call("switch.set", {
    id: JSON.stringify(currentOperation[0]),
    on: currentOperation[1] === "on",
  });
  if (currentCycle === 0) {
    timer = Timer.set(250, true, runCycle, null);
  }
  currentCycle++;
};

let setup = function () {
  Shelly.call(
    "switch.setconfig",
    { id: JSON.stringify(CONFIG.INPUT_ID), config: { in_mode: "detached" } },
    function () {
      Shelly.addEventHandler(function (event) {
      print("event handler: ", event.info.state, event.info.event, event.component);
        //if (event.component === "input:" + JSON.stringify(CONFIG.INPUT_ID)) {
        if (event.component === "switch:" + JSON.stringify(CONFIG.INPUT_ID)) {
          if (cycled === 0 &&
            event.info.state !== false //&&
            //event.info.event !== "btn_up" &&
            //event.info.event !== "btn_down"
          ) {
            runCycle();
          }
        }
      }, null);
    }
  );
};

setup();
