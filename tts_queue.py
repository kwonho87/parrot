"""TTS 작업을 1개씩 직렬 처리하는 큐. 상태(/status용)를 함께 추적한다."""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("tts")


@dataclass
class Job:
    ref_id: str
    text: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    enqueued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    future: Optional[asyncio.Future] = None


class TTSQueue:
    RECENT_MAX = 20

    def __init__(self, runner: Callable[[Job], Awaitable[bytes]]):
        self._runner = runner
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._current: Optional[Job] = None
        self._recent: list[dict[str, Any]] = []
        self._totals = {"ok": 0, "error": 0}
        self._worker_task: Optional[asyncio.Task] = None
        self.started_at = time.time()

    def start(self):
        # 반드시 실행 중인 이벤트 루프 안에서 호출 (lifespan/테스트 모두 async 컨텍스트)
        self._worker_task = asyncio.get_running_loop().create_task(self._worker())

    async def stop(self):
        """워커를 종료한다.

        대기 중인 job을 모두 처리한 뒤 워커를 종료한다. 백로그가 있으면
        그만큼 블로킹되므로, 서버 shutdown에서는 필요 시 asyncio.wait_for로
        감싸 타임아웃을 둘 것.
        """
        if self._worker_task:
            await self._queue.join()
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    async def submit(self, ref_id: str, text: str) -> bytes:
        job = Job(ref_id=ref_id, text=text)
        job.future = asyncio.get_running_loop().create_future()
        await self._queue.put(job)
        return await job.future

    async def _worker(self):
        while True:
            job = await self._queue.get()
            if job.future.done():  # 대기 중 클라이언트가 취소한 job은 실행하지 않음
                self._queue.task_done()
                continue
            job.started_at = time.time()
            self._current = job
            # 외부 클라이언트 요청도 tts.log에서 추적 가능하도록 기록
            logger.info(f"[TTS] start ref_id={job.ref_id} text_len={len(job.text)} "
                        f"queue_len={self._queue.qsize()}")
            try:
                result = await self._runner(job)
                if not job.future.done():
                    job.future.set_result(result)
                self._record(job, ok=True, error=None)
            except Exception as e:
                if not job.future.done():
                    job.future.set_exception(e)
                self._record(job, ok=False, error=str(e))
            finally:
                self._current = None
                self._queue.task_done()

    def _record(self, job: Job, ok: bool, error: Optional[str]):
        self._totals["ok" if ok else "error"] += 1
        entry = {
            "ref_id": job.ref_id,
            "text_len": len(job.text),
            "ok": ok,
            "error": error,
            "duration_sec": round(time.time() - job.started_at, 2),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._recent.insert(0, entry)
        del self._recent[self.RECENT_MAX:]
        logger.info(f"[TTS] {'done' if ok else 'fail'} ref_id={job.ref_id} "
                    f"duration_sec={entry['duration_sec']}"
                    + (f" error={error}" if error else ""))

    def status(self) -> dict[str, Any]:
        current = None
        if self._current is not None:
            current = {
                "ref_id": self._current.ref_id,
                "text_len": len(self._current.text),
                "elapsed_sec": round(time.time() - self._current.started_at, 1),
            }
        return {
            "uptime_sec": int(time.time() - self.started_at),
            "queue_len": self._queue.qsize(),
            "current_job": current,
            "recent": list(self._recent),
            "totals": dict(self._totals),
        }
