let swState = [null, null];
let swPower = [0, 0];

let readPower = function (callback) {
    Shelly.call("Switch.GetStatus", {id: 0}, function (r, error_code, error_message, userdata1) {
        print("r:", JSON.stringify(r));
        swState[r["id"]] = r["output"];
        swPower[r["id"]] = r["apower"];

        if (r["id"] === 0) {
            print("Asking for Sw1 power");
            Shelly.call("Switch.GetStatus", {id: 1}, function (r, error_code, error_message, userdata1) {
                print("r:", JSON.stringify(r));
                swState[r["id"]] = r["output"];
                swPower[r["id"]] = r["apower"];
                print("Power reading done");
                callback();
            });
        }
        return r;
    });
}


let switchTo = function(state) {
    readPower(function () {
        const totalPower = swPower[0] + swPower[1];
        const isCurrentlyOn = totalPower > 0.1;
        if (state !== isCurrentlyOn) {
            Shelly.call("Switch.Set", {id: 0, on: !swState[0]}, function (r, e, m, d) {
                print("Switched");
            });
        }
    })
}

/**
 * https://shelly-api-docs.shelly.cloud/gen2/Scripts/Tutorial/
 * curl -X POST -d '{"id":1, "method":"Script.Eval", "params":{"id":2, "code":"switchTo(false)"}}'\
 *  http://${SHELLY}/rpc
 */
