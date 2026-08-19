# Parrot 🦜

> Easy local voice cloning — a TTS server for Apple Silicon

**English** | [한국어](README.ko.md)

A local FastAPI-based TTS server that runs on Apple Silicon (macOS + MLX). Drop a short reference voice and its transcript into the `refs` folder, and Parrot generates an MP3 of your text read in that voice. Like a parrot mimicking a voice, it's handy for local use — alarm sounds, narration, short speech synthesis, and more.

Requests go into an internal queue (`asyncio.Queue`) and are processed one at a time. The default engine (`TTS_ENGINE=worker`) keeps the model resident in an isolated child process for fast repeat requests, and automatically unloads it after a period of idle time.

Flow:

```text
Client
  -> POST http://localhost:8010/tts   { "ref_id": "...", "text": "..." }
  -> server.py (serial queue)
  -> fishaudio-s2-pro-8bit-mlx
  -> returns MP3 bytes
```

---

## Environment

| Item | Value |
|------|-------|
| Model | `fishaudio-s2-pro-8bit-mlx` |
| Runtime | Apple Silicon macOS + MLX |
| Python | `3.13`+ |
| Python packages | `mlx-speech`, `fastapi`, `uvicorn`, `python-multipart`, `psutil`, `numpy`, `soundfile` |
| External tool | `ffmpeg` (MP3 encoding) |
| Default venv path | `{parrot}/.venv` |
| Default model path | `{parrot}/fishaudio-s2-pro-8bit-mlx` |
| Default refs path | `{parrot}/refs` (external folder via `TTS_REFS_DIR`) |
| Default temp path | `/tmp/fish_tts_temp` |
| Port | `8010` |

The model is the MLX model `mlx-community/fishaudio-s2-pro-8bit-mlx` from Hugging Face.

---

## Folder structure

```text
parrot/
├── fishaudio-s2-pro-8bit-mlx/   # Model files (not in git; downloaded locally)
├── refs/                        # Reference voices (wav + txt)
├── output/                      # Generated MP3s (not in git; created by setup.sh)
├── .venv/                       # Python virtualenv (not in git)
├── setup.sh                     # one-shot setup + run script
├── server.py                    # FastAPI server
├── tts_engine.py                # Generation engines (worker / api / cli)
├── tts_worker.py                # Isolated model-resident worker
├── tts_queue.py                 # Serial processing queue
├── tts_logging.py               # Logging setup
├── tts.sh                       # start/stop/status script
├── macapp/                      # (optional) menu-bar manager app source
└── README.md
```

---

## refs file rules

A reference voice is a `wav + txt` pair.

```text
refs/
├── myvoice.wav
├── myvoice.txt
└── ...
```

Rules:

- `ref_id` is the filename without extension. e.g. `myvoice`
- If `myvoice.wav` exists, `myvoice.txt` must exist too.
- The `txt` file should contain, as accurately as possible, what is actually spoken in the wav.
- Short, clean reference audio produces better quality.

> ⚠️ Only use reference voices you own or have permission to use. Cloning or distributing someone else's voice without consent may violate voice/personality and publicity rights.

---

## Quick start (one-shot setup)

`setup.sh` does everything below in one command, using the repository path as the base: it creates the venv, installs packages, downloads the model, creates the `output/` folder, saves your chosen paths to `.parrot.env`, and starts the server.

```bash
brew install python@3.13 ffmpeg   # prerequisites (once)
./setup.sh
```

When it finishes the server is already running at `http://localhost:8010`. Manage it afterwards with `./tts.sh start|stop|status|restart`.

### Changing paths

Every path is overridable via a flag or an environment variable of the same name. The repository path is only the default base.

```bash
# store generated MP3s, the model, and use a different port elsewhere
./setup.sh --output ~/tts-out --model /Volumes/ext/fish-model --port 9000

# same via environment variables
TTS_OUTPUT_DIR=~/tts-out ./setup.sh
```

| Flag | Env var | Default |
|------|---------|---------|
| `--venv` | `PARROT_VENV` | `{parrot}/.venv` |
| `--model` | `FISH_S2_MODEL_PATH` | `{parrot}/fishaudio-s2-pro-8bit-mlx` |
| `--refs` | `TTS_REFS_DIR` | `{parrot}/refs` |
| `--output` | `TTS_OUTPUT_DIR` | `{parrot}/output` |
| `--temp` | `TTS_TEMP_DIR` | `/tmp/fish_tts_temp` |
| `--port` | `TTS_PORT` | `8010` |
| `--host` | `TTS_HOST` | `0.0.0.0` |
| `--model-repo` | `PARROT_MODEL_REPO` | `mlx-community/fishaudio-s2-pro-8bit-mlx` |
| `--python` | `PARROT_PYTHON` | auto-detected `python3.13+` |

