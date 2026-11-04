# Home Assistant Voice Factory

Generate filtered announcement batches with multiple takes, FFmpeg postprocessing, resumable per-take checkpoints, and CSV manifests. The configuration loading and audio filters originate in an existing local IndexTTS2 batch pipeline.

## Run the Windows demo

```sh
python -m pip install -r requirements.txt
python generate_voice_batch.py --category timer
python generate_voice_batch.py --category timer --skip-existing
```

The bundled profile uses Windows' installed synthetic system voice. The two timer takes are real speech files. A rerun skips completed takes with the same text, configuration, and reference-file hash. Interrupted synthesis is retried because a checkpoint is written only after audio encoding succeeds. Run one process per output directory.

[Listen to the system-voice sample](examples/timer.wav). It says “The sample timer has finished.” This is the bundled demo voice, generated locally through Windows SAPI.

Run the per-take retry and changed-input checks with `python -m unittest discover -s tests -v`.

The original IndexTTS2 workflow remains available through a local JSON profile with `engine`, `index_tts_dir`, `checkpoint_dir`, and `reference_audio`. Install that engine separately and review its model terms. An XTTS profile uses `engine: xtts`, `model_path`, `config_path`, `reference_audio`, and optional `language`. Keep model paths and personal reference recordings in a `.local.json` file.

The demo profile demonstrates batch orchestration using a system voice. Model-based cloning requires its own configured runtime and a reference recording cleared for that use. Generated files stay in the ignored `output/` folder. Manifest filenames are relative and contain no local machine paths.
