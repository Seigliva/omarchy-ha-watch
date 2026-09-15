import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import aiohttp
from aiohttp import web

from bridge import Bridge, normalize_url, triggered, notification_text


class Rules(unittest.TestCase):
    def test_cover_and_door_states(self):
        for sensor, states, sequence in [
            ("cover.garage", ["opening", "open", "closing", "closed"], ["closed", "opening", "open", "closing", "closed"]),
            ("binary_sensor.door", ["on", "off"], ["off", "on", "off"]),
        ]:
            rule = {"sensor": sensor, "states": states}
            for old, new in zip(sequence, sequence[1:]):
                event = {"entity_id": sensor, "old_state": {"state": old}, "new_state": {"state": new}}
                self.assertTrue(triggered(rule, event))
                self.assertFalse(triggered({**rule, "states": []}, event))
                event["old_state"] = {"state": "unavailable"}
                self.assertFalse(triggered(rule, event))
        self.assertFalse(triggered({"sensor": "binary_sensor.door"}, {
            "entity_id": "binary_sensor.door", "old_state": {"state": "on"}, "new_state": {"state": "off"}}))

    def test_custom_and_automatic_text(self):
        rule = {"sensor": "binary_sensor.door", "messages": {"on": " Kjellerdør åpnet ", "off": " "}}
        self.assertEqual(notification_text(rule, "on", {"device_class": "door"}), "Kjellerdør åpnet")
        self.assertEqual(notification_text(rule, "off", {"device_class": "door"}), "Closed")
        self.assertEqual(notification_text({}, "on", {"device_class": "motion"}), "Motion detected")
        self.assertEqual(notification_text({"sensor": "cover.garage"}, "closing", {}), "Closing")

    def test_url_validation(self):
        self.assertEqual(normalize_url(" http://homeassistant.local:8123/ "), "http://homeassistant.local:8123")
        for value in ["file:///tmp/ha", "https://user:pass@ha.local", "https://ha.local/?token=x", "https://ha.local/dashboard", "http://ha.local:bad"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_url(value)

    def test_only_real_activation(self):
        rule = {"sensor": "binary_sensor.motion"}
        for old, new, expected in [("off", "on", True), ("on", "on", False), ("on", "off", False),
                                    ("unavailable", "on", False), ("unknown", "on", False)]:
            self.assertEqual(triggered(rule, {"entity_id": rule["sensor"], "old_state": {"state": old}, "new_state": {"state": new}}), expected)
        self.assertFalse(triggered(rule, {"entity_id": rule["sensor"], "old_state": None, "new_state": {"state": "on"}}))
        self.assertFalse(triggered({**rule, "enabled": False}, {"entity_id": rule["sensor"], "old_state": {"state": "off"}, "new_state": {"state": "on"}}))


class Integration(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_stays_stable_until_choices_change(self):
        ident = "binary_sensor.door"
        self.bridge.states = {ident: {"entity_id": ident, "state": "off",
            "attributes": {"friendly_name": "Door", "device_class": "door"}}}
        self.bridge.emit_entities()
        self.assertEqual(len(self.events), 1)
        for state in ["on", "off", "unavailable", "off"]:
            self.bridge.states[ident]["state"] = state
            self.bridge.states[ident]["attributes"]["battery_level"] = 90
            self.bridge.emit_entities()
        self.assertEqual(len(self.events), 1, "Live updates must not reset the selector")
        self.bridge.states[ident]["attributes"]["friendly_name"] = "Basement door"
        self.bridge.emit_entities()
        self.assertEqual(self.events[-1]["entities"][0]["name"], "Basement door")
        self.bridge.states[ident]["attributes"]["device_class"] = "window"
        self.bridge.emit_entities()
        self.assertEqual(self.events[-1]["entities"][0]["deviceClass"], "window")
        self.bridge.states["cover.garage"] = {"entity_id": "cover.garage", "state": "closed"}
        self.bridge.emit_entities()
        self.assertEqual(len(self.events[-1]["entities"]), 2)
        del self.bridge.states[ident]
        self.bridge.emit_entities()
        self.assertEqual([row["id"] for row in self.events[-1]["entities"]], ["cover.garage"])
        await self.bridge.stop_connection()
        self.bridge.emit_entities()
        self.assertEqual(self.events[-1], {"type": "entities", "entities": []})
        self.assertEqual(len(self.events), 7)

    async def test_opposite_states_and_event_text(self):
        base = await self.server()
        await self.bridge.configure({"url": base, "clientId": "http://127.0.0.1:1234/",
            "rules": [{"sensor": "cover.garage", "states": ["opening", "closed"],
                       "messages": {"opening": "Garasjeporten åpnes"}}]})
        await self.wait_event("entities")
        for old, new in [("closed", "opening"), ("closing", "closed"), ("closed", "opening")]:
            await self.socket.send_json({"type": "event", "event": {"data": {
                "entity_id": "cover.garage", "old_state": {"state": old},
                "new_state": {"entity_id": "cover.garage", "state": new,
                              "attributes": {"friendly_name": "Garasjeport", "device_class": "garage"}}}}})
        async with asyncio.timeout(3):
            while sum(e["type"] == "preview" for e in self.events) < 2:
                await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        previews = [e for e in self.events if e["type"] == "preview"]
        self.assertEqual([e["message"] for e in previews], ["Garasjeporten åpnes", "Closed"])
        self.assertTrue(any(row["id"] == "cover.garage" and row["deviceClass"] == "garage"
                            for e in self.events if e["type"] == "entities" for row in e["entities"]))

    async def asyncSetUp(self):
        self.events = []
        self.emit_patch = patch("bridge.emit", side_effect=lambda kind, **values: self.events.append({"type": kind, **values}))
        self.emit_patch.start()
        self.keyring = AsyncMock(return_value="refresh-test")
        self.key_patch = patch("bridge.keyring", self.keyring)
        self.key_patch.start()
        self.bridge = Bridge()
        self.bridge.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3))
        self.socket = None
        self.runner = None
        self.grants = []

    async def asyncTearDown(self):
        await self.bridge.stop_connection()
        for task in list(self.bridge.tasks):
            task.cancel()
        await asyncio.gather(*self.bridge.tasks, return_exceptions=True)
        if self.bridge.auth_runner:
            await self.bridge.auth_runner.cleanup()
        await self.bridge.http.close()
        if self.runner:
            await self.runner.cleanup()
        self.emit_patch.stop()
        self.key_patch.stop()

    async def server(self):
        async def token(request):
            self.grants.append(dict(await request.post()))
            return web.json_response({"access_token": "access-test", "refresh_token": "refresh-test"})

        async def websocket(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            self.socket = ws
            await ws.send_json({"type": "auth_required"})
            auth = await ws.receive_json()
            self.assertEqual(auth["access_token"], "access-test")
            await ws.send_json({"type": "auth_ok"})
            async for msg in ws:
                data = msg.json()
                result = None
                if data["type"] == "get_states":
                    result = [{"entity_id": "camera.front", "state": "idle", "attributes": {"friendly_name": "Front"}},
                              {"entity_id": "binary_sensor.motion", "state": "off", "attributes": {"friendly_name": "Entrance"}}]
                elif data["type"] == "auth/sign_path":
                    result = {"path": data["path"] + "?authSig=test"}
                elif data["type"] == "camera/stream":
                    result = {"url": "/api/hls/test/master_playlist.m3u8"}
                await ws.send_json({"type": "result", "id": data["id"], "success": True, "result": result})
            return ws

        app = web.Application()
        app.router.add_post("/auth/token", token)
        app.router.add_get("/api/websocket", websocket)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        return f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"

    async def wait_event(self, kind):
        async with asyncio.timeout(3):
            while not any(e["type"] == kind for e in self.events):
                await asyncio.sleep(0.01)
        return next(e for e in self.events if e["type"] == kind)

    async def motion(self, old="off"):
        await self.socket.send_json({"type": "event", "event": {"data": {
            "entity_id": "binary_sensor.motion", "old_state": {"state": old},
            "new_state": {"entity_id": "binary_sensor.motion", "state": "on", "attributes": {"friendly_name": "Entrance"}}}}})

    async def test_end_to_end_event_camera_and_cooldown(self):
        base = await self.server()
        await self.bridge.configure({"url": base, "clientId": "http://127.0.0.1:1234/",
                                     "rules": [{"sensor": "binary_sensor.motion", "camera": "camera.front"}]})
        rows = await self.wait_event("entities")
        self.assertEqual(len(rows["entities"]), 2)
        await self.motion()
        video = await self.wait_event("video")
        self.assertEqual(video["url"], base + "/api/hls/test/master_playlist.m3u8")
        self.assertTrue(any(e["type"] == "image" for e in self.events))
        await self.motion()
        await asyncio.sleep(0.05)
        self.assertEqual(sum(e["type"] == "preview" for e in self.events), 1)
        self.bridge.last_alert.clear()
        await self.bridge.command({"type": "pause", "paused": True})
        await self.motion()
        await asyncio.sleep(0.05)
        self.assertEqual(sum(e["type"] == "preview" for e in self.events), 1)

    async def test_oauth_state_single_use_and_keyring(self):
        base = await self.server()
        await self.bridge.login(base)
        auth = await self.wait_event("open_url")
        query = parse_qs(urlsplit(auth["url"]).query)
        callback = query["redirect_uri"][0]
        async with self.bridge.http.get(callback, params={"code": "code-test", "state": "wrong"}) as resp:
            self.assertEqual(resp.status, 400)
        self.keyring.assert_not_awaited()
        async with self.bridge.http.get(callback, params={"code": "code-test", "state": query["state"][0]}) as resp:
            self.assertEqual(resp.status, 200)
        self.assertTrue(any(call.args[0] == "store" for call in self.keyring.await_args_list))
        async with self.bridge.http.get(callback, params={"code": "code-test", "state": query["state"][0]}) as resp:
            self.assertEqual(resp.status, 400)
        self.assertEqual(sum(g.get("grant_type") == "authorization_code" for g in self.grants), 1)
        await self.wait_event("entities")
        saved = next(e for e in self.events if e["type"] == "save_connection")
        self.assertNotIn("refresh_token", saved)

    async def test_expired_oauth(self):
        base = await self.server()
        await self.bridge.login(base)
        query = parse_qs(urlsplit((await self.wait_event("open_url"))["url"]).query)
        self.bridge.auth_expiry = time.monotonic() - 1
        async with self.bridge.http.get(query["redirect_uri"][0], params={"state": query["state"][0], "code": "x"}) as resp:
            self.assertEqual(resp.status, 400)

    async def test_snapshot_fallback_and_reject_external_stream(self):
        async def rpc(kind, **kwargs):
            if kind == "auth/sign_path":
                return {"path": "/api/camera_proxy/camera.front?authSig=test"}
            return {"url": "https://unrelated.invalid/stream"}
        self.bridge.config = {"url": "http://ha.local"}
        self.bridge.rpc = rpc
        await self.bridge.preview({"camera": "camera.front"})
        self.assertTrue(any(e["type"] == "image" for e in self.events))
        self.assertTrue(any(e["type"] == "video_unavailable" for e in self.events))
        self.assertFalse(any(e["type"] == "video" for e in self.events))


if __name__ == "__main__":
    unittest.main()