Other options: `--no-start` (set up but don't launch the server), `--help` (full list). The chosen paths are written to `.parrot.env`, which `tts.sh` reads on every start — so later `./tts.sh start` reuses them. Priority is **pre-exported env var > `.parrot.env` > built-in default**, so you can still override a single run with e.g. `TTS_OUTPUT_DIR=/other ./tts.sh start`.

Prefer to run the steps manually? Follow the sections below instead.

---

## Manual setup (step by step)

Prefer to understand each step, or need a custom setup? Run the steps below in order from the repository root. (All of them are automated by `setup.sh` — see the note at the end.)

### 1. Install prerequisites

`mlx-speech` requires Python 3.13+. The system `python3` on macOS is often 3.9, so install `python@3.13`. `ffmpeg` is required for MP3 encoding.

```bash
brew install python@3.13 ffmpeg
```

### 2. Create the virtualenv

Create the venv with `python3.13` from the repo root.

```bash
cd parrot
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

If you already created `.venv` with Python 3.9, run `rm -rf .venv` and repeat this step.

### 3. Install packages

```bash
pip install mlx-speech fastapi uvicorn python-multipart huggingface_hub psutil numpy soundfile
```

### 4. Download the model

The model is not committed to git; download it into the local `fishaudio-s2-pro-8bit-mlx` folder.

```bash
hf download mlx-community/fishaudio-s2-pro-8bit-mlx \
  --local-dir ./fishaudio-s2-pro-8bit-mlx
```

To store the model elsewhere, set `FISH_S2_MODEL_PATH` before starting the server.

```bash
export FISH_S2_MODEL_PATH=/path/to/fishaudio-s2-pro-8bit-mlx
```

### 5. (Optional) Choose where generated MP3s are saved

By default generated MP3s are returned and then deleted. To keep a copy, point `TTS_OUTPUT_DIR` at a folder (created if missing).

```bash
export TTS_OUTPUT_DIR="$(pwd)/output"
```

### 6. Start the server

```bash
./tts.sh start
```

Then open `http://localhost:8010/health`. Managing the server (`start`/`stop`/`status`/`restart`) is covered in the next section.

> 💡 **All six steps at once:** everything above — venv, packages, model download, `output/` folder, and starting the server — is done automatically by `./setup.sh`. See **[Quick start](#quick-start-one-shot-setup)** above. Use the manual steps only when you want to run or customize each part yourself.

---

## Running the server

```bash
cd parrot
./tts.sh start     # start
./tts.sh status    # status
./tts.sh stop      # stop
./tts.sh restart   # restart
```

View logs:

```bash
tail -f parrot/tts.log
```

---

## Parrot macOS app (optional)

The `macapp/` folder contains the source of a macOS app that starts, watches, and monitors the TTS server from the menu bar (macOS 14+). See **[macapp/README.md](macapp/README.md)** for design, features, and troubleshooting.

Build the app from source (requires Xcode + xcodegen):

```bash
./macapp/build-app.sh
open macapp/dist/Parrot.app
```

- Starts the server automatically on launch (attaches if already running via `tts.sh`)
- Auto-restart on crash (1s→5s→15s, stops after 3 consecutive failures)
- Stops the server on quit (an "keep server running" option is available in settings)
- Change paths, port, and model TTL in Settings (⌘,)

---

## API

### Health check

```bash
curl http://localhost:8010/health
```

```json
{"status":"ok"}
```

### Status

```bash
curl http://localhost:8010/status
```

```json
{
  "server": "ok",
  "uptime_sec": 1234,
  "queue_len": 0,
  "current_job": null,
  "recent": [{"ref_id": "myvoice", "text_len": 10, "ok": true, "error": null, "duration_sec": 8.2, "finished_at": "2026-08-19T12:00:00"}],
  "totals": {"ok": 12, "error": 0},
  "engine": "worker",
  "model_resident": true,
  "memory_mb": 3100
}
```

### List references

```bash
curl http://localhost:8010/refs
```

```json
{
  "refs": [
    {"ref_id": "myvoice", "has_txt": true}
  ]
}
```

### Generate TTS

```bash
curl -X POST http://localhost:8010/tts \
  -H "Content-Type: application/json" \
  -d '{"ref_id":"myvoice","text":"Good morning. Time to wake up."}' \
  --output test.mp3
```

The response is an `audio/mpeg` MP3 binary. The example above saves `test.mp3` in the current folder.

Request parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ref_id` | string | Y | Filename in the `refs` folder, without extension |
| `text` | string | Y | Text to synthesize |

---

## Adding reference voices

Put a `wav + txt` pair into `refs/` (or the folder set by `TTS_REFS_DIR`).

```bash
cp newvoice.wav parrot/refs/new_ref.wav
echo "Type here exactly what is spoken in the wav" > parrot/refs/new_ref.txt

curl http://localhost:8010/refs
```

Changes are reflected immediately in `/refs` and `/tts` — no server restart needed.

---

## Calling from other services

Other processes on the same machine call `http://localhost:8010/tts`. To reach the server from another network namespace (e.g. a Docker container), use the host address.

```text
# Calling the host's TTS server from inside a container
http://host.docker.internal:8010/tts
```

In that case the server must be bound to an interface reachable from the container (see `TTS_HOST`). Be sure to read the **Security notes** below.

---

## Environment variables

`server.py` and `tts.sh` support the following environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `FISH_S2_MODEL_PATH` | `{parrot}/fishaudio-s2-pro-8bit-mlx` | Model folder path |
| `TTS_REFS_DIR` | `{parrot}/refs` | Reference voice folder. Set to use an external folder (the repo's `refs/` is checked first, then this folder) |
| `TTS_TEMP_DIR` | `/tmp/fish_tts_temp` | Temp folder for WAV/MP3 generation |
| `TTS_OUTPUT_DIR` | *(empty)* | Folder to keep generated MP3s. When set, each result is also saved here as `{timestamp}_{ref_id}_{id}.mp3`. Empty means don't keep them (deleted after the response). `setup.sh` sets this to `{parrot}/output` |
| `TTS_PORT` | `8010` | Server port used by `tts.sh` |
| `TTS_HOST` | `0.0.0.0` | Bind address used by `tts.sh`. Use `127.0.0.1` to restrict to local only (see Security notes) |
| `TTS_ENGINE` | `worker` | `worker`=model resident in an isolated child process (fast + crash-isolated, recommended), `api`=in-process resident (fast, but a crash takes down the whole server), `cli`=runs the mlx-speech CLI per request. Falls back to cli if init fails |
| `TTS_WORKER_TIMEOUT` | `120` | Timeout (sec) waiting for a generation result in the worker engine. On timeout the worker is killed and restarted |
| `TTS_WORKER_STARTUP_TIMEOUT` | `120` | Timeout (sec) waiting for worker model load (ready) |
| `TTS_MODEL_TTL_SEC` | `600` | Seconds until an idle model is unloaded (worker/api). `0` or less keeps it resident permanently (no cold start, but holds memory — recommended only on a dedicated machine) |
| `TTS_REF_CACHE_MAX` | `32` | Max number of per-ref reference encodings the worker engine caches. Skips re-encoding when repeatedly generating the same voice (oldest evicted when exceeded) |
| `TTS_MP3_BITRATE` | `96k` | Output MP3 bitrate. Can be lowered for speech (e.g. `64k`), reducing response size and encode time |
| `TTS_MP3_CHANNELS` | `1` | Output MP3 channel count. Mono (`1`) recommended for speech |
| `TTS_MP3_SAMPLE_RATE` | `24000` | Output MP3 sample rate (Hz). Empty string keeps the original |
| `TTS_MP3_TAIL_SILENCE_SEC` | `0.5` | Silence (sec) appended to the end of the output MP3. Keeps sentences from running together when looped (e.g. as an alarm). `0` or less disables it |
| `TTS_LOG_DIR` | `{parrot}/logs` | Server log folder. `tts.log` rotates hourly and logs older than 7 days are deleted. The legacy `{parrot}/tts.log` is used only as a stdout/stderr safety net (for crash output) |

Example:

```bash
cd parrot
FISH_S2_MODEL_PATH=/path/to/fishaudio-s2-pro-8bit-mlx ./tts.sh start
```

---

## Security notes

- **No authentication.** This server has no access control such as API keys or tokens. Anyone who can reach the server can generate speech via `/tts` and list references via `/refs`.
- **Default bind is `0.0.0.0`** — `tts.sh` binds to all network interfaces by default, so other devices on the same network can reach it. For local-only use, run `TTS_HOST=127.0.0.1 ./tts.sh start`. If you need access from another device/container, allow only trusted sources via a firewall and never expose it on a public network.
- **Reference voice rights** — see the note under "refs file rules" above.

---

## Troubleshooting

### `mlx-speech: command not found`

The virtualenv isn't activated, or the package isn't installed.

```bash
cd parrot
source .venv/bin/activate
pip install mlx-speech
```

### `No matching distribution found for mlx-speech`

Usually happens when installing under a Python 3.9 venv. Check the Python version.

```bash
python --version
```

If it isn't `Python 3.13.x`, recreate the venv.

```bash
cd parrot
deactivate 2>/dev/null || true
rm -rf .venv
brew install python@3.13
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install mlx-speech fastapi uvicorn python-multipart huggingface_hub psutil numpy soundfile
```

### `ffmpeg` errors

MP3 conversion requires `ffmpeg`.

```bash
brew install ffmpeg
```

### Model files not found

Check `FISH_S2_MODEL_PATH` or the `{parrot}/fishaudio-s2-pro-8bit-mlx` path.

```bash
ls -la parrot/fishaudio-s2-pro-8bit-mlx
```

### Can't call from another device/container

First confirm the server responds on the host.

```bash
curl http://localhost:8010/health
```

Then check that the server is bound to an externally reachable address (`TTS_HOST`) and that a firewall isn't blocking port `8010`.

---

## License

The code in this repository is released under the [MIT License](LICENSE).

The TTS model (`fishaudio-s2-pro-8bit-mlx`) is not included in this repository and is downloaded separately. The model has its own license — check the [Hugging Face model page](https://huggingface.co/mlx-community/fishaudio-s2-pro-8bit-mlx).
