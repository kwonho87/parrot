import asyncio
import pytest
from tts_queue import TTSQueue


@pytest.mark.asyncio
async def test_jobs_run_serially():
    running = 0
    max_concurrent = 0

    async def runner(job):
        nonlocal running, max_concurrent
        running += 1
        max_concurrent = max(max_concurrent, running)
        await asyncio.sleep(0.02)
        running -= 1
        return f"done-{job.ref_id}".encode()

    q = TTSQueue(runner)
    q.start()
    results = await asyncio.gather(
        q.submit("a", "text1"), q.submit("b", "text2"), q.submit("c", "text3")
    )
    await q.stop()
    assert results == [b"done-a", b"done-b", b"done-c"]
    assert max_concurrent == 1


@pytest.mark.asyncio
async def test_status_reports_queue_and_history():
    gate = asyncio.Event()

    async def runner(job):
        await gate.wait()
        if job.ref_id == "bad":
            raise RuntimeError("boom")
        return b"ok"

    q = TTSQueue(runner)
    q.start()
    t1 = asyncio.create_task(q.submit("good", "hello"))
    t2 = asyncio.create_task(q.submit("bad", "world"))
    await asyncio.sleep(0.01)  # 워커가 첫 job을 집을 시간

    s = q.status()
    assert s["queue_len"] == 1
    assert s["current_job"]["ref_id"] == "good"
    assert s["current_job"]["text_len"] == 5

    gate.set()
    assert await t1 == b"ok"
    with pytest.raises(RuntimeError):
        await t2
    await q.stop()

    s = q.status()
    assert s["queue_len"] == 0
    assert s["current_job"] is None
    assert s["totals"] == {"ok": 1, "error": 1}
    assert len(s["recent"]) == 2
    assert s["recent"][0]["ref_id"] == "bad" and s["recent"][0]["ok"] is False
    assert s["recent"][1]["ref_id"] == "good" and s["recent"][1]["ok"] is True


@pytest.mark.asyncio
async def test_cancelled_job_is_skipped():
    ran = []
    gate = asyncio.Event()

    async def runner(job):
        ran.append(job.ref_id)
        await gate.wait()
        return b"ok"

    q = TTSQueue(runner)
    q.start()
    t1 = asyncio.create_task(q.submit("first", "x"))
    t2 = asyncio.create_task(q.submit("second", "y"))
    await asyncio.sleep(0.01)  # 워커가 first를 집을 시간
    t2.cancel()                # 대기 중인 second 취소
    await asyncio.sleep(0)
    gate.set()
    assert await t1 == b"ok"
    await q.stop()
    assert ran == ["first"]   # second는 실행되지 않아야 함


@pytest.mark.asyncio
async def test_recent_history_capped_at_20():
    async def runner(job):
        return b"ok"

    q = TTSQueue(runner)
    q.start()
    for i in range(25):
        await q.submit(f"ref{i}", "x")
    await q.stop()
    s = q.status()
    assert len(s["recent"]) == 20
    assert s["recent"][0]["ref_id"] == "ref24"
