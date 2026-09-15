.pragma library

function options(entity) {
    if (entity && entity.id.indexOf("cover.") === 0)
        return [{value: "opening", label: "Opening"}, {value: "open", label: "Open"},
                {value: "closing", label: "Closing"}, {value: "closed", label: "Closed"}]
    var labels = {
        door: ["Open", "Closed"], garage_door: ["Open", "Closed"],
        window: ["Open", "Closed"], opening: ["Open", "Closed"],
        motion: ["Motion detected", "No motion"], occupancy: ["Occupied", "Clear"],
        presence: ["Present", "Away"], lock: ["Unlocked", "Locked"]
    }
    var pair = labels[entity ? entity.deviceClass : ""] || ["Active", "Inactive"]
    return [{value: "on", label: pair[0]}, {value: "off", label: pair[1]}]
}

function defaults(id) { return [id.indexOf("cover.") === 0 ? "open" : "on"] }
