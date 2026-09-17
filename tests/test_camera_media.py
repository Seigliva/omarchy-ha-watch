import asyncio
import contextlib
import gzip
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

import aiohttp
from aiohttp import web

from camera_media import CameraMedia, FRAME_BYTES, MediaLimit, image_format, playlist, safe_url


def png(width=2, height=2):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + b'\xff\0\0' * width) * height)) + chunk(b'IEND', b''))


class MediaValidation(unittest.TestCase):
    def test_image_dimensions_and_format(self):
        self.assertEqual(image_format(png()), 'png_pipe')
        with self.assertRaises(MediaLimit):
            image_format(png()[:16] + struct.pack('>II', 100000, 100000) + png()[24:])
        for data in [b'', b'<svg/>', b'\xff\xd8\xff\xc0\0\1', b'\x89PNG\r\n\x1a\n']:
            with self.subTest(data=data), self.assertRaises(MediaLimit):
                image_format(data)

    def test_origin_restrictions(self):
        base = 'https://ha.local/api/hls/master.m3u8'
        self.assertEqual(safe_url(base, 'segment.ts'), 'https://ha.local/api/hls/segment.ts')
        for path in ['https://other.local/a', '//evil/a', 'http://ha.local/a', 'file:///etc/passwd',
                     'https://u:p@ha.local/a', '/a\\b', '/a\n', '/a#fragment']:
            with self.subTest(path=path), self.assertRaises(MediaLimit):
                safe_url(base, path)

    def test_playlist_limits(self):
        variants, segments = playlist(b'#EXTM3U\n#EXTINF:2,\nsegment.ts\n')
        self.assertEqual(segments, [('segment.ts', 2, None)])
        for data in [b'#EXTM3U\n#EXTINF:999,\na.ts', b'#EXTM3U\n#EXTINF:nan,\na.ts',
                     b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128', b'#EXTM3U\n#EXT-X-BYTERANGE:10',
                     b'#EXTM3U\na.ts', b'not a playlist']:
            with self.subTest(data=data), self.assertRaises(MediaLimit):
                playlist(data)


class MediaTransport(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        def emit(kind, **values):
            self.events.append(dict(type=kind, **values))
            if kind == 'image':
                self.media.acknowledge(values['frame'])
        self.media = CameraMedia('http://ha.local', None, emit, 1)
        self.directory = tempfile.TemporaryDirectory()
        self.media.folder = self.directory.name
        self.runner = None
        self.media.http = aiohttp.ClientSession(auto_decompress=False)

    async def asyncTearDown(self):
        await self.media.http.close()
        if self.runner:
            await self.runner.cleanup()
        self.directory.cleanup()

    async def server(self, handler):
        app = web.Application()
        app.router.add_get('/{path:.*}', handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.media.base = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
        return self.media.base

    async def test_snapshot_is_fixed_local_raw_image(self):
        data = png()
        await self.media.worker(data, image_format(data), 'frame')
        result = self.events[-1]
        self.assertTrue(result['url'].startswith('file://'))
        content = Path(result['url'][7:]).read_bytes()
        self.assertEqual(len(content), FRAME_BYTES + len(b'P6\n640 360\n255\n'))
        self.assertTrue(content.startswith(b'P6\n640 360\n255\n'))
        self.assertFalse(result['live'])

    async def test_bounded_content_length_and_chunked_response(self):
        async def handler(request):
            if request.path == '/length':
                return web.Response(body=b'x' * 100)
            response = web.StreamResponse()
            await response.prepare(request)
            with contextlib.suppress(ConnectionResetError):
                await response.write(b'x' * 100)
                await response.write_eof()
            return response
        base = await self.server(handler)
        for path in ['/length', '/chunked']:
            with self.subTest(path=path), self.assertRaises(MediaLimit):
                await self.media.fetch(base + path, 10)

    async def test_redirect_and_compressed_response_are_rejected(self):
        async def handler(request):
            if request.path == '/redirect':
                raise web.HTTPFound('/target')
            return web.Response(body=b'x', headers={'Content-Encoding': 'gzip'})
        base = await self.server(handler)
        for path in ['/redirect', '/compressed']:
            with self.assertRaises(MediaLimit):
                await self.media.fetch(base + path, 100)

    async def test_gzip_has_a_decompressed_byte_cap(self):
        async def handler(request):
            return web.Response(body=gzip.compress(b'x' * 10000), headers={'Content-Encoding': 'gzip'})
        base = await self.server(handler)
        self.assertEqual(await self.media.fetch(base, 10000), b'x' * 10000)
        with self.assertRaises(MediaLimit):
            await self.media.fetch(base, 100)

    async def test_session_budget_is_enforced(self):
        async def handler(request):
            return web.Response(body=b'123456')
        base = await self.server(handler)
        with patch('camera_media.SESSION_BYTES', 10):
            self.assertEqual(await self.media.fetch(base, 100), b'123456')
            with self.assertRaises(MediaLimit):
                await self.media.fetch(base, 100)

    async def test_decode_failure_and_output_backpressure(self):
        with self.assertRaises(MediaLimit):
            await self.media.worker(b'invalid data', 'mpegts', 'video')
        self.media.emit = lambda *a, **k: None
        with self.assertRaises(TimeoutError):
            await self.media.publish(b'\0' * FRAME_BYTES, True)
        self.assertEqual(len(list(Path(self.directory.name).glob('*.ppm'))), 1)

    async def test_download_timeout(self):
        async def handler(request):
            await asyncio.sleep(0.2)
            return web.Response(body=b'x')
        base = await self.server(handler)
        timeout = aiohttp.ClientTimeout(total=0.05, connect=0.05, sock_read=0.05)
        with patch('camera_media.aiohttp.ClientTimeout', return_value=timeout):
            with self.assertRaises(TimeoutError):
                await self.media.fetch(base, 100)

    async def test_cancellation_reaps_decoder(self):
        original = asyncio.create_subprocess_exec
        processes = []
        async def capture(*args, **kwargs):
            process = await original(*args, **kwargs)
            processes.append(process)
            return process
        self.media.emit = lambda *a, **k: None
        with patch('camera_media.asyncio.create_subprocess_exec', side_effect=capture):
            task = asyncio.create_task(self.media.worker(png(), 'png_pipe', 'frame'))
            async with asyncio.timeout(3):
                while not self.media.waiting_id:
                    await asyncio.sleep(0.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(processes)
        self.assertTrue(all(p.returncode is not None for p in processes))

    async def test_video_decodes_in_worker(self):
        process = await asyncio.create_subprocess_exec('ffmpeg', '-v', 'error', '-f', 'lavfi',
            '-i', 'testsrc=size=160x90:rate=10', '-t', '0.5', '-c:v', 'libx264', '-threads', '1',
            '-pix_fmt', 'yuv420p', '-f', 'mpegts', 'pipe:1', stdout=asyncio.subprocess.PIPE)
        data, _ = await process.communicate()
        self.assertEqual(process.returncode, 0)
        await self.media.worker(data, 'mpegts', 'probe')
        await self.media.worker(data, 'mpegts', 'video', True)
        self.assertGreaterEqual(len(self.events), 4)
        self.assertTrue(all(e['live'] and e['url'].startswith('file://') for e in self.events))
        self.assertLessEqual(len(list(Path(self.directory.name).glob('*.ppm'))), 2)
