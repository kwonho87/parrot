import importlib
import logging
import os
import time
from logging.handlers import TimedRotatingFileHandler

import tts_logging


def test_rolling_handler_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_LOG_DIR", str(tmp_path))
    importlib.reload(tts_logging)  # _configured 리셋
    logger = tts_logging.setup_logging()

    handler = logger.handlers[0]
    assert isinstance(handler, TimedRotatingFileHandler)
    assert handler.when == "H"
    assert handler.backupCount == 7 * 24

    logger.info("hello rolling")
    handler.flush()
    assert "hello rolling" in (tmp_path / "tts.log").read_text()

    # uvicorn access 로거에 /status 노이즈 필터가 걸려 있는지
    access = logging.getLogger("uvicorn.access")
    assert access.handlers == [handler]
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0,
        '127.0.0.1:1 - "GET /status HTTP/1.1" 200 OK', None, None,
    )
    assert not access.filters[0].filter(record)
    record_tts = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0,
        '127.0.0.1:1 - "POST /tts HTTP/1.1" 200 OK', None, None,
    )
    assert access.filters[0].filter(record_tts)


def test_old_logs_cleaned_on_setup(tmp_path, monkeypatch):
    old = tmp_path / "tts.log.2020-01-01_00"
    old.write_text("ancient")
    os.utime(old, (time.time() - 8 * 86400, time.time() - 8 * 86400))
    recent = tmp_path / "tts.log.recent"
    recent.write_text("recent")

    monkeypatch.setenv("TTS_LOG_DIR", str(tmp_path))
    importlib.reload(tts_logging)
    tts_logging.setup_logging()

    assert not old.exists()
    assert recent.exists()
