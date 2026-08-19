"""공용 로깅 설정: 1시간 롤링 + 7일 보관.

logs/tts.log에 기록하고 매시 정각 기준으로 tts.log.YYYY-MM-DD_HH 로 회전한다.
7일(168시간)보다 오래된 회전 파일은 자동 삭제된다.
프로세스 stdout/stderr(tts.log)은 로깅 시스템 밖 출력(크래시 등)의 안전망으로 남는다.
"""
import logging
import os
import time
from logging.handlers import TimedRotatingFileHandler

RETENTION_DAYS = 7

_configured = False


class _AccessLogFilter(logging.Filter):
    """2초 폴링(/status·/health)과 /refs 조회는 로그에서 제외해 노이즈를 줄인다."""

    _QUIET = ('GET /status ', 'GET /health ', 'GET /refs ')

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(q in msg for q in self._QUIET)


def _cleanup_old_logs(log_dir: str):
    """롤링과 무관하게 7일 지난 로그 파일을 시작 시점에 정리한다."""
    cutoff = time.time() - RETENTION_DAYS * 86400
    try:
        for name in os.listdir(log_dir):
            if not name.startswith("tts.log."):
                continue
            path = os.path.join(log_dir, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


def setup_logging() -> logging.Logger:
    """앱 로거("tts")와 uvicorn 로거를 롤링 파일 핸들러로 구성한다. 멱등."""
    global _configured
    logger = logging.getLogger("tts")
    if _configured:
        return logger

    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.getenv("TTS_LOG_DIR", os.path.join(base_dir, "logs"))
    os.makedirs(log_dir, exist_ok=True)
    _cleanup_old_logs(log_dir)

    handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "tts.log"),
        when="H", interval=1, backupCount=RETENTION_DAYS * 24, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    logger.setLevel(logging.INFO)
    logger.handlers = [handler]
    logger.propagate = False

    # uvicorn 로그도 같은 롤링 파일로 모으고 stderr 중복 출력을 막는다
    access_filter = _AccessLogFilter()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        ulog = logging.getLogger(name)
        ulog.handlers = [handler]
        ulog.propagate = False
        if name == "uvicorn.access":
            ulog.filters = [access_filter]

    _configured = True
    return logger
