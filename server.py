from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import asyncio
import os
import shutil
import subprocess
import threading
import uuid

import psutil

import tts_engine
from tts_logging import setup_logging
from tts_queue import TTSQueue, Job

logger = setup_logging()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


MODEL_PATH = os.getenv("FISH_S2_MODEL_PATH", f"{BASE_DIR}/fishaudio-s2-pro-8bit-mlx")
# 외부 레퍼런스 폴더(선택). 지정하지 않으면 저장소의 refs/만 사용한다.
REFS_DIR = os.getenv("TTS_REFS_DIR", f"{BASE_DIR}/refs")
# 저장소에 포함된 refs/. ref_id를 여기서 먼저 찾고, 없으면 REFS_DIR로 폴백한다.
LOCAL_REFS_DIR = f"{BASE_DIR}/refs"
TEMP_DIR = os.getenv("TTS_TEMP_DIR", "/tmp/fish_tts_temp")
MLX_SPEECH_BIN = (
    os.getenv("MLX_SPEECH_BIN")
    or shutil.which("mlx-speech")
    or f"{BASE_DIR}/.venv/bin/mlx-speech"
)
MLX_RETRIES = max(1, int(os.getenv("TTS_MLX_RETRIES", "3")))
MLX_RETRY_DELAY_SEC = max(0.0, float(os.getenv("TTS_MLX_RETRY_DELAY_SEC", "5")))
ENGINE_MODE = os.getenv("TTS_ENGINE", "worker")  # "worker" | "api" | "cli"
MODEL_TTL_SEC = float(os.getenv("TTS_MODEL_TTL_SEC", "600"))  # <=0 이면 idle 언로드 안 함(영구 상주)
# 알림음/내레이션용 mp3 인코딩 설정 — 음성엔 모노 + 낮은 비트레이트로 충분하다.
# 인코딩이 빨라지고 응답 바이트가 작아진다. 필요하면 env로 조정/복구.
MP3_BITRATE = os.getenv("TTS_MP3_BITRATE", "96k")
MP3_CHANNELS = os.getenv("TTS_MP3_CHANNELS", "1")
MP3_SAMPLE_RATE = os.getenv("TTS_MP3_SAMPLE_RATE", "24000")  # 빈 문자열이면 원본 샘플레이트 유지
# 알람음처럼 mp3를 반복 재생할 때 문장이 곧바로 이어지지 않도록 끝에 무음을 덧붙인다.
# 0 이하면 추가하지 않음.
MP3_TAIL_SILENCE_SEC = max(0.0, float(os.getenv("TTS_MP3_TAIL_SILENCE_SEC", "0.5")))
# GUI 앱이 띄운 프로세스는 Homebrew PATH를 상속받지 못하므로 절대 경로 폴백 필요
FFMPEG_BIN = (
    os.getenv("FFMPEG_BIN")
    or shutil.which("ffmpeg")
    or next(
        (p for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg") if os.path.isfile(p)),
        "ffmpeg",
    )
)

os.makedirs(TEMP_DIR, exist_ok=True)

_engine = None
_engine_lock = threading.Lock()
queue: TTSQueue | None = None


def get_engine():
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            engine = None
            if ENGINE_MODE == "worker":
                try:
                    engine = tts_engine.WorkerEngine(
                        MODEL_PATH, ttl_sec=MODEL_TTL_SEC,
                        timeout=float(os.getenv("TTS_WORKER_TIMEOUT", "120")),
                        startup_timeout=float(os.getenv("TTS_WORKER_STARTUP_TIMEOUT", "120")),
                        retries=MLX_RETRIES,
                    )
                except Exception as e:
                    logger.info(f"[TTS] worker engine unavailable, falling back to cli: {e}")
            elif ENGINE_MODE == "api":
                try:
                    engine = tts_engine.ApiEngine(MODEL_PATH, ttl_sec=MODEL_TTL_SEC)
                except Exception as e:
                    logger.info(f"[TTS] api engine unavailable, falling back to cli: {e}")
            if engine is None:
                engine = tts_engine.CliEngine(
                    MLX_SPEECH_BIN, MODEL_PATH,
                    retries=MLX_RETRIES, retry_delay=MLX_RETRY_DELAY_SEC,
                )
            _engine = engine
    return _engine


def _wav_to_mp3(wav_file: str, mp3_file: str):
    cmd = [
        FFMPEG_BIN, "-y", "-i", wav_file,
        "-codec:a", "libmp3lame", "-b:a", MP3_BITRATE, "-ac", MP3_CHANNELS,
    ]
    if MP3_SAMPLE_RATE:
        cmd += ["-ar", MP3_SAMPLE_RATE]
    if MP3_TAIL_SILENCE_SEC > 0:
        # apad=pad_dur=N → 원본 뒤에 N초 무음을 덧붙인다.
        cmd += ["-af", f"apad=pad_dur={MP3_TAIL_SILENCE_SEC}"]
    cmd.append(mp3_file)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)


def _fallback_to_cli(reason: Exception):
    """깨진 ApiEngine을 CliEngine으로 교체한다 (mlx_speech API 시그니처 불일치 등)."""
    global _engine
    with _engine_lock:
        logger.warning(f"[TTS] api engine incompatible, switching to cli: {reason}")
        _engine = tts_engine.CliEngine(
            MLX_SPEECH_BIN, MODEL_PATH,
            retries=MLX_RETRIES, retry_delay=MLX_RETRY_DELAY_SEC,
        )
    return _engine


