# Home Assistant Watch for Omarchy

A small camera window when something happens at home. Sign in to Home Assistant,
choose a sensor and a camera, and let Watch handle the desktop preview.

**Version 0.2.0 — local testing preview.** Built against Omarchy's Quickshell
plugin API. The transport is tested against a simulated HA server; the initial version has also been tested successfully with a real HA instance,
UniFi camera and door contact sensor. Cover support needs real-device testing.

## What works in this version

- Browser sign-in with Home Assistant's authorization flow. No manually copied token.
- Refresh tokens in the Linux Secret Service keyring through `secret-tool`.
- Automatic discovery of camera, binary sensor, input boolean and cover entities.
- Multiple rules: selected device states → camera preview or text-only popup.
- Choose Open/Closed for contacts, Active/Inactive for other binary sensors,
  and Opening/Open/Closing/Closed for covers. Select one or several states.
- Optional custom text per state; blank fields use an automatic state label.
- HA-provided HLS video, muted, with snapshots while video loads or is unavailable.
- Four corners, selectable monitor, 5–120 seconds on screen.
- Pin, expand, dismiss, and open the camera in Home Assistant.
- One-hour pause and a 30-second cooldown per sensor/camera/state combination. Opposite states can notify immediately.
- Automatic reconnect with backoff after connection loss or resume.
- Uses the active monitor when set to Automatic; does not take keyboard focus.
- Settings follow the Omarchy palette. UI text is currently English.

## Requirements

Omarchy with the **Quickshell shell and `omarchy plugin` commands**, Python 3.11+
with venv support, `secret-tool` and an unlocked Secret Service keyring,
`xdg-open`, and Qt Multimedia with its FFmpeg backend.

On Arch the relevant packages are `python`, `libsecret`, `xdg-utils`,
`qt6-multimedia`, and `qt6-multimedia-ffmpeg`. A Secret Service provider must
already be available (as in a standard configured Omarchy desktop).

Python dependencies are isolated in `.venv/`; system Python is untouched.

## Installation from a checkout

From this directory:

```bash
bash setup.sh
```

The script creates the virtual environment, installs the pinned Python
dependencies, links this checkout into `~/.config/omarchy/plugins/ha.watch`,
rescans plugins and enables the bar button. It refuses to replace an existing,
different plugin directory. It does not install system packages.

The Omarchy plugin installer only clones the repository: it does not run
`setup.sh` or install Python dependencies. If you install through
`omarchy plugin add`, run `bash setup.sh` inside the installed plugin directory
before enabling it. The `.venv` is created locally and is not part of the repository.

Open the house button in the bar, or run:

```bash
omarchy-shell ha-watch settings
```

1. Enter the base HA address, for example `http://homeassistant.local:8123`.
2. Select **Sign in**. Complete the normal Home Assistant login in your browser.
3. Return to Watch. Choose **Device**, select **Notify when** states and **Show**, then **Add rule**.
   Optionally enter custom text, such as “Kjellerdør åpnet”, for each selected state.
4. Use **Test** to verify the camera without waiting for motion.
5. Trigger real motion to verify the entire path. The device must transition to one of the selected states.

Use the HA address reachable from this desktop. The browser callback is on
`127.0.0.1` and requires the browser to run on the same computer as the plugin.
No public callback server, HA add-on, MQTT broker, camera password or RTSP URL
is required by this design. The plugin never changes HA automations or devices.

## Camera compatibility

Watch talks to HA, not to UniFi, Reolink or other manufacturers directly.
This version requests the common `camera/stream` HLS endpoint. A camera that
only exposes WebRTC or still images may fall back to snapshots. Playback also
depends on the codecs available on the desktop. HLS can take several seconds
to start and can lag the live scene; low-latency WebRTC is future work.

Snapshots refresh every five seconds while video is unavailable. Signed
snapshot URLs currently last one hour; reopen a preview pinned longer than
that to refresh its snapshot access. Snapshot refresh stops while video plays.

Only real state changes from a known state trigger rules. Initial states and
recovery from `unknown` or `unavailable` do not create alerts. Existing rules
without state selections keep their original `on`-only behavior (open-only for
door contacts). New cover rules default to `open`; movement states require
the integration to report `opening`/`closing`. Test previews use the first
selected state and do not control or move the actual device.
Event entities (including some doorbell implementations), arbitrary HA
automation calls and detection labels are not supported yet. A HA helper
`input_boolean` can be used as a trigger in this version.

There is one preview at a time. New activity replaces an unpinned preview;
a pinned preview stays on screen. No event history is stored. Pause state is
session-only, and Watch currently has its own pause control rather than
following Omarchy's Do Not Disturb setting.

## Storage and privacy

Non-secret configuration is inline in the `ha.watch` entry in
`~/.config/omarchy/shell.json`. The plugin follows the shell's persistence API.
Refresh tokens are stored only in the keyring, access tokens stay in the
connection process, and camera URLs are passed in memory to the player.
The auth callback uses a random, single-use state value and expires after
five minutes. TLS certificate verification stays enabled.

HA access follows the signed-in user's permissions; selecting cameras in the
UI is not an additional server-side permission boundary. Use HTTPS for a
connection that should be encrypted.

Sign out to revoke the session and remove the keyring entry. If HA is
unreachable during sign-out, revoke the old session in your HA profile later.
Switching to another HA address clears the rules to avoid accidental matches.
Disabling or removing the plugin does not itself revoke an HA session.

## Development and validation

```bash
.venv/bin/python -m unittest discover -s tests -v
omarchy-shell ha-watch status
omarchy-shell ha-watch demo
```

Tests start a local mock server and cover OAuth state checks and replay,
expiry, token exchange, sensor transitions, WebSocket discovery, image/stream
requests, cooldown, pause and rejecting external stream URLs. The keyring is
mocked; no user HA instance or credentials are needed. `demo` displays a
text-only popup to test placement without an HA connection.

Implementation:

- `Service.qml`: plugin lifecycle, settings persistence and private JSON IPC.
- `Settings.qml`: connection, rules and window preferences.
- `Preview.qml`: layer-shell camera surface and video player.
- `bridge.py`: browser authorization, keyring and HA WebSocket transport.

Reference APIs: [HA authentication](https://developers.home-assistant.io/docs/auth_api/),
[HA WebSocket](https://developers.home-assistant.io/docs/api/websocket/),
[camera implementation](https://github.com/home-assistant/core/blob/dev/homeassistant/components/camera/__init__.py).

## Disable

```bash
omarchy plugin disable ha.watch
```

Sign out first if you also want to revoke the connection.

To remove an installation managed by Omarchy, use `omarchy plugin remove ha.watch`.
For a development checkout installed with `setup.sh`, disable the plugin and
remove only the `~/.config/omarchy/plugins/ha.watch` symlink, leaving your checkout
intact. Neither operation changes cameras or automations in Home Assistant.

## Updating during development

Pull the latest commits and rerun `bash setup.sh` if dependencies changed.
If the UI still shows an older version after a plugin rescan, run
`omarchy restart shell`, then reopen Watch. This briefly restarts the bar and
shell surfaces, while preserving your saved rules and HA session.

To validate a release, run `omarchy plugin validate` on a clean checkout or
Git archive before creating `.venv`. The validator rejects symlinks, including
those in a local Python virtual environment.

## Next milestones

Real cover testing, faster video startup, WebRTC, searchable entity pickers,
event-based doorbells, and additional camera/integration compatibility tests.
The project is under active development and has not been submitted to the
Omarchy plugin marketplace. Name, icon and visual design may change before listing.
