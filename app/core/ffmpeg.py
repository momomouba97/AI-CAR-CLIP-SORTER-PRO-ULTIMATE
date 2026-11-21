import imageio_ffmpeg
import subprocess
import re

def ffmpeg_path():
    return imageio_ffmpeg.get_ffmpeg_exe()

def export_clip(source, destination, start_seconds, duration_seconds, crf=18, preset="veryfast"):
    cmd = [
        ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start_seconds:.3f}", "-i", str(source),
        "-t", f"{duration_seconds:.3f}",
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats", str(destination)
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1)
    last = 0.0
    if proc.stdout:
        for line in proc.stdout:
            if line.startswith("out_time_ms="):
                try:
                    ms = int(line.split("=", 1)[1].strip())
                    last = min(100.0, (ms / 1_000_000 / max(duration_seconds, .001)) * 100)
                except Exception:
                    pass
                yield last
    stderr = proc.stderr.read() if proc.stderr else ""
    code = proc.wait()
    if code != 0:
        raise RuntimeError(stderr.strip() or f"FFmpeg exited with code {code}")
    yield 100.0
