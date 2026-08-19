import importlib
import pytest
from fastapi.testclient import TestClient


class FakeEngine:
    name = "fake"
    is_loaded = True

    def generate(self, text, ref_audio, ref_text, wav_file):
        with open(wav_file, "wb") as f:
            f.write(b"RIFFfake")

    def maybe_unload(self):
        pass


@pytest.fixture
def client(monkeypatch):
    import server
    importlib.reload(server)
    monkeypatch.setattr(server, "get_engine", lambda: FakeEngine())
    monkeypatch.setattr(server, "_wav_to_mp3", lambda wav, mp3: open(mp3, "wb").write(b"MP3FAKE"))
    with TestClient(server.app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_refs_lists_fixture(client):
    r = client.get("/refs")
    assert r.status_code == 200
    ids = [x["ref_id"] for x in r.json()["refs"]]
    assert "testvoice" in ids


def test_tts_returns_mp3(client):
    r = client.post("/tts", json={"ref_id": "testvoice", "text": "안녕하세요"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content == b"MP3FAKE"


def test_tts_missing_ref_404(client):
    r = client.post("/tts", json={"ref_id": "no_such_ref", "text": "x"})
    assert r.status_code == 404


@pytest.mark.parametrize("bad_ref", ["../secret", "../../etc/passwd", "", "foo/../../bar"])
def test_tts_rejects_path_traversal(client, bad_ref):
    """ref_id로 refs 폴더 밖 파일을 참조하려는 시도는 400으로 거부된다."""
    r = client.post("/tts", json={"ref_id": bad_ref, "text": "x"})
    assert r.status_code == 400


def test_status_shape(client):
    client.post("/tts", json={"ref_id": "testvoice", "text": "안녕하세요"})
    r = client.get("/status")
    assert r.status_code == 200
    s = r.json()
    assert s["server"] == "ok"
    assert s["engine"] == "fake"
    assert s["model_resident"] is True
    assert s["queue_len"] == 0
    assert s["current_job"] is None
    assert s["totals"]["ok"] == 1
    assert s["recent"][0]["ref_id"] == "testvoice"
    assert isinstance(s["uptime_sec"], int)
    assert isinstance(s["memory_mb"], int)


def test_get_engine_falls_back_to_cli(monkeypatch):
    import server
    importlib.reload(server)
    monkeypatch.setattr(server, "ENGINE_MODE", "api")
    monkeypatch.setattr(server, "_engine", None)

    def boom(*args, **kwargs):
        raise RuntimeError("mlx_speech is not installed")

    monkeypatch.setattr(server.tts_engine, "ApiEngine", boom)
    engine = server.get_engine()
    assert engine.name == "cli"
    assert server.get_engine() is engine  # 싱글턴 캐시 확인


def test_get_engine_concurrent_single_construction(monkeypatch):
    import threading
    import time
    import server
    importlib.reload(server)
    monkeypatch.setattr(server, "ENGINE_MODE", "cli")
    monkeypatch.setattr(server, "_engine", None)

    constructed = []
    real_cli = server.tts_engine.CliEngine

    class CountingCli(real_cli):
        def __init__(self, *args, **kwargs):
            constructed.append(1)
            time.sleep(0.05)  # 생성 지연을 흉내내 레이스 창을 넓힘
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(server.tts_engine, "CliEngine", CountingCli)
    barrier = threading.Barrier(8)
    results = []

    def call():
        barrier.wait()
        results.append(server.get_engine())

    threads = [threading.Thread(target=call) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(constructed) == 1
    assert all(r is results[0] for r in results)


def test_broken_api_engine_falls_back_to_cli_at_runtime(monkeypatch, tmp_path):
    import server
    importlib.reload(server)

    class BrokenApiEngine:
        name = "api"
        is_loaded = True

        def generate(self, text, ref_audio, ref_text, wav_file):
            raise TypeError("generate() got an unexpected keyword argument 'ref_audio'")

        def maybe_unload(self):
            pass

    cli_calls = []

    class FakeCli:
        name = "cli"
        is_loaded = False

        def __init__(self, *args, **kwargs):
            pass

        def generate(self, text, ref_audio, ref_text, wav_file):
            cli_calls.append(text)
            with open(wav_file, "wb") as f:
                f.write(b"RIFFfake")

        def maybe_unload(self):
            pass

    monkeypatch.setattr(server, "_engine", BrokenApiEngine())
    monkeypatch.setattr(server.tts_engine, "CliEngine", FakeCli)
    monkeypatch.setattr(server, "_wav_to_mp3", lambda wav, mp3: open(mp3, "wb").write(b"MP3FAKE"))

    result = server._generate_sync("testvoice", "폴백 테스트")
    assert result == b"MP3FAKE"
    assert cli_calls == ["폴백 테스트"]
    assert server._engine.name == "cli"  # 이후 요청은 CLI 사용


def test_engine_mode_defaults_to_worker(monkeypatch):
    monkeypatch.delenv("TTS_ENGINE", raising=False)
    import server
    importlib.reload(server)
    try:
        assert server.ENGINE_MODE == "worker"
    finally:
        monkeypatch.setenv("TTS_ENGINE", "cli")
        importlib.reload(server)


def test_wav_to_mp3_uses_voice_options(monkeypatch):
    """음성용 mp3 옵션(모노 + 비트레이트 + 샘플레이트)이 ffmpeg 인자에 반영된다."""
    import subprocess as sp
    import server
    importlib.reload(server)

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return sp.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    server._wav_to_mp3("/in.wav", "/out.mp3")
    cmd = captured["cmd"]
    assert cmd[0] == server.FFMPEG_BIN
    assert "-ac" in cmd and cmd[cmd.index("-ac") + 1] == server.MP3_CHANNELS
    assert "-b:a" in cmd and cmd[cmd.index("-b:a") + 1] == server.MP3_BITRATE
    assert "-ar" in cmd and cmd[cmd.index("-ar") + 1] == server.MP3_SAMPLE_RATE
    assert cmd[-1] == "/out.mp3"
    assert "-qscale:a" not in cmd


def test_wav_to_mp3_appends_tail_silence(monkeypatch):
    """끝에 무음을 붙이는 apad 필터가 ffmpeg 인자에 반영된다."""
    import subprocess as sp
    import server
    monkeypatch.setenv("TTS_MP3_TAIL_SILENCE_SEC", "0.5")
    importlib.reload(server)

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return sp.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    server._wav_to_mp3("/in.wav", "/out.mp3")
    cmd = captured["cmd"]
    assert "-af" in cmd and cmd[cmd.index("-af") + 1] == "apad=pad_dur=0.5"


def test_wav_to_mp3_no_tail_silence_when_zero(monkeypatch):
    """무음 길이가 0이면 apad 필터를 넣지 않는다."""
    import subprocess as sp
    import server
    monkeypatch.setenv("TTS_MP3_TAIL_SILENCE_SEC", "0")
    importlib.reload(server)

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return sp.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    server._wav_to_mp3("/in.wav", "/out.mp3")
    assert "-af" not in captured["cmd"]


def test_tts_archives_output_when_configured(monkeypatch, tmp_path):
    """TTS_OUTPUT_DIR이 설정되면 생성된 mp3 사본이 그 폴더에 보관된다."""
    outdir = tmp_path / "out"
    monkeypatch.setenv("TTS_OUTPUT_DIR", str(outdir))
    import server
    importlib.reload(server)  # 모듈 로드 시 OUTPUT_DIR 읽고 폴더 생성
    monkeypatch.setattr(server, "get_engine", lambda: FakeEngine())
    monkeypatch.setattr(server, "_wav_to_mp3", lambda wav, mp3: open(mp3, "wb").write(b"MP3FAKE"))
    try:
        with TestClient(server.app) as c:
            r = c.post("/tts", json={"ref_id": "testvoice", "text": "보관"})
        assert r.status_code == 200
        saved = list(outdir.glob("*.mp3"))
        assert len(saved) == 1
        assert saved[0].read_bytes() == b"MP3FAKE"
        assert "testvoice" in saved[0].name
    finally:
        monkeypatch.delenv("TTS_OUTPUT_DIR", raising=False)
        importlib.reload(server)  # 다른 테스트에 OUTPUT_DIR 누수 방지


def test_get_engine_worker_falls_back_to_cli(monkeypatch):
    import server
    importlib.reload(server)
    monkeypatch.setattr(server, "ENGINE_MODE", "worker")
    monkeypatch.setattr(server, "_engine", None)

    def boom(*args, **kwargs):
        raise RuntimeError("mlx_speech is not installed")

    monkeypatch.setattr(server.tts_engine, "WorkerEngine", boom)
    engine = server.get_engine()
    assert engine.name == "cli"
