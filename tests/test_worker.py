# tests/test_worker.py
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _make_fake_mlx(tmp_path: Path):
    pkg = tmp_path / "mlx_speech"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from . import tts\n")
    (pkg / "tts.py").write_text(textwrap.dedent('''
        import numpy as np

        class _Result:
            def __init__(self):
                self.waveform = np.zeros(2400, dtype="float32")
                self.sample_rate = 24000

        class _Model:
            def generate(self, text, ref_audio=None, ref_text=None):
                if ref_audio == "BAD":
                    raise ValueError("bad reference")
                return _Result()

        def load(path):
            return _Model()
    '''))


def _make_fake_mlx_with_prepare(tmp_path: Path, counter: str):
    """prepare_reference를 지원하는 가짜 모델. 호출 시마다 counter 파일에 한 글자 기록."""
    pkg = tmp_path / "mlx_speech"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from . import tts\n")
    (pkg / "tts.py").write_text(textwrap.dedent(f'''
        import numpy as np

        _COUNTER = {counter!r}

        class _Result:
            def __init__(self):
                self.waveform = np.zeros(2400, dtype="float32")
                self.sample_rate = 24000

        class _Prepared:
            def __init__(self, ref_text):
                self.reference_text = ref_text

        class _Model:
            def prepare_reference(self, reference_audio, *, reference_text):
                with open(_COUNTER, "a") as f:
                    f.write("1")
                return _Prepared(reference_text)

            def generate(self, text, reference_audio=None, reference_text=None):
                # 캐시 경로에서는 PreparedReference 핸들이 넘어와야 한다
                assert isinstance(reference_audio, _Prepared)
                return _Result()

        def load(path):
            return _Model()
    '''))


def _spawn_worker(tmp_path: Path):
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{tmp_path}:{REPO}"
    return subprocess.Popen(
        [sys.executable, str(REPO / "tts_worker.py"), "--model", "/fake"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, bufsize=1, env=env,
    )


def _readline(proc, timeout=15):
    import select
    r, _, _ = select.select([proc.stdout], [], [], timeout)
    assert r, "worker produced no output in time"
    return proc.stdout.readline()


def test_worker_ready_generate_ok(tmp_path):
    _make_fake_mlx(tmp_path)
    out_wav = tmp_path / "out.wav"
    proc = _spawn_worker(tmp_path)
    try:
        ready = json.loads(_readline(proc))
        assert ready == {"ready": True}
        proc.stdin.write(json.dumps({
            "text": "안녕", "ref_audio": "/a.wav", "ref_text": "t",
            "out_wav": str(out_wav),
        }) + "\n")
        proc.stdin.flush()
        result = json.loads(_readline(proc))
        assert result == {"ok": True}
        assert out_wav.exists() and out_wav.stat().st_size > 0
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_worker_caches_prepared_reference(tmp_path):
    """같은 ref로 두 번 생성하면 prepare_reference(레퍼런스 인코딩)는 1회만 호출돼야 한다."""
    counter = tmp_path / "prep_calls"
    _make_fake_mlx_with_prepare(tmp_path, str(counter))
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"x")  # mtime 조회가 되도록 실제 파일 생성
    proc = _spawn_worker(tmp_path)
    try:
        assert json.loads(_readline(proc)) == {"ready": True}
        for i in range(2):
            out = tmp_path / f"out{i}.wav"
            proc.stdin.write(json.dumps({
                "text": f"안녕{i}", "ref_audio": str(ref), "ref_text": "t",
                "out_wav": str(out),
            }) + "\n")
            proc.stdin.flush()
            assert json.loads(_readline(proc)) == {"ok": True}
            assert out.exists() and out.stat().st_size > 0
        assert counter.read_text() == "1"  # 두 요청, 인코딩은 1회
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_worker_reencodes_when_reference_file_changes(tmp_path):
    """ref 파일이 바뀌면(mtime 변화) 캐시를 무효화하고 다시 인코딩해야 한다."""
    import time as _t
    counter = tmp_path / "prep_calls"
    _make_fake_mlx_with_prepare(tmp_path, str(counter))
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"x")
    proc = _spawn_worker(tmp_path)
    try:
        assert json.loads(_readline(proc)) == {"ready": True}

        def gen(idx):
            out = tmp_path / f"out{idx}.wav"
            proc.stdin.write(json.dumps({
                "text": "t", "ref_audio": str(ref), "ref_text": "t",
                "out_wav": str(out),
            }) + "\n")
            proc.stdin.flush()
            assert json.loads(_readline(proc)) == {"ok": True}

        gen(0)
        _t.sleep(1.1)          # mtime 해상도 여유
        ref.write_bytes(b"yy")  # 레퍼런스 변경
        gen(1)
        assert counter.read_text() == "11"  # 무효화 후 재인코딩 → 2회
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_worker_reports_generation_error(tmp_path):
    _make_fake_mlx(tmp_path)
    proc = _spawn_worker(tmp_path)
    try:
        assert json.loads(_readline(proc)) == {"ready": True}
        proc.stdin.write(json.dumps({
            "text": "x", "ref_audio": "BAD", "ref_text": "t",
            "out_wav": str(tmp_path / "x.wav"),
        }) + "\n")
        proc.stdin.flush()
        result = json.loads(_readline(proc))
        assert result["ok"] is False
        assert "bad reference" in result["error"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)
