"""Bounded HA media transport. No remote media is ever handed to the shell."""
import asyncio
from collections import deque
import contextlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import tempfile
import time
import zlib
from urllib.parse import urljoin, urlsplit

import aiohttp

FRAME_BYTES = 640 * 360 * 3
MAX_IMAGE = 8 * 1024 * 1024
MAX_SEGMENT = 8 * 1024 * 1024
MAX_PLAYLIST = 64 * 1024
MAX_INIT = 1024 * 1024
MAX_PIXELS = 8 * 1024 * 1024
SESSION_SECONDS = 600
SESSION_BYTES = 256 * 1024 * 1024
WORKER = Path(__file__).with_name("media_worker.py")


class MediaLimit(ValueError):
    pass


def dimensions(width, height):
    if not (0 < width <= 4096 and 0 < height <= 4096 and width * height <= MAX_PIXELS):
        raise MediaLimit("Image dimensions exceed preview limits")


def image_format(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 33 or data[12:16] != b"IHDR" or data[8:12] != b"\0\0\0\r":
            raise MediaLimit("Invalid PNG header")
        dimensions(*struct.unpack(">II", data[16:24]))
        return "png_pipe"
    if not data.startswith(b"\xff\xd8"):
        raise MediaLimit("Only JPEG and PNG snapshots are supported")
    offset = 2
    while offset < len(data):
        if data[offset] != 255:
            break
        while offset < len(data) and data[offset] == 255:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in (0xD9, 0xDA):
            break
        if marker == 1 or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset:offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        if marker in (0xC0, 0xC1, 0xC2):
            if length < 8:
                break
            height, width = struct.unpack(">HH", data[offset + 3:offset + 7])
            dimensions(width, height)
            return "mjpeg"
        offset += length
    raise MediaLimit("Invalid or unsupported JPEG header")


def safe_url(base, value):
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value) or "\\" in value:
        raise MediaLimit("Invalid media address")
    target = urlsplit(urljoin(base, value))
    origin = urlsplit(base)
    if (target.scheme not in ("http", "https") or target.scheme != origin.scheme
            or target.hostname != origin.hostname or target.port != origin.port
            or target.username or target.password or target.fragment):
        raise MediaLimit("Media must stay on the Home Assistant origin")
    return target.geturl()


def playlist(data):
    text = data.decode("utf-8", errors="strict")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != "#EXTM3U" or len(lines) > 1024:
        raise MediaLimit("Invalid HLS playlist")
    # Encrypted and byte-range streams need additional transport controls.
    if any(line.startswith(("#EXT-X-KEY:", "#EXT-X-BYTERANGE:")) for line in lines):
        raise MediaLimit("Encrypted/range HLS is not supported")
    variants, segments = [], []
    variant, duration, init = False, None, None
    for line in lines[1:]:
        if line.startswith("#EXT-X-STREAM-INF:"):
            variant = True
        elif line.startswith("#EXT-X-MAP:"):
            match = re.fullmatch(r'#EXT-X-MAP:URI="([^"\r\n]+)"', line)
            if not match:
                raise MediaLimit("Unsupported HLS initialization")
            init = match[1]
        elif line.startswith("#EXTINF:"):
            duration = float(line[8:].split(",")[0])
            if not math.isfinite(duration) or not 0 < duration <= 10:
                raise MediaLimit("HLS segment duration exceeds limits")
        elif not line.startswith("#"):
            if variant:
                variants.append(line)
                variant = False
            elif duration is not None:
                segments.append((line, duration, init))
                duration = None
            else:
                raise MediaLimit("Unexpected HLS media entry")
    if len(variants) > 16 or len(segments) > 100:
        raise MediaLimit("HLS playlist exceeds limits")
    return variants, segments


