#!/usr/bin/env python3
"""HA transport. Private newline JSON on stdin/stdout; no tokens in settings."""
import asyncio
import contextlib
import json
import re
import secrets
import sys
import time
from urllib.parse import urlencode, urlsplit

import aiohttp
from aiohttp import web

from camera_media import CameraMedia


TOKEN_RESPONSE_LIMIT = 64 * 1024


async def read_token_response(response, *, require_refresh=False):
    """Read only bounded, uncompressed JSON; never include tokens in errors."""
    response.raise_for_status()
    if (response.status != 200
            or response.headers.get("Content-Encoding", "identity").lower() != "identity"
            or response.content_type != "application/json"):
        raise ValueError("Invalid Home Assistant token response.")
    if response.content_length is not None and response.content_length > TOKEN_RESPONSE_LIMIT:
        response.close()
        raise ValueError("Home Assistant token response exceeds the size limit.")
    body = bytearray()
    async for chunk in response.content.iter_chunked(4096):
        if len(body) + len(chunk) > TOKEN_RESPONSE_LIMIT:
            response.close()
            raise ValueError("Home Assistant token response exceeds the size limit.")
        body.extend(chunk)
    try:
        token = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("Invalid Home Assistant token response.") from None
    fields = ("access_token", "refresh_token") if require_refresh else ("access_token",)
    if not isinstance(token, dict) or any(
            not isinstance(token.get(field), str) or not token[field] or len(token[field]) > 16384
            for field in fields):
        raise ValueError("Invalid Home Assistant token response.")
    return token


def emit(kind, **values):
    print(json.dumps({"type": kind, **values}), flush=True)


def normalize_url(value):
    value = value.strip().rstrip("/")
    p = urlsplit(value)
    if (p.scheme not in ("http", "https") or not p.hostname or p.username
            or p.password or p.query or p.fragment or p.path not in ("", "/")):
        raise ValueError("Enter the Home Assistant address, e.g. http://homeassistant.local:8123")
    _ = p.port
    return value


def entity(value, domain=None):
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", value)) and (
        domain is None or value.startswith(domain + "."))


def target_states(rule):
    allowed = ("opening", "open", "closing", "closed") if rule.get("sensor", "").startswith("cover.") else ("on", "off")
    return [s for s in rule.get("states", ["open" if allowed[0] == "opening" else "on"]) if s in allowed]


def state_label(state, device_class="", cover=False):
    if cover:
        return {"opening": "Opening", "open": "Open", "closing": "Closing", "closed": "Closed"}.get(state, state)
    labels = {
        "door": ("Open", "Closed"), "garage_door": ("Open", "Closed"),
        "window": ("Open", "Closed"), "opening": ("Open", "Closed"),
        "motion": ("Motion detected", "No motion"), "occupancy": ("Occupied", "Clear"),
        "presence": ("Present", "Away"), "lock": ("Unlocked", "Locked"),
    }
    return labels.get(device_class, ("Active", "Inactive"))[0 if state == "on" else 1]


def notification_text(rule, state, attributes):
    custom = rule.get("messages", {}).get(state, "").strip()
    return custom or state_label(state, attributes.get("device_class", ""), rule.get("sensor", "").startswith("cover."))


def triggered(rule, data):
    old, new = data.get("old_state"), data.get("new_state")
    return bool(rule.get("enabled", True) and data.get("entity_id") == rule.get("sensor")
                and old and new and old.get("state") not in ("unknown", "unavailable")
                and old.get("state") != new.get("state") and new.get("state") in target_states(rule))


async def keyring(action, base, client, value=None):
    args = ["secret-tool", action]
    if action == "store":
        args += ["--label=Home Assistant Watch"]
    # Keep the original credential service ID: a display/plugin namespace
    # change must not require users to reauthorize their HA instance.
    args += ["application", "ha.watch", "instance", base, "client", client]
    proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                                               stdout=asyncio.subprocess.PIPE,
                                               stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(value.encode() if value else None), 60)
    except BaseException:
        proc.kill()
        await proc.wait()
        raise
    if proc.returncode and action != "lookup":
        raise RuntimeError("Could not access the system keyring. Unlock your keyring and retry.")
    return out.decode().strip()


