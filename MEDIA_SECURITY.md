# Bounded camera previews

Home Assistant media URLs never reach QML Image or MediaPlayer. The Python
bridge fetches bounded inputs; FFmpeg/ffprobe run in separate resource-limited
processes with only pipe input/output. QML reads locally generated fixed-size
PPM files, never the original compressed media. This protects the shell from
unbounded camera downloads and media decoding; it is not an OS security sandbox
or a claim that FFmpeg has no vulnerabilities.

## Network limits

- Same HA scheme, hostname and port; no URL credentials or fragments.
- No HTTP redirects. TLS verification remains enabled.
- Three-second connect, ten-second read and fifteen-second total request timeout.
- Snapshot and media segment: 8 MiB each; MP4 initialization: 1 MiB;
  HLS playlist: 64 KiB and at most 1,024 lines.
- Identity and gzip encoding only. Both compressed and decompressed responses
  have the same strict byte cap; gzip expansion cannot bypass the cap.
- At most 16 MiB downloaded in any rolling ten seconds; 256 MiB per preview.
- Hard preview lifetime: ten minutes, including pinned previews.
- Playlists poll at most once per second. At most three playlist levels,
  sixteen variants, one selected video variant and one active media session.
- Segments declare at most ten seconds; at most the newest two pending segments
  are processed. No encrypted media, external origins or byte ranges.
- On live failure, snapshots refresh no faster than once per five seconds.

## Decode limits

- Snapshot JPEG/PNG dimensions are parsed before decoding. Video dimensions
  are checked by an isolated ffprobe before decoding each segment.
- Maximum input: 4096 per axis and 8,388,608 pixels. FFmpeg also enforces the
  pixel cap internally, including changes after initial inspection.
- Every probe/decoder has a 1 GiB address-space hard limit, six-second CPU soft
  limit and seven-second CPU hard limit. Core dumps and regular-file writes are
  disabled. File descriptors are capped at 32.
- Parent deadlines: five seconds for a snapshot/probe, twenty seconds for a
  video segment including paced display. Timeout, replacement and dismissal
  kill and reap the subprocess. No concurrent media decoder jobs.
- One decoder/filter/output thread; 32 MiB maximum individual allocation;
  1 MiB probe size, one-second analysis and at most eight input streams.
- Only explicit JPEG, PNG, MPEG-TS or MOV demuxers. The protocol whitelist
  permits pipes only, preventing decoder-initiated network/file requests.
- Decoder environment excludes HA credentials. stderr is discarded to avoid
  leaking signed URLs or media metadata. No media URL is passed on argv.
- Output is exactly 640 × 360 RGB, at most 100 frames per segment and ten
  displayed frames per second. Probe JSON is capped at 16 KiB.

## Shell and temporary files

The bridge constructs PPM headers and verifies the exact raw frame length.
A private, randomly named temporary directory holds two alternating frame
files (0600), written via atomic rename. A third temporary file exists only
during a write. Qt must acknowledge the current frame within two seconds;
this bounds queued frames and prevents overwriting an in-flight image. Qt
loads at a fixed source size with caching disabled. The directory is removed
on normal completion/cancellation; forced termination of the bridge may leave
at most these bounded files for the OS temporary-directory cleanup.

## Verification

`tests/test_camera_media.py` covers malformed/oversized image headers, origin
restrictions, playlist limits, Content-Length and chunked byte limits, gzip
expansion, redirects, timeouts, total budget, fixed local output, decode failure,
frame backpressure, cancellation/reaping and real FFmpeg video output.
Integration tests verify that camera rules emit local files rather than URLs.
The maintainer's real HA/UniFi fragmented-MP4 stream was also exercised through
the helper. Other camera implementations may require additional compatibility
work; they must never bypass these limits.
