from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
from generate_voice_batch import generate


def synthesize(text, target, voice, engines):
    with wave.open(str(target), "wb") as audio:
        audio.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x00\x00" * 100)


def encode(source, target, settings):
    target.write_bytes(b"test encoded audio")


class BatchTests(unittest.TestCase):
    def test_multiple_takes_and_changed_text(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = [{"key": "timer", "text": "Sample timer", "takes": "2"}]
            with patch("generate_voice_batch.synthesize", side_effect=synthesize) as engine, \
                    patch("generate_voice_batch.run_ffmpeg", side_effect=encode):
                self.assertEqual(len(generate(rows, {"engine": "sapi"}, folder)), 2)
                rerun = generate(rows, {"engine": "sapi"}, folder, skip_existing=True)
                self.assertTrue(all(row["status"] == "skipped_existing" for row in rerun))
                self.assertEqual(engine.call_count, 2)
                rows[0]["text"] = "Changed timer"
                generate(rows, {"engine": "sapi"}, folder, skip_existing=True)
                self.assertEqual(engine.call_count, 4)

    def test_interrupted_take_is_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = [{"key": "timer", "text": "Timer"}]
            with patch("generate_voice_batch.synthesize", side_effect=RuntimeError("interrupted")):
                with self.assertRaises(RuntimeError):
                    generate(rows, {"engine": "sapi"}, folder)
            with patch("generate_voice_batch.synthesize", side_effect=synthesize), \
                    patch("generate_voice_batch.run_ffmpeg", side_effect=encode):
                self.assertEqual(generate(rows, {"engine": "sapi"}, folder, skip_existing=True)[0]["status"], "generated")


if __name__ == "__main__":
    unittest.main()
