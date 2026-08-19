"""TTS 생성 엔진. CliEngine은 요청마다 mlx-speech CLI를 실행하고,
ApiEngine(Task 4)은 mlx_speech Python API로 모델을 상주시킨다."""
import gc
import importlib.util
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time


def _cleanup_files(*paths: str):
    for path in paths:
        if os.path.exists(path):
            os.remove(path)


logger = logging.getLogger("tts")


def _log(msg: str):
    logger.info(msg)


def _save_wav(result, wav_file: str):
    import numpy as np
    import soundfile as sf
    sf.write(wav_file, np.array(result.waveform), result.sample_rate)


def reference_kwargs(model, ref_audio: str, ref_text: str) -> dict:
    """model.generate의 실제 파라미터명에 맞춰 레퍼런스 kwargs를 구성한다.

    라이브러리에 따라 ref_audio / reference_audio 등 이름이 다르고, 잘못된
    이름을 **kwargs로 조용히 삼키면 레퍼런스가 무시되어 엉뚱한 목소리가
    나온다. 이름을 확정할 수 없으면 TypeError를 던진다.
    """
    import inspect
    try:
        params = inspect.signature(model.generate).parameters
    except (TypeError, ValueError):
        params = {}
    for audio_key, text_key in (
        ("ref_audio", "ref_text"),
        ("reference_audio", "reference_text"),
        ("speaker_audio", "speaker_text"),
    ):
        if audio_key in params and text_key in params:
            return {audio_key: ref_audio, text_key: ref_text}
    raise TypeError(
        f"cannot determine reference kwargs for model.generate; params={list(params)}"
    )


class CliEngine:
    name = "cli"
    is_loaded = False  # CLI 방식은 모델 상주 없음

    def __init__(self, bin_path: str, model_path: str, retries: int = 3, retry_delay: float = 5.0):
        self.bin_path = bin_path
        self.model_path = model_path
        self.retries = max(1, retries)
        self.retry_delay = max(0.0, retry_delay)

    def generate(self, text: str, ref_audio: str, ref_text: str, wav_file: str):
        cmd = [
            self.bin_path, "tts",
            "--model", self.model_path,
            "--text", text,
            "--reference-audio", ref_audio,
            "--reference-text", ref_text,
            "-o", wav_file,
        ]
        last_error = ""
        for attempt in range(1, self.retries + 1):
            _cleanup_files(wav_file)
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
            except FileNotFoundError as e:
                raise RuntimeError(f"mlx-speech executable not found: {cmd[0]}") from e
            if result.returncode == 0:
                return
            last_error = (
                result.stderr.strip()
                or result.stdout.strip()
                or f"mlx-speech exited with code {result.returncode}"
            )
            _log(f"[TTS] mlx-speech failed attempt={attempt}/{self.retries} exit={result.returncode}")
            for line in last_error.splitlines():
                _log(line)
            if attempt < self.retries:
                time.sleep(self.retry_delay)
        raise RuntimeError(f"mlx-speech failed after {self.retries} attempts: {last_error}")

    def maybe_unload(self):
        pass  # CLI 방식은 상주 모델 없음


class ApiEngine:
    name = "api"

    def __init__(self, model_path: str, ttl_sec: float = 600.0):
        if importlib.util.find_spec("mlx_speech") is None:
            raise RuntimeError("mlx_speech is not installed")
        self.model_path = model_path
        self.ttl_sec = ttl_sec
        self._model = None
        self._last_used = 0.0
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def generate(self, text: str, ref_audio: str, ref_text: str, wav_file: str):
        with self._lock:
            model = self._ensure_loaded()
            kwargs = reference_kwargs(model, ref_audio, ref_text)
            result = model.generate(text, **kwargs)
            _save_wav(result, wav_file)
            self._last_used = time.time()  # TTL은 "마지막 사용 완료" 기준 (로드 시점 아님)

    def _ensure_loaded(self):
        if self._model is None:
            import mlx_speech
            _log(f"[TTS] loading model into memory: {self.model_path}")
            t0 = time.time()
            self._model = mlx_speech.tts.load(self.model_path)
            _log(f"[TTS] model loaded in {time.time() - t0:.1f}s")
        return self._model

    def maybe_unload(self):
        if self.ttl_sec <= 0:
            return  # 영구 상주 (idle 언로드 안 함)
        # 생성 중(_lock 점유)에는 스킵, TTL 경과 시에만 언로드
        if not self._lock.acquire(blocking=False):
            return
        try:
            if self._model is not None and time.time() - self._last_used > self.ttl_sec:
                _log("[TTS] unloading idle model")
                self._model = None
                gc.collect()
                try:
                    import mlx.core as mx
                    mx.clear_cache()
                except Exception as e:
                    _log(f"[TTS] mx.clear_cache skipped: {e}")
        finally:
            self._lock.release()


