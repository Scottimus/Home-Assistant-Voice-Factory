"""Configuration and FFmpeg processing from the original batch generator."""
import csv
import json
import shutil
import subprocess

def truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y"}

def slug(value):
    allowed = []
    for char in value.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {" ", "-", "_"}:
            allowed.append("_")
    cleaned = "".join(allowed).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned

def load_lines(path, category=None, keys=None):
    wanted_keys = set(keys or [])
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if not truthy(row.get("enabled", "true")):
                continue
            if category and row.get("category") != category:
                continue
            if wanted_keys and row.get("key") not in wanted_keys:
                continue
            rows.append(row)
    return rows

def load_voice(path, voice_name):
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        return data[voice_name]
    except KeyError as exc:
        available = ", ".join(sorted(data))
        raise SystemExit(f"Voice profile '{voice_name}' not found. Available: {available}") from exc

def run_ffmpeg(wav_path, mp3_path, postprocess):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError as error:
            raise RuntimeError("Install imageio-ffmpeg or put FFmpeg on PATH") from error

    filters = []
    if postprocess.get("trim_silence", True):
        filters.append("silenceremove=start_periods=1:start_duration=0.05:start_threshold=-50dB")
    fade_ms = int(postprocess.get("fade_ms", 0) or 0)
    if fade_ms > 0:
        fade_seconds = fade_ms / 1000.0
        filters.append(f"afade=t=in:st=0:d={fade_seconds}")
        filters.append(f"areverse,afade=t=in:st=0:d={fade_seconds},areverse")
    if postprocess.get("normalize", True):
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(wav_path),
    ]
    if filters:
        command.extend(["-af", ",".join(filters)])
    command.extend([
        "-codec:a",
        "libmp3lame",
        "-b:a",
        str(postprocess.get("mp3_bitrate", "192k")),
        str(mp3_path),
    ])
    subprocess.run(command, check=True)