def _generate_sync(ref_id: str, text: str) -> bytes:
    ref_audio, ref_text_path = _resolve_ref_paths(ref_id)
    with open(ref_text_path) as f:
        ref_text = f.read().strip()

    file_id = str(uuid.uuid4())
    wav_file = f"{TEMP_DIR}/{file_id}.wav"
    mp3_file = f"{TEMP_DIR}/{file_id}.mp3"
    try:
        engine = get_engine()
        try:
            engine.generate(text, ref_audio, ref_text, wav_file)
        except (TypeError, AttributeError) as e:
            # mlx_speech Python API가 가정과 다른 경우 — CLI로 전환 후 1회 재시도
            if engine.name != "api":
                raise
            _fallback_to_cli(e).generate(text, ref_audio, ref_text, wav_file)
        _wav_to_mp3(wav_file, mp3_file)
        with open(mp3_file, "rb") as f:
            return f.read()
    finally:
        tts_engine._cleanup_files(wav_file, mp3_file)


async def _run_job(job: Job) -> bytes:
    # 큐가 1개씩만 실행하므로 기본 executor 스레드는 동시에 1개만 점유된다
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _generate_sync, job.ref_id, job.text)


async def _ttl_loop():
    while True:
        await asyncio.sleep(60)
        try:
            get_engine().maybe_unload()  # non-blocking, 동기 호출로 안전
        except Exception as e:
            logger.warning(f"[TTS] ttl check failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global queue
    queue = TTSQueue(_run_job)
    queue.start()
    ttl_task = asyncio.create_task(_ttl_loop())
    yield
    ttl_task.cancel()
    try:
        await ttl_task
    except asyncio.CancelledError:
        pass
    try:
        # 백로그 드레인이 오래 걸리면 10초 후 포기 (uvicorn graceful shutdown 보호)
        await asyncio.wait_for(queue.stop(), timeout=10)
    except asyncio.TimeoutError:
        logger.warning("[TTS] queue stop timed out; shutting down anyway")


app = FastAPI(lifespan=lifespan)


class TTSRequest(BaseModel):
    ref_id: str
    text: str


def _safe_ref_path(base_dir: str, ref_id: str, ext: str) -> str:
    """base_dir 안의 ref 파일 경로를 안전하게 만든다(path traversal 방지).

    ref_id가 요청 본문에서 오므로 `..`나 절대 경로, 심볼릭 링크로 base_dir를
    벗어나면 거부한다. 하위 폴더 참조(예: `group/name`)는 허용한다.
    """
    if not ref_id or "\x00" in ref_id:
        raise HTTPException(status_code=400, detail="유효하지 않은 ref_id 입니다.")
    base = os.path.realpath(base_dir)
    candidate = os.path.realpath(os.path.join(base, ref_id + ext))
    if candidate != base and not candidate.startswith(base + os.sep):
        raise HTTPException(status_code=400, detail="유효하지 않은 ref_id 입니다.")
    return candidate


def _resolve_ref_paths(ref_id: str) -> tuple[str, str]:
    # 저장소 refs/를 먼저 탐색하고, 없으면 외부 REFS_DIR로 폴백한다.
    local_audio = _safe_ref_path(LOCAL_REFS_DIR, ref_id, ".wav")
    local_text = _safe_ref_path(LOCAL_REFS_DIR, ref_id, ".txt")
    if os.path.exists(local_audio) and os.path.exists(local_text):
        return local_audio, local_text
    return _safe_ref_path(REFS_DIR, ref_id, ".wav"), _safe_ref_path(REFS_DIR, ref_id, ".txt")


@app.post("/tts")
async def generate_tts(req: TTSRequest):
    ref_audio, ref_text_path = _resolve_ref_paths(req.ref_id)
    if not os.path.exists(ref_audio):
        raise HTTPException(status_code=404, detail=f"refs/{req.ref_id}.wav 파일이 없습니다.")
    if not os.path.exists(ref_text_path):
        raise HTTPException(status_code=404, detail=f"refs/{req.ref_id}.txt 파일이 없습니다.")
    try:
        mp3_bytes = await queue.submit(req.ref_id, req.text)
    except Exception as e:
        logger.error(f"[TTS] request failed ref_id={req.ref_id} text_len={len(req.text)} error={e}")
        raise HTTPException(status_code=500, detail=str(e))
    return Response(content=mp3_bytes, media_type="audio/mpeg")


@app.get("/status")
async def status():
    s = queue.status()
    proc = psutil.Process()
    rss = proc.memory_info().rss
    for child in proc.children(recursive=True):
        try:
            rss += child.memory_info().rss
        except psutil.NoSuchProcess:
            pass
    engine = get_engine()
    s.update({
        "server": "ok",
        "engine": engine.name,
        "model_resident": engine.is_loaded,
        "memory_mb": rss // (1024 * 1024),
    })
    return s


@app.get("/refs")
async def list_refs():
    # 저장소 refs/와 외부 REFS_DIR를 병합 나열한다.
    # _resolve_ref_paths가 로컬을 우선 탐색하므로 목록도 같은 기준으로 로컬 우선 dedup.
    refs: dict[str, dict] = {}
    for d in (LOCAL_REFS_DIR, REFS_DIR):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".wav"):
                ref_id = f[:-4]
                if ref_id not in refs:
                    refs[ref_id] = {
                        "ref_id": ref_id,
                        "has_txt": os.path.exists(f"{d}/{ref_id}.txt"),
                    }
    return {"refs": sorted(refs.values(), key=lambda r: r["ref_id"])}


@app.get("/health")
async def health():
    return {"status": "ok"}
