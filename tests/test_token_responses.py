"""Adversarial token responses through the actual OAuth login/refresh paths."""
import asyncio
import contextlib
import gzip
import json
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import aiohttp
from aiohttp import web

from bridge import Bridge, TOKEN_RESPONSE_LIMIT, read_token_response


class TokenResponses(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.keyring = AsyncMock(return_value="saved-refresh")
        self.key_patch = patch('bridge.keyring', self.keyring)
        self.emit_patch = patch('bridge.emit', side_effect=lambda kind, **v: self.events.append(dict(type=kind, **v)))
        self.key_patch.start()
        self.emit_patch.start()
        self.bridge = Bridge()
        self.bridge.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3))
        self.mode = 'valid'
        self.requests = []
        self.websocket_attempts = 0

        async def token(request):
            self.requests.append(dict(await request.post()))
            self.assertEqual(request.headers.get('Accept-Encoding'), 'identity')
            if self.mode == 'oversized':
                return web.Response(body=b'x' * (TOKEN_RESPONSE_LIMIT + 1), content_type='application/json')
            if self.mode == 'chunked':
                response = web.StreamResponse(headers={'Content-Type': 'application/json'})
                await response.prepare(request)
                with contextlib.suppress(ConnectionResetError):
                    await response.write(b'x' * (TOKEN_RESPONSE_LIMIT + 1))
                    await response.write_eof()
                return response
            if self.mode == 'gzip':
                return web.Response(body=gzip.compress(b'x' * (TOKEN_RESPONSE_LIMIT * 100)),
                    headers={'Content-Type': 'application/json', 'Content-Encoding': 'gzip'})
            if self.mode == 'malformed':
                return web.Response(body=b'{secret-invalid-json', content_type='application/json')
            if self.mode == 'invalid_type':
                return web.json_response({'access_token': ['secret'], 'refresh_token': 12})
            if self.mode == 'html':
                return web.Response(text='<html>secret</html>', content_type='text/html')
            if self.mode == 'slow':
                response = web.StreamResponse(headers={'Content-Type': 'application/json'})
                await response.prepare(request)
                await response.write(b'{')
                await asyncio.sleep(0.2)
                return response
            data = b'{"access_token":"valid","refresh_token":"valid-refresh"}'
            if self.mode == 'boundary':
                data += b' ' * (TOKEN_RESPONSE_LIMIT - len(data))
            return web.Response(body=data, content_type='application/json')

        async def websocket(request):
            self.websocket_attempts += 1
            return web.Response(status=400)

        app = web.Application()
        app.router.add_post('/auth/token', token)
        app.router.add_get('/api/websocket', websocket)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.base = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'

    async def asyncTearDown(self):
        await self.bridge.stop_connection()
        for task in list(self.bridge.tasks):
            task.cancel()
        await asyncio.gather(*self.bridge.tasks, return_exceptions=True)
        if self.bridge.auth_runner:
            await self.bridge.auth_runner.cleanup()
        await self.bridge.http.close()
        await self.runner.cleanup()
        self.key_patch.stop()
        self.emit_patch.stop()

    async def test_login_rejects_oversized_and_invalid_responses(self):
        for mode in ['oversized', 'chunked', 'gzip', 'malformed', 'invalid_type', 'html']:
            with self.subTest(mode=mode):
                self.mode = mode
                self.events.clear()
                await self.bridge.login(self.base)
                event = next(e for e in self.events if e['type'] == 'open_url')
                query = parse_qs(urlsplit(event['url']).query)
                async with self.bridge.http.get(query['redirect_uri'][0],
                    params={'code': 'test-code', 'state': query['state'][0]}) as response:
                    self.assertEqual(response.status, 400)
                    self.assertNotIn('secret', await response.text())
                self.assertFalse(any(c.args[0] == 'store' for c in self.keyring.call_args_list))
                self.assertFalse(any(e['type'] == 'save_connection' for e in self.events))
                self.assertIsNone(self.bridge.auth_state)

    async def test_refresh_rejects_oversized_and_invalid_responses(self):
        for mode in ['oversized', 'chunked', 'gzip', 'malformed', 'invalid_type', 'html']:
            with self.subTest(mode=mode):
                self.mode = mode
                self.events.clear()
                await self.bridge.configure({'url': self.base, 'clientId': 'http://localhost/'})
                async with asyncio.timeout(2):
                    while not any(e.get('state') == 'offline' for e in self.events):
                        await asyncio.sleep(0.01)
                self.assertEqual(self.bridge.access, '')
                self.assertEqual(self.websocket_attempts, 0)
                await self.bridge.stop_connection()

    async def test_exact_byte_boundary_and_normal_response(self):
        for mode in ['valid', 'boundary']:
            self.mode = mode
            async with self.bridge.http.post(self.base + '/auth/token', auto_decompress=False,
                headers={'Accept-Encoding': 'identity'}) as response:
                token = await read_token_response(response, require_refresh=True)
                self.assertEqual(token['access_token'], 'valid')

    async def test_existing_request_timeout_still_applies(self):
        self.mode = 'slow'
        with self.assertRaises(TimeoutError):
            async with self.bridge.http.post(self.base + '/auth/token', auto_decompress=False,
                headers={'Accept-Encoding': 'identity'}, timeout=aiohttp.ClientTimeout(total=0.05)) as response:
                await read_token_response(response)

    async def test_oversized_body_never_reaches_json_parser(self):
        for mode in ['oversized', 'chunked', 'gzip']:
            self.mode = mode
            async with self.bridge.http.post(self.base + '/auth/token', auto_decompress=False,
                headers={'Accept-Encoding': 'identity'}) as response:
                with patch('bridge.json.loads') as parser:
                    with self.assertRaises(ValueError):
                        await read_token_response(response)
                    parser.assert_not_called()
