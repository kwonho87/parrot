"""tts_worker를 in-process로 구동하는 테스트.

기존 test_worker.py는 tts_worker.py를 자식 프로세스로 띄워 검증하는데,
그 경우 coverage가 자식 프로세스를 추적하지 못해 0%로 잡힌다. 여기서는
main()과 _reference_for()를 부모 프로세스에서 직접 호출해 커버리지를 확보한다.
"""
import importlib.machinery
import io
import json
import os
import sys
import types

import numpy as np

import tts_worker


class _Result:
    def __init__(self):
        self.waveform = np.zeros(240, dtype="float32")
        self.sample_rate = 24000


def _install_fake_mlx(monkeypatch, load):
    tts_mod = types.SimpleNamespace(load=load)
    mod = types.ModuleType("mlx_speech")
    mod.tts = tts_mod
    mod.__spec__ = importlib.machinery.ModuleSpec("mlx_speech", None)
    monkeypatch.setitem(sys.modules, "mlx_speech", mod)
    monkeypatch.setitem(sys.modules, "mlx_speech.tts", tts_mod)


def _run_main(monkeypatch, tmp_path, load, stdin_lines):
    """main()을 in-process로 실행하고 protocol(stdout 대체)로 나온 JSON 라인들을 돌려준다."""
    _install_fake_mlx(monkeypatch, load)
    proto = tmp_path / "proto.txt"
    fd = os.open(str(proto), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    # main()은 os.dup(1)로 protocol fd를 떼어내고 os.dup2(2,1)로 stdout을 stderr로 돌린다.
    # 테스트에서는 protocol을 임시 파일로 보내고 dup2는 무력화해 pytest 캡처를 건드리지 않는다.
    monkeypatch.setattr(os, "dup", lambda n: fd)
    monkeypatch.setattr(os, "dup2", lambda a, b: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(l + "\n" for l in stdin_lines)))
    monkeypatch.setattr(sys, "argv", ["tts_worker.py", "--model", "/fake"])
    rc = tts_worker.main()
    lines = [json.loads(l) for l in proto.read_text().splitlines() if l.strip()]
    return rc, lines


def test_main_generates_ok(tmp_path, monkeypatch):
    class Model:
        def generate(self, text, ref_audio=None, ref_text=None):
            return _Result()

    out = tmp_path / "o.wav"
    job = json.dumps({"text": "hi", "ref_audio": "/a.wav", "ref_text": "t", "out_wav": str(out)})
    rc, lines = _run_main(monkeypatch, tmp_path, lambda path: Model(), [job])
    assert rc == 0
    assert lines[0] == {"ready": True}
    assert lines[1] == {"ok": True}
    assert out.exists() and out.stat().st_size > 0


def test_main_uses_prepared_reference(tmp_path, monkeypatch):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"x")

    class Prepared:
        pass

    class Model:
        def prepare_reference(self, reference_audio, *, reference_text):
            return Prepared()

        def generate(self, text, reference_audio=None):
            assert isinstance(reference_audio, Prepared)  # 캐시 경로에서 handle 전달
            return _Result()

    job = json.dumps({"text": "hi", "ref_audio": str(ref), "ref_text": "t",
                      "out_wav": str(tmp_path / "o.wav")})
    rc, lines = _run_main(monkeypatch, tmp_path, lambda path: Model(), [job])
    assert lines[1] == {"ok": True}


def test_main_reports_generation_error(tmp_path, monkeypatch):
    class Model:
        def generate(self, text, ref_audio=None, ref_text=None):
            raise ValueError("boom")

    job = json.dumps({"text": "x", "ref_audio": "/a.wav", "ref_text": "t",
                      "out_wav": str(tmp_path / "x.wav")})
    rc, lines = _run_main(monkeypatch, tmp_path, lambda path: Model(), [job])
    assert lines[0] == {"ready": True}
    assert lines[1]["ok"] is False
    assert "boom" in lines[1]["error"]


def test_main_skips_blank_lines(tmp_path, monkeypatch):
    class Model:
        def generate(self, text, ref_audio=None, ref_text=None):
            return _Result()

    job = json.dumps({"text": "hi", "ref_audio": "/a.wav", "ref_text": "t",
                      "out_wav": str(tmp_path / "o.wav")})
    rc, lines = _run_main(monkeypatch, tmp_path, lambda path: Model(), ["", job, ""])
    assert rc == 0
    assert lines == [{"ready": True}, {"ok": True}]  # 빈 줄은 무시


def test_main_load_failure_emits_not_ready(tmp_path, monkeypatch):
    def bad_load(path):
        raise RuntimeError("no model")

    rc, lines = _run_main(monkeypatch, tmp_path, bad_load, [])
    assert rc == 1
    assert lines[0]["ready"] is False
    assert "no model" in lines[0]["error"]


# --- _reference_for 직접 테스트 ---

def test_reference_for_without_prepare_returns_none():
    class M:
        pass

    assert tts_worker._reference_for(M(), "/a.wav", "t", {}, 32) is None


def test_reference_for_caches_and_evicts(tmp_path):
    calls = []

    class M:
        def prepare_reference(self, reference_audio, *, reference_text):
            calls.append(reference_audio)
            return ("prepared", reference_text)

    a = tmp_path / "a.wav"; a.write_bytes(b"x")
    b = tmp_path / "b.wav"; b.write_bytes(b"y")
    cache = {}

    r1 = tts_worker._reference_for(M(), str(a), "t", cache, cache_max=1)
    r2 = tts_worker._reference_for(M(), str(a), "t", cache, cache_max=1)
    assert r1 == r2 and len(calls) == 1               # 같은 ref → 캐시 히트(1회 인코딩)

    tts_worker._reference_for(M(), str(b), "t", cache, cache_max=1)
    assert list(cache.keys()) == [str(b)]             # cache_max=1 → a 축출

    tts_worker._reference_for(M(), str(a), "t", cache, cache_max=1)
    assert len(calls) == 3                            # 축출된 a는 재인코딩


def test_reference_for_missing_file_mtime():
    class M:
        def prepare_reference(self, reference_audio, *, reference_text):
            return "prepared"

    # 존재하지 않는 파일 → getmtime OSError → mtime None 경로
    assert tts_worker._reference_for(M(), "/no/such.wav", "t", {}, 32) == "prepared"
