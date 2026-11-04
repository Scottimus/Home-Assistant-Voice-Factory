"""Filtered announcement generation with per-take checkpoints and CSV manifests."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import wave
from line_config import load_lines, load_voice, run_ffmpeg, slug


def synthesize(text, target, voice, engines):
    engine = voice["engine"]
    if engine == "sapi":
        if sys.platform != "win32":
            raise RuntimeError("SAPI demo requires Windows")
        environment = os.environ.copy()
        environment["VOICE_FACTORY_TEXT"] = text
        environment["VOICE_FACTORY_OUTPUT"] = str(target.resolve())
        script = ("$speaker=New-Object -ComObject SAPI.SpVoice; "
                  "$stream=New-Object -ComObject SAPI.SpFileStream; "
                  "$stream.Open($env:VOICE_FACTORY_OUTPUT,3,$false); "
                  "$speaker.AudioOutputStream=$stream; "
                  "[void]$speaker.Speak($env:VOICE_FACTORY_TEXT); $stream.Close()")
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
                       env=environment, check=True, capture_output=True, timeout=120)
    elif engine == "xtts":
        if engine not in engines:
            from TTS.api import TTS
            engines[engine] = TTS(model_path=voice["model_path"], config_path=voice["config_path"])
        engines[engine].tts_to_file(text=text, speaker_wav=voice["reference_audio"],
                                   language=voice.get("language", "en"), file_path=str(target))
    elif engine == "indextts2":
        if engine not in engines:
            sys.path.insert(0, voice["index_tts_dir"])
            from indextts.infer_v2 import IndexTTS2
            checkpoints = Path(voice["checkpoint_dir"])
            engines[engine] = IndexTTS2(cfg_path=str(checkpoints / "config.yaml"),
                                       model_dir=str(checkpoints), use_fp16=False,
                                       use_cuda_kernel=False, use_deepspeed=False)
        engines[engine].infer(spk_audio_prompt=voice["reference_audio"], text=text,
                             output_path=str(target), **voice.get("generation", {}))
    else:
        raise ValueError("Supported engines are sapi, xtts, and indextts2")


def generate(rows, voice, output, takes=0, skip_existing=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    keys = [slug(row["key"]) for row in rows]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("Line keys must be nonempty and unique after normalization")
    engines, manifest = {}, []
    for row, key in zip(rows, keys):
        text = row["text"].strip()
        count = int(takes or row.get("takes") or voice.get("default_takes", 1))
        if not text or count < 1:
            raise ValueError("Each line needs text and a positive take count")
        fingerprint = {"text": text, "voice": voice}
        if voice.get("reference_audio"):
            fingerprint["reference_sha256"] = hashlib.sha256(Path(voice["reference_audio"]).read_bytes()).hexdigest()
        signature = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
        for take in range(1, count + 1):
            stem = f"{key}_take{take:03d}"
            wav = output / (stem + ".wav")
            mp3 = output / (stem + ".mp3")
            checkpoint = output / (stem + ".json")
            status = "generated"
            try:
                completed = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
            except json.JSONDecodeError:
                completed = {}
            intact = (mp3.exists() and wav.exists()
                      and completed.get("mp3_sha256") == hashlib.sha256(mp3.read_bytes()).hexdigest()
                      and completed.get("wav_sha256") == hashlib.sha256(wav.read_bytes()).hexdigest())
            if skip_existing and intact and completed.get("signature") == signature:
                status = "skipped_existing"
            else:
                # Completed files are replaced only after synthesis and encoding both succeed.
                work = output / ".work" / uuid.uuid4().hex
                work.mkdir(parents=True)
                temporary_wav = work / "take.wav"
                temporary_mp3 = work / "take.mp3"
                synthesize(text, temporary_wav, voice, engines)
                with wave.open(str(temporary_wav)) as audio:
                    if audio.getnframes() == 0:
                        raise ValueError("Speech engine returned empty audio")
                run_ffmpeg(temporary_wav, temporary_mp3, voice.get("postprocess", {}))
                os.replace(temporary_wav, wav)
                os.replace(temporary_mp3, mp3)
                temporary_checkpoint = work / "checkpoint.json"
                temporary_checkpoint.write_text(json.dumps({
                    "signature": signature, "mp3_sha256": hashlib.sha256(mp3.read_bytes()).hexdigest(),
                    "wav_sha256": hashlib.sha256(wav.read_bytes()).hexdigest()}), encoding="utf-8")
                os.replace(temporary_checkpoint, checkpoint)
            manifest.append({"key": key, "category": row.get("category", ""), "take": take,
                             "engine": voice["engine"], "wav": wav.name, "mp3": mp3.name, "status": status})
            with (output / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
                writer.writeheader()
                writer.writerows(manifest)
    return manifest


def main():
    root = Path(__file__).parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", default="system_demo")
    parser.add_argument("--voices", type=Path, default=root / "config/voices.example.json")
    parser.add_argument("--lines", type=Path, default=root / "config/lines.example.csv")
    parser.add_argument("--output", type=Path, default=root / "output")
    parser.add_argument("--category")
    parser.add_argument("--key", action="append")
    parser.add_argument("--takes", type=int, default=0)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()
    rows = load_lines(args.lines, category=args.category, keys=args.key)
    if not rows:
        parser.error("No enabled lines matched the filters")
    result = generate(rows, load_voice(args.voices, args.voice), args.output, args.takes, args.skip_existing)
    print(f"Processed {len(result)} takes. Manifest saved under {args.output}")


if __name__ == "__main__":
    main()
