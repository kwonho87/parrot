import importlib.machinery
import subprocess
import sys
import textwrap
import types

import pytest
import tts_engine
from tts_engine import CliEngine


def _completed(returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


def test_cli_engine_success(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    engine = CliEngine(bin_path="/fake/mlx-speech", model_path="/fake/model", retries=3, retry_delay=0)
    engine.generate("안녕", "/refs/a.wav", "레퍼런스", str(tmp_path / "out.wav"))
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == "/fake/mlx-speech"
    assert "--text" in cmd and "안녕" in cmd
    assert "--reference-audio" in cmd and "/refs/a.wav" in cmd


def test_cli_engine_retries_then_fails(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(1, stderr="metal error")

    monkeypatch.setattr(subprocess, "run", fake_run)
    engine = CliEngine(bin_path="/fake/mlx-speech", model_path="/fake/model", retries=3, retry_delay=0)
    with pytest.raises(RuntimeError, match="metal error"):
        engine.generate("안녕", "/refs/a.wav", "레퍼런스", str(tmp_path / "out.wav"))
    assert len(calls) == 3


def test_cli_engine_is_never_resident():
    engine = CliEngine(bin_path="/fake/mlx-speech", model_path="/fake/model")
    assert engine.is_loaded is False


class FakeResult:
    waveform = [0.0, 0.1]
    sample_rate = 24000


class FakeModel:
    """ref_audio/ref_text 파라미터명을 가진 모델 (명시적 시그니처)."""

    def __init__(self):
        self.calls = []

    def generate(self, text, ref_audio=None, ref_text=None):
        self.calls.append((text, {"ref_audio": ref_audio, "ref_text": ref_text}))
        return FakeResult()


@pytest.fixture
def fake_mlx(monkeypatch):
    fake_model = FakeModel()
    tts_mod = types.SimpleNamespace(load=lambda path: fake_model)
    mod = types.ModuleType("mlx_speech")
    mod.tts = tts_mod
    mod.__spec__ = importlib.machinery.ModuleSpec("mlx_speech", None)
    monkeypatch.setitem(sys.modules, "mlx_speech", mod)
    monkeypatch.setitem(sys.modules, "mlx_speech.tts", tts_mod)
    saved = []
    monkeypatch.setattr(
        tts_engine, "_save_wav",
        lambda result, wav_file: saved.append(wav_file)
    )
    return fake_model, saved


def test_api_engine_loads_once_and_reuses(fake_mlx, tmp_path):
    fake_model, saved = fake_mlx
    engine = tts_engine.ApiEngine(model_path="/fake/model", ttl_sec=600)
    engine.generate("하나", "/refs/a.wav", "레퍼런스", str(tmp_path / "1.wav"))
    engine.generate("둘", "/refs/a.wav", "레퍼런스", str(tmp_path / "2.wav"))
    assert engine.is_loaded is True
    assert len(fake_model.calls) == 2
    assert len(saved) == 2
    text, kwargs = fake_model.calls[0]
    assert text == "하나"
    assert kwargs["ref_audio"] == "/refs/a.wav"
    assert kwargs["ref_text"] == "레퍼런스"


def test_api_engine_maps_reference_audio_param_names(fake_mlx, tmp_path):
    """라이브러리가 reference_audio/reference_text 이름을 쓰는 경우 자동 매핑."""
    fake_model, _ = fake_mlx

    calls = []

    def generate(text, reference_audio=None, reference_text=None):
        calls.append((text, reference_audio, reference_text))
        return FakeResult()

    fake_model.generate = generate
    engine = tts_engine.ApiEngine(model_path="/fake/model", ttl_sec=600)
    engine.generate("하나", "/refs/a.wav", "레퍼런스", str(tmp_path / "1.wav"))
    assert calls == [("하나", "/refs/a.wav", "레퍼런스")]


def test_api_engine_rejects_unknown_signature(fake_mlx, tmp_path):
    """파라미터명을 확정할 수 없으면(**kwargs만 있는 경우) TypeError → CLI 폴백 유도."""
    fake_model, _ = fake_mlx

    def generate(text, **kwargs):
        return FakeResult()

    fake_model.generate = generate
    engine = tts_engine.ApiEngine(model_path="/fake/model", ttl_sec=600)
    with pytest.raises(TypeError, match="reference kwargs"):
        engine.generate("하나", "/refs/a.wav", "레퍼런스", str(tmp_path / "1.wav"))


def test_api_engine_ttl_unload(fake_mlx, tmp_path):
    fake_model, _ = fake_mlx
    engine = tts_engine.ApiEngine(model_path="/fake/model", ttl_sec=600)
    engine.generate("하나", "/refs/a.wav", "레퍼런스", str(tmp_path / "1.wav"))
    assert engine.is_loaded is True

    engine.maybe_unload()  # TTL 안 지남 → 유지
    assert engine.is_loaded is True

    engine._last_used -= 601  # TTL 경과 시뮬레이션
    engine.maybe_unload()
    assert engine.is_loaded is False


def test_api_engine_ttl_zero_never_unloads(fake_mlx, tmp_path):
    """ttl_sec<=0이면 idle이어도 언로드하지 않는다 (영구 상주)."""
    engine = tts_engine.ApiEngine(model_path="/fake/model", ttl_sec=0)
    engine.generate("하나", "/refs/a.wav", "레퍼런스", str(tmp_path / "1.wav"))
    assert engine.is_loaded is True
    engine._last_used -= 10_000  # 한참 idle 시뮬레이션
    engine.maybe_unload()
    assert engine.is_loaded is True


def test_reference_kwargs_module_function_maps_names():
    class M1:
        def generate(self, text, ref_audio=None, ref_text=None): ...
    class M2:
        def generate(self, text, reference_audio=None, reference_text=None): ...
    assert tts_engine.reference_kwargs(M1(), "/a.wav", "t") == {"ref_audio": "/a.wav", "ref_text": "t"}
    assert tts_engine.reference_kwargs(M2(), "/a.wav", "t") == {"reference_audio": "/a.wav", "reference_text": "t"}


def test_reference_kwargs_rejects_unknown():
    class M:
        def generate(self, text, **kwargs): ...
    with pytest.raises(TypeError, match="reference kwargs"):
        tts_engine.reference_kwargs(M(), "/a.wav", "t")


# ready 후 job마다 out_wav를 쓰고 ok를 반환하는 정상 스텁
_STUB_OK = textwrap.dedent('''
    import sys, json
    sys.stdout.write(json.dumps({"ready": True}) + "\\n"); sys.stdout.flush()
    for line in sys.stdin:
        job = json.loads(line)
        open(job["out_wav"], "wb").write(b"RIFFfake")
        sys.stdout.write(json.dumps({"ok": True}) + "\\n"); sys.stdout.flush()
''')

# 첫 프로세스는 job 받고 크래시, 두 번째 프로세스부터 성공 (STUB_COUNTER 파일로 상태 유지)
_STUB_FLAKY = textwrap.dedent('''
    import sys, json, os
    c = os.environ["STUB_COUNTER"]
    n = int(open(c).read() or "0") if os.path.exists(c) else 0
    open(c, "w").write(str(n + 1))
    sys.stdout.write(json.dumps({"ready": True}) + "\\n"); sys.stdout.flush()
    line = sys.stdin.readline()
    if n == 0:
        sys.exit(1)
    job = json.loads(line)
    open(job["out_wav"], "wb").write(b"RIFF")
    sys.stdout.write(json.dumps({"ok": True}) + "\\n"); sys.stdout.flush()
''')

# ready 후 job에 응답하지 않고 대기 → 타임아웃 유발
_STUB_HANG = textwrap.dedent('''
    import sys, json, time
    sys.stdout.write(json.dumps({"ready": True}) + "\\n"); sys.stdout.flush()
    sys.stdin.readline()
    time.sleep(30)
''')


def test_worker_engine_generates(fake_mlx, tmp_path):
    engine = tts_engine.WorkerEngine(
        model_path="/fake", worker_cmd=[sys.executable, "-c", _STUB_OK],
    )
    out = tmp_path / "1.wav"
    engine.generate("안녕", "/a.wav", "레퍼런스", str(out))
    assert engine.is_loaded is True
    assert out.read_bytes() == b"RIFFfake"
    engine.maybe_unload()  # ttl 안 지남 → 유지
    assert engine.is_loaded is True
    engine._kill_worker()


def test_worker_engine_respawns_after_crash(fake_mlx, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_COUNTER", str(tmp_path / "counter"))
    engine = tts_engine.WorkerEngine(
        model_path="/fake", worker_cmd=[sys.executable, "-c", _STUB_FLAKY], retries=3,
    )
    out = tmp_path / "1.wav"
    engine.generate("안녕", "/a.wav", "t", str(out))  # 1회 크래시 후 재기동해 성공
    assert out.read_bytes() == b"RIFF"
    engine._kill_worker()


def test_worker_engine_gives_up_after_retries(fake_mlx, tmp_path, monkeypatch):
    always_crash = textwrap.dedent('''
        import sys, json
        sys.stdout.write(json.dumps({"ready": True}) + "\\n"); sys.stdout.flush()
        sys.stdin.readline(); sys.exit(1)
    ''')
    engine = tts_engine.WorkerEngine(
        model_path="/fake", worker_cmd=[sys.executable, "-c", always_crash], retries=2,
    )
    with pytest.raises(RuntimeError, match="worker failed after 2 attempts"):
        engine.generate("x", "/a.wav", "t", str(tmp_path / "x.wav"))
    engine._kill_worker()


def test_worker_engine_times_out(fake_mlx, tmp_path):
    engine = tts_engine.WorkerEngine(
        model_path="/fake", worker_cmd=[sys.executable, "-c", _STUB_HANG],
        timeout=0.5, retries=1,
    )
    with pytest.raises(RuntimeError, match="worker failed after 1 attempts"):
        engine.generate("x", "/a.wav", "t", str(tmp_path / "x.wav"))
    engine._kill_worker()


def test_worker_engine_fails_fast_on_generation_error(fake_mlx, tmp_path, monkeypatch):
    """워커가 살아있는데 생성만 실패(ok:false)하면 결정론적 실패이므로 재시도 없이 즉시 실패해야 한다."""
    counter = tmp_path / "okfalse_counter"
    monkeypatch.setenv("OKFALSE_COUNTER", str(counter))
    stub = textwrap.dedent('''
        import sys, json, os
        c = os.environ["OKFALSE_COUNTER"]
        sys.stdout.write(json.dumps({"ready": True}) + "\\n"); sys.stdout.flush()
        for line in sys.stdin:
            n = int(open(c).read() or "0") if os.path.exists(c) else 0
            open(c, "w").write(str(n + 1))
            sys.stdout.write(json.dumps({"ok": False, "error": "bad ref"}) + "\\n"); sys.stdout.flush()
    ''')
    engine = tts_engine.WorkerEngine(
        model_path="/fake", worker_cmd=[sys.executable, "-c", stub], retries=3,
    )
    try:
        with pytest.raises(RuntimeError, match="worker generation failed: bad ref"):
            engine.generate("x", "/a.wav", "t", str(tmp_path / "x.wav"))
        assert int(counter.read_text()) == 1  # 재시도 없이 1회만 호출됨
    finally:
        engine._kill_worker()


def test_worker_engine_idle_unload(fake_mlx, tmp_path):
    engine = tts_engine.WorkerEngine(
        model_path="/fake", worker_cmd=[sys.executable, "-c", _STUB_OK], ttl_sec=600,
    )
    engine.generate("안녕", "/a.wav", "t", str(tmp_path / "1.wav"))
    assert engine.is_loaded is True
    engine._last_used -= 601  # TTL 경과 시뮬레이션
    engine.maybe_unload()
    assert engine.is_loaded is False


def test_worker_engine_ttl_zero_never_unloads(fake_mlx, tmp_path):
    """ttl_sec<=0이면 idle이어도 워커를 죽이지 않는다 (영구 상주)."""
    engine = tts_engine.WorkerEngine(
        model_path="/fake", worker_cmd=[sys.executable, "-c", _STUB_OK], ttl_sec=0,
    )
    try:
        engine.generate("안녕", "/a.wav", "t", str(tmp_path / "1.wav"))
        assert engine.is_loaded is True
        engine._last_used -= 10_000  # 한참 idle 시뮬레이션
        engine.maybe_unload()
        assert engine.is_loaded is True
    finally:
        engine._kill_worker()
