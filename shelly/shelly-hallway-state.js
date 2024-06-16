let swState = [null, null];
let swPower = [0, 0];
let evPower = [0, 0];
let systemEventHandler = null;
let systemStatusHandler = null;
let timerPowerReader = null;
let haParams = null;

let readPower = function (callback) {
    Shelly.call("Switch.GetStatus", {id: 0}, function (r, error_code, error_message, userdata1) {
        print("r:", JSON.stringify(r));
        swState[r["id"]] = r["output"];
        swPower[r["id"]] = r["apower"];
        evPower[r["id"]] = r["apower"];

        if (r["id"] === 0) {
            print("Asking for Sw1 power");
            Shelly.call("Switch.GetStatus", {id: 1}, function (r, error_code, error_message, userdata1) {
                print("r:", JSON.stringify(r));
                swState[r["id"]] = r["output"];
                swPower[r["id"]] = r["apower"];
                evPower[r["id"]] = r["apower"];
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

let callWebhook = function () {
    const totalPower = evPower[0] + evPower[1];
    const isCurrentlyOn = totalPower > 0.1;

    if (haParams && haParams.url) {
        Shelly.call("HTTP.POST", {
            url: haParams.url,
            body: JSON.stringify({"state": isCurrentlyOn ? 'on' : 'off', "token": haParams.token}),
        })
    }
}

let isOn = function () {
    return evPower[0] + evPower[1];
}

let readPowerAndCallWebhook = function () {
    Shelly.call("KVS.Get", {key: "HA_PARAMS"}, function (r, error_code, error_message, userdata1) {
        if (r && r.value) {
            if (typeof r.value === 'string') {
                try {
                    haParams = JSON.parse(r.value);
                } catch (e) {
                    print('Error parsing JSON:', e);
                }
            } else {
                haParams = r.value
            }
        }
        readPower(function () {
            callWebhook()
        })
    })
}

systemEventHandler = Shelly.addEventHandler(function (event) {
    // print("event handler: ", JSON.stringify(event));
    // if (event.name === "switch" && event.info && event.info.event === "power_update") {
    //     evPower[event.info.id] = event.info.apower;
    //     callWebhook();
    // }
}, null);

systemStatusHandler = Shelly.addStatusHandler(function (event) {
    print("status handler: ", JSON.stringify(event));
    if (event.name === "switch" && event.delta && event.delta.apower !== undefined) {
        evPower[event.delta.id] = event.delta.apower;
        callWebhook();
    }
}, null);

timerPowerReader = Timer.set(60_000 * 5, true, readPowerAndCallWebhook)
readPowerAndCallWebhook()

/**
 * event handler: {"component":"switch:1","name":"switch","id":1,"now":1718050985.83310985565,"info":{"component":"switch:1","id": 22:23:06
 * 1,"event":"power_update","apower":33.6,"ts":1718050985.82999992370}} 22:23:06
 * shelly_notification:163 Status change of switch:1: {"id":1,"apower":33.6} 22:23:06
 * event handler: {"component":"switch:1","name":"switch","id":1,"now":1718050985.83331489562,"info":{"component":"switch:1","id": 22:23:06
 * 1,"event":"current_update","current":0.3,"ts":1718050985.82999992370}} 22:23:06
 * event handler: {"component":"switch:1","name":"switch","id":1,"now":1718050985.83331489562,"info":{"component":"switch:1","id": 22:23:06
 * 1,"event":"current_update","current":0.3,"ts":1718050985.82999992370}}
 */
/**
 * https://shelly-api-docs.shelly.cloud/gen2/Scripts/Tutorial/
 * curl -X POST -d '{"id":1, "method":"Script.Eval", "params":{"id":2, "code":"switchTo(false)"}}'\
 *  http://${SHELLY}/rpc
 */