class Bridge:
    def __init__(self):
        self.config = {}
        self.ws = None
        self.pending = {}
        self.serial = 0
        self.connection = None
        self.tasks = set()
        self.last_alert = {}
        self.paused_until = 0
        self.states = {}
        self.entity_catalog = None
        self.auth_runner = None
        self.auth_state = None
        self.auth_expiry = 0
        self.preview_serial = 0
        self.media = None
        self.media_task = None
        self.preview_pinned = False
        self.preview_lock = asyncio.Lock()
        self.access = ""

    def spawn(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def rpc(self, kind, **values):
        if not self.ws or self.ws.closed:
            raise RuntimeError("Home Assistant is not connected yet.")
        self.serial += 1
        ident = self.serial
        future = asyncio.get_running_loop().create_future()
        self.pending[ident] = future
        try:
            await self.ws.send_json({"id": ident, "type": kind, **values})
            return await asyncio.wait_for(future, 30)
        finally:
            self.pending.pop(ident, None)

    async def stop_media(self):
        if self.media_task:
            self.media_task.cancel()
            await asyncio.gather(self.media_task, return_exceptions=True)
        self.media_task = None
        self.media = None

    async def stop_connection(self):
        await self.stop_media()
        self.preview_pinned = False
        if self.connection:
            self.connection.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.connection
        self.connection = None
        self.access = ""
        self.states = {}
        self.entity_catalog = None
        self.preview_serial += 1
        emit("clear")

    async def configure(self, config):
        changed = (config.get("url"), config.get("clientId")) != (
            self.config.get("url"), self.config.get("clientId"))
        self.config = config
        if changed or not self.connection or self.connection.done():
            await self.stop_connection()
            if config.get("url") and config.get("clientId"):
                self.connection = self.spawn(self.connect_loop())
            else:
                emit("status", state="signed_out", message="Connect your Home Assistant to get started.")

    async def connect_loop(self):
        delay = 2
        while True:
            try:
                base = normalize_url(self.config["url"])
                client = self.config["clientId"]
                refresh = await keyring("lookup", base, client)
                if not refresh:
                    emit("status", state="signed_out", message="Sign in to Home Assistant.")
                    return
                emit("status", state="connecting", message="Connecting to Home Assistant…")
                async with self.http.post(base + "/auth/token", data={
                    "grant_type": "refresh_token", "refresh_token": refresh, "client_id": client},
                    allow_redirects=False, auto_decompress=False, read_bufsize=4096,
                    headers={"Accept-Encoding": "identity"}) as response:
                    if response.status in (400, 401, 403):
                        emit("status", state="signed_out", message="Your session expired. Please sign in again.")
                        return
                    response.raise_for_status()
                    token = await read_token_response(response)
                self.access = token["access_token"]
                async with self.http.ws_connect(base + "/api/websocket", heartbeat=30) as ws:
                    self.ws = ws
                    if (await ws.receive_json())["type"] != "auth_required":
                        raise RuntimeError("Unexpected Home Assistant response.")
                    await ws.send_json({"type": "auth", "access_token": self.access})
                    if (await ws.receive_json())["type"] != "auth_ok":
                        raise RuntimeError("Home Assistant rejected the session.")
                    reader = asyncio.create_task(self.read_ws(ws))
                    try:
                        await self.rpc("subscribe_events", event_type="state_changed")
                        states = await self.rpc("get_states")
                        self.states = {s["entity_id"]: s for s in states}
                        self.emit_entities()
                        emit("status", state="connected", message="Connected to Home Assistant")
                        delay = 2
                        await reader
                    finally:
                        reader.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await reader
            except asyncio.CancelledError:
                raise
            except Exception:
                emit("status", state="offline", message="Cannot reach Home Assistant. Retrying automatically…")
            finally:
                self.ws = None
                self.access = ""
                for future in list(self.pending.values()):
                    if not future.done():
                        future.set_exception(RuntimeError("Home Assistant disconnected."))
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    async def read_ws(self, ws):
        async for message in ws:
            if message.type != aiohttp.WSMsgType.TEXT:
                continue
            data = message.json()
            if data.get("type") == "result":
                future = self.pending.get(data["id"])
                if future and not future.done():
                    if data.get("success"):
                        future.set_result(data.get("result"))
                    else:
                        future.set_exception(RuntimeError("Home Assistant could not complete this request."))
            elif data.get("type") == "event":
                event = data.get("event", {}).get("data", {})
                ident = event.get("entity_id", "")
                if event.get("new_state"):
                    self.states[ident] = event["new_state"]
                else:
                    self.states.pop(ident, None)
                if ident.startswith(("camera.", "binary_sensor.", "input_boolean.", "cover.")):
                    self.emit_entities()
                if time.monotonic() < self.paused_until:
                    continue
                for rule in self.config.get("rules", []):
                    if triggered(rule, event):
                        state = event["new_state"]["state"]
                        key = (rule.get("sensor"), rule.get("camera"), state)
                        now = time.monotonic()
                        if now - self.last_alert.get(key, -1e9) >= 30:
                            self.last_alert[key] = now
                            self.spawn(self.safe_preview(rule, state, event["new_state"].get("attributes", {})))

    def emit_entities(self):
        rows = [{"id": s["entity_id"], "name": s.get("attributes", {}).get("friendly_name", s["entity_id"]),
                 "deviceClass": s.get("attributes", {}).get("device_class", "")} for s in self.states.values()
                if s["entity_id"].startswith(("camera.", "binary_sensor.", "input_boolean.", "cover."))]
        # Live states belong to alert processing, not the selection model.
        # Replacing that model on each state event resets an open dropdown.
        rows.sort(key=lambda x: (x["name"].casefold(), x["id"]))
        if rows != self.entity_catalog:
            self.entity_catalog = rows
            emit("entities", entities=rows)

    async def safe_preview(self, rule, state=None, attributes=None):
        try:
            await self.preview(rule, state, attributes)
        except Exception:
            emit("error", message="Could not open the camera. Check the connection and try again.")

    async def preview(self, rule, state=None, attributes=None):
        async with self.preview_lock:
            if self.preview_pinned:
                return
            await self.stop_media()
            await self.start_preview(rule, state, attributes)

    async def start_preview(self, rule, state=None, attributes=None):
        camera = rule.get("camera", "")
        self.preview_serial += 1
        serial = self.preview_serial
        attributes = attributes if attributes is not None else self.states.get(rule.get("sensor"), {}).get("attributes", {})
        name = attributes.get("friendly_name", rule.get("sensor") or "Home Assistant")
        state = state or next(iter(target_states(rule)), "on")
        message = notification_text(rule, state, attributes)
        if not camera:
            emit("preview", serial=serial, title=name, message=message, camera="", duration=self.config.get("duration", 20))
            return
        if not entity(camera, "camera"):
            raise ValueError("Invalid camera")
        base = normalize_url(self.config["url"])
        emit("preview", serial=serial, title=name, message=message, camera=camera, duration=self.config.get("duration", 20))
        self.media = CameraMedia(base, self.rpc, emit, serial)
        self.media_task = self.spawn(self.media.run(camera))

    async def login(self, value):
        base = normalize_url(value)
        if self.auth_runner:
            await self.auth_runner.cleanup()
        state = secrets.token_urlsafe(32)
        self.auth_state = state
        self.auth_expiry = time.monotonic() + 300
        app = web.Application()
        client = ""

        async def callback(request):
            nonlocal client
            if (time.monotonic() > self.auth_expiry or not self.auth_state
                    or not secrets.compare_digest(request.query.get("state", ""), self.auth_state)):
                return web.Response(status=400, text="This sign-in attempt expired. Start again in Home Assistant Watch.")
            code = request.query.get("code")
            if not code:
                return web.Response(status=400, text="No authorization code received.")
            self.auth_state = None  # Consume once, including on exchange failure.
            try:
                async with self.http.post(base + "/auth/token", data={
                    "grant_type": "authorization_code", "code": code, "client_id": client},
                    allow_redirects=False, auto_decompress=False, read_bufsize=4096,
                    headers={"Accept-Encoding": "identity"}) as response:
                    response.raise_for_status()
                    token = await read_token_response(response, require_refresh=True)
                await keyring("store", base, client, token["refresh_token"])
                different_instance = bool(self.config.get("url") and self.config["url"] != base)
                config = {**self.config, "url": base, "clientId": client}
                if different_instance:
                    config["rules"] = []
                emit("save_connection", url=base, clientId=client, resetRules=different_instance)
                await self.configure(config)
                return web.Response(text="Connected! You can close this tab and return to Home Assistant Watch.",
                                    headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
            except Exception:
                emit("error", message="Sign-in could not be saved. Check that your system keyring is unlocked and retry.")
                return web.Response(status=400, text="Sign-in failed. Return to Home Assistant Watch and retry.")

        async def index(request):
            return web.Response(text="Home Assistant Watch")

        app.router.add_get("/callback", callback)
        app.router.add_get("/", index)
        self.auth_runner = web.AppRunner(app, access_log=None)
        await self.auth_runner.setup()
        site = web.TCPSite(self.auth_runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        client = f"http://127.0.0.1:{port}/"
        emit("open_url", url=base + "/auth/authorize?" + urlencode({
            "client_id": client, "redirect_uri": client + "callback", "state": state}))
        emit("status", state="signing_in", message="Finish signing in in your browser.")

    async def command(self, data):
        try:
            kind = data.get("type")
            if kind == "configure":
                await self.configure(data.get("config", {}))
            elif kind == "login":
                await self.login(data.get("url", ""))
            elif kind == "test":
                self.spawn(self.safe_preview(data.get("rule", {})))
            elif kind == "pause":
                self.paused_until = time.monotonic() + (3600 if data.get("paused") else 0)
            elif kind == "frame_ready":
                if self.media and data.get("serial") == self.preview_serial:
                    self.media.acknowledge(data.get("frame"))
            elif kind == "pin":
                if data.get("serial") == self.preview_serial:
                    self.preview_pinned = bool(data.get("pinned"))
            elif kind == "dismiss":
                if data.get("serial", self.preview_serial) == self.preview_serial:
                    self.preview_serial += 1
                    self.preview_pinned = False
                    await self.stop_media()
            elif kind == "logout":
                base, client = self.config.get("url"), self.config.get("clientId")
                await self.stop_connection()
                if base and client:
                    refresh = await keyring("lookup", base, client)
                    if refresh:
                        # Supported by both older and newer HA versions.
                        try:
                            async with self.http.post(base + "/auth/token", data={"action": "revoke", "token": refresh},
                                                      allow_redirects=False, auto_decompress=False, read_bufsize=4096,
                                                      headers={"Accept-Encoding": "identity"}) as response:
                                response.raise_for_status()
                        except Exception:
                            emit("error", message="Signed out locally. HA was unreachable; revoke the session in your HA profile if needed.")
                        await keyring("clear", base, client)
                self.auth_state = None
                emit("save_connection", url=base or "", clientId="")
                await self.configure({**self.config, "clientId": ""})
        except ValueError as error:
            emit("error", message=str(error))
        except Exception:
            emit("error", message="The request failed. Check your Home Assistant address and system keyring.")

    async def run(self):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35)) as self.http:
            reader = asyncio.StreamReader(limit=1024 * 1024)
            protocol = asyncio.StreamReaderProtocol(reader)
            await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, sys.stdin)
            emit("ready")
            try:
                while line := await reader.readline():
                    try:
                        data = json.loads(line)
                        if isinstance(data, dict):
                            await self.command(data)
                    except (ValueError, TypeError):
                        emit("error", message="Invalid command.")
            finally:
                await self.stop_connection()
                for task in list(self.tasks):
                    task.cancel()
                await asyncio.gather(*self.tasks, return_exceptions=True)
                if self.auth_runner:
                    await self.auth_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(Bridge().run())