class _WorkerCrash(RuntimeError):
    """워커 프로세스 크래시/타임아웃/파이프 오류 — 재기동+재시도 대상."""


class WorkerEngine:
    name = "worker"

    def __init__(self, model_path: str, worker_cmd: list | None = None,
                 ttl_sec: float = 600.0, timeout: float = 120.0,
                 startup_timeout: float = 120.0, retries: int = 3):
        if importlib.util.find_spec("mlx_speech") is None:
            raise RuntimeError("mlx_speech is not installed")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.model_path = model_path
        self.worker_cmd = worker_cmd or [
            sys.executable, os.path.join(base_dir, "tts_worker.py"),
            "--model", model_path,
        ]
        self.ttl_sec = ttl_sec
        self.timeout = timeout
        self.startup_timeout = startup_timeout
        self.retries = max(1, retries)
        self._proc = None
        self._reader = None
        self._out_q: queue.Queue = queue.Queue()
        self._ready = False
        self._last_used = 0.0
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._ready and self._proc is not None and self._proc.poll() is None

    def generate(self, text: str, ref_audio: str, ref_text: str, wav_file: str):
        with self._lock:
            last_error = ""
            for attempt in range(1, self.retries + 1):
                try:
                    self._ensure_worker()
                    self._send_job(text, ref_audio, ref_text, wav_file)
                    result = self._read_result(self.timeout)
                    if result.get("ok"):
                        self._last_used = time.time()
                        return
                    # 워커는 살아있고 생성만 실패(결정론적) → 재시도 이득 없음, 즉시 실패
                    raise RuntimeError(
                        f"worker generation failed: {result.get('error', 'unknown worker error')}"
                    )
                except _WorkerCrash as e:  # 파이프 깨짐/타임아웃/크래시 → 재기동 후 재시도
                    last_error = str(e)
                    self._kill_worker()
                    _log(f"[TTS] worker attempt={attempt}/{self.retries} crashed: {last_error}")
            raise RuntimeError(f"worker failed after {self.retries} attempts: {last_error}")

    def maybe_unload(self):
        if self.ttl_sec <= 0:
            return  # 영구 상주 (idle 언로드 안 함)
        if not self._lock.acquire(blocking=False):
            return
        try:
            if self.is_loaded and time.time() - self._last_used > self.ttl_sec:
                _log("[TTS] unloading idle model worker")
                self._kill_worker()
        finally:
            self._lock.release()

    # --- 내부 ---
    def _ensure_worker(self):
        if self.is_loaded:
            return
        self._kill_worker()
        self._spawn_worker()

    def _spawn_worker(self):
        _log(f"[TTS] starting model worker: {self.worker_cmd}")
        self._proc = subprocess.Popen(
            self.worker_cmd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self._out_q = queue.Queue()
        self._reader = threading.Thread(
            target=self._reader_loop, args=(self._proc.stdout, self._out_q), daemon=True,
        )
        self._reader.start()
        msg = self._read_result(self.startup_timeout)
        if not msg.get("ready"):
            raise RuntimeError(f"worker failed to load model: {msg.get('error')}")
        self._ready = True
        self._last_used = time.time()

    @staticmethod
    def _reader_loop(stream, q: queue.Queue):
        try:
            for line in stream:
                q.put(line)
        finally:
            q.put(None)  # EOF 센티널 (워커 종료/크래시)

    def _send_job(self, text, ref_audio, ref_text, wav_file):
        job = json.dumps({
            "text": text, "ref_audio": ref_audio,
            "ref_text": ref_text, "out_wav": wav_file,
        })
        try:
            self._proc.stdin.write(job + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise _WorkerCrash(f"worker stdin write failed: {e}")

    def _read_result(self, timeout: float) -> dict:
        try:
            line = self._out_q.get(timeout=timeout)
        except queue.Empty:
            raise _WorkerCrash("worker timed out")
        if line is None:
            raise _WorkerCrash("worker exited unexpectedly")
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            raise _WorkerCrash(f"worker sent invalid line: {e}")

    def _kill_worker(self):
        self._ready = False
        p = self._proc
        self._proc = None
        if p is None:
            return
        try:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        except Exception:
            pass
