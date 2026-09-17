#!/usr/bin/env python3
"""Resource limits are installed before exec; FFmpeg only receives bounded stdin."""
import os
import resource
import sys


def main():
    mode, demuxer = sys.argv[1:]
    if mode not in ("probe", "frame", "video") or demuxer not in ("mjpeg", "png_pipe", "mov", "mpegts"):
        raise SystemExit(2)
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_CPU, (6, 7))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    common = ["-v", "error", "-max_alloc", "33554432", "-protocol_whitelist", "pipe",
              "-threads", "1", "-probesize", "1048576", "-analyzeduration", "1000000",
              "-max_streams", "8", "-max_pixels", "8388608", "-f", demuxer]
    if mode == "probe":
        command = ["ffprobe", *common, "-i", "pipe:0", "-select_streams", "v:0",
                   "-show_entries", "stream=width,height", "-of", "json"]
    else:
        command = ["ffmpeg", "-nostdin", *common, "-i", "pipe:0", "-map", "0:v:0",
                   "-an", "-sn", "-dn", "-filter_threads", "1", "-threads", "1",
                   "-vf", ("fps=10," if mode == "video" else "") + "scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2",
                   "-frames:v", "1" if mode == "frame" else "100", "-t", "10",
                   "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "OPENBLAS_NUM_THREADS": "1",
                   "OMP_NUM_THREADS": "1", "HOME": "/nonexistent"}
    os.execvpe(command[0], command, environment)


if __name__ == "__main__":
    main()