class CameraMedia:
    def __init__(self, base, rpc, emit, serial):
        self.base, self.rpc, self.emit, self.serial = base, rpc, emit, serial
        self.total = 0
        self.window = deque()
        self.deadline = time.monotonic() + SESSION_SECONDS
        self.ack = asyncio.Event()
        self.frame_id = 0
        self.waiting_id = None
        self.http = None
        self.folder = None

    def acknowledge(self, frame):
        if frame == self.waiting_id:
            self.ack.set()

    async def fetch(self, url, cap):
        if self.total >= SESSION_BYTES or time.monotonic() >= self.deadline:
            raise MediaLimit("Preview transfer budget exhausted")
        url = safe_url(self.base, url)
        timeout = aiohttp.ClientTimeout(total=15, connect=3, sock_read=10)
        async with self.http.get(url, timeout=timeout, allow_redirects=False,
                                 headers={"Accept-Encoding": "identity"}, auto_decompress=False) as response:
            encoding = response.headers.get("Content-Encoding", "identity").lower()
            if response.status != 200 or encoding not in ("identity", "gzip"):
                raise MediaLimit("Media response rejected")
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
            if response.content_length is not None and response.content_length > cap:
                raise MediaLimit("Media download exceeds size limit")
            data = bytearray()
            received = 0
            async for chunk in response.content.iter_chunked(16384):
                now = time.monotonic()
                while self.window and self.window[0][0] < now - 10:
                    self.window.popleft()
                self.window.append((now, len(chunk)))
                self.total += len(chunk)
                received += len(chunk)
                if (received > cap or self.total > SESSION_BYTES
                        or sum(size for _, size in self.window) > 16 * 1024 * 1024
                        or now > self.deadline):
                    raise MediaLimit("Media transfer budget exceeded")
                if decoder:
                    try:
                        chunk = decoder.decompress(chunk, cap - len(data) + 1)
                    except zlib.error as error:
                        raise MediaLimit("Invalid compressed media response") from error
                if len(data) + len(chunk) > cap:
                    raise MediaLimit("Decompressed media exceeds size limit")
                data.extend(chunk)
            if decoder and (not decoder.eof or decoder.unused_data):
                raise MediaLimit("Invalid compressed media response")
            return bytes(data)

    async def worker(self, data, demuxer, mode, live=False):
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-I", str(WORKER), mode, demuxer,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=FRAME_BYTES)

        async def feed():
            try:
                process.stdin.write(data)
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                process.stdin.close()
        writer = asyncio.create_task(feed())
        try:
            async with asyncio.timeout(20 if mode == "video" else 5):
                if mode == "probe":
                    result = await process.stdout.read(16385)
                    if len(result) > 16384:
                        raise MediaLimit("Probe output exceeds limit")
                    # Read to EOF without permitting an unbounded JSON response.
                    while chunk := await process.stdout.read(16385 - len(result)):
                        result += chunk
                        if len(result) > 16384:
                            raise MediaLimit("Probe output exceeds limit")
                    await process.wait()
                    if process.returncode:
                        raise MediaLimit("Media inspection failed")
                    streams = json.loads(result).get("streams", [])
                    if len(streams) != 1:
                        raise MediaLimit("Missing video stream")
                    dimensions(streams[0].get("width", 0), streams[0].get("height", 0))
                    return
                count = 0
                while True:
                    try:
                        frame = await process.stdout.readexactly(FRAME_BYTES)
                    except asyncio.IncompleteReadError as error:
                        if error.partial:
                            raise MediaLimit("Truncated decoded frame") from None
                        break
                    count += 1
                    if count > (100 if mode == "video" else 1):
                        raise MediaLimit("Too many decoded frames")
                    await self.publish(frame, live)
                await process.wait()
                if process.returncode or not count:
                    raise MediaLimit("Media decoding failed")
        finally:
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
            await process.wait()
            writer.cancel()
            await asyncio.gather(writer, return_exceptions=True)

    async def publish(self, frame, live):
        if len(frame) != FRAME_BYTES:
            raise MediaLimit("Invalid raw frame length")
        # Only fixed-sized raw RGB reaches Qt's trivial PPM reader. Two slots
        # bound disk use; acknowledgement prevents overwriting an in-flight file.
        self.frame_id += 1
        target = Path(self.folder) / f"frame-{self.frame_id % 2}.ppm"
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(b"P6\n640 360\n255\n" + frame)
        temporary.chmod(0o600)
        temporary.replace(target)
        self.ack.clear()
        self.waiting_id = self.frame_id
        started = time.monotonic()
        self.emit("image", serial=self.serial, url=target.as_uri(), frame=self.frame_id, live=live)
        await asyncio.wait_for(self.ack.wait(), timeout=2)
        if live:
            await asyncio.sleep(max(0, 0.1 - (time.monotonic() - started)))

    async def snapshot(self):
        signed = await self.rpc("auth/sign_path", path="/api/camera_proxy/" + self.camera, expires=30)
        data = await self.fetch(safe_url(self.base, signed["path"]), MAX_IMAGE)
        demuxer = image_format(data)  # Validate compressed dimensions before decode.
        await self.worker(data, demuxer, "frame")

    async def stream(self):
        result = await self.rpc("camera/stream", entity_id=self.camera, format="hls")
        url = safe_url(self.base, result["url"])
        for _ in range(3):
            variants, segments = playlist(await self.fetch(url, MAX_PLAYLIST))
            if not variants:
                break
            url = safe_url(url, variants[0])
        else:
            raise MediaLimit("Too many nested HLS playlists")
        seen = deque(maxlen=100)
        init_url, init_data = None, b""
        while True:
            if segments:
                pending = [s for s in segments if safe_url(url, s[0]) not in seen]
                # Stay near the live edge instead of queuing an unlimited backlog.
                for path, duration, init in pending[-2:]:
                    segment_url = safe_url(url, path)
                    if init:
                        new_init = safe_url(url, init)
                        if init_url != new_init:
                            init_data = await self.fetch(new_init, MAX_INIT)
                            init_url = new_init
                    else:
                        init_data, init_url = b"", None
                    data = init_data + await self.fetch(segment_url, MAX_SEGMENT)
                    demuxer = "mov" if init else "mpegts"
                    await self.worker(data, demuxer, "probe")
                    await self.worker(data, demuxer, "video", live=True)
                    seen.append(segment_url)
            await asyncio.sleep(1)
            variants, segments = playlist(await self.fetch(url, MAX_PLAYLIST))
            if variants:
                raise MediaLimit("Unexpected HLS playlist change")

    async def run(self, camera):
        self.camera = camera
        with tempfile.TemporaryDirectory(prefix="ha-watch-media-") as folder:
            self.folder = folder
            async with aiohttp.ClientSession(auto_decompress=False) as self.http:
                try:
                    async with asyncio.timeout(SESSION_SECONDS):
                        with contextlib.suppress(Exception):
                            await self.snapshot()
                        try:
                            await self.stream()
                        except Exception:
                            self.emit("video_unavailable", serial=self.serial)
                        # A rejected live stream never reaches Qt. Bounded snapshots
                        # remain available, with a fixed refresh interval and deadline.
                        while True:
                            await asyncio.sleep(5)
                            try:
                                await self.snapshot()
                            except Exception:
                                self.emit("media_error", serial=self.serial,
                                          message="Camera preview unavailable or exceeds limits")
                except TimeoutError:
                    self.emit("media_error", serial=self.serial, message="Preview limit reached · reopen to continue")
