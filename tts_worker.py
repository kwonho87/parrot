"""모델을 상주시키는 격리 워커 프로세스.

stdin에서 JSON job 라인을 읽어 mlx_speech 모델로 생성하고 out_wav에 저장한 뒤
stdout에 결과 JSON 라인을 쓴다. MLX GPU 크래시가 나면 이 프로세스만 죽고 부모
서버는 파이프 EOF로 감지해 재기동한다.

프로토콜(모두 한 줄 JSON):
  워커 → 부모:  {"ready": true}  또는 {"ready": false, "error": "..."}
  부모 → 워커:  {"text":..., "ref_audio":..., "ref_text":..., "out_wav":...}
  워커 → 부모:  {"ok": true}  또는 {"ok": false, "error": "..."}
"""
import argparse
import json
import os
import sys


def _reference_for(model, ref_audio, ref_text, cache, cache_max):
    """레퍼런스 인코딩을 ref별 1회만 수행하고 재사용한다.

    fish adapter처럼 `prepare_reference`를 지원하는 모델에서만 레퍼런스
    오디오를 미리 인코딩(load_audio + codec.encode)해 `PreparedReference`를
    캐시하고, 이후 같은 ref는 재인코딩 없이 재사용한다. 미지원 모델은 None을
    반환해 호출부가 기존(요청마다 인코딩) 경로로 폴백한다.

    - 파일이 바뀌면(mtime 변화) 캐시를 무효화한다.
    - 캐시 항목 수는 cache_max로 제한(가장 오래된 것부터 제거)해 메모리를 묶는다.
    """
    if not hasattr(model, "prepare_reference"):
        return None
    try:
        mtime = os.path.getmtime(ref_audio)
    except OSError:
        mtime = None
    cached = cache.get(ref_audio)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    prepared = model.prepare_reference(ref_audio, reference_text=ref_text)
    cache[ref_audio] = (mtime, prepared)
    while len(cache) > cache_max:
        cache.pop(next(iter(cache)))  # 삽입 순서상 가장 오래된 항목 제거
    return prepared


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    args = parser.parse_args()

    # 모델이 stdout(fd1)에 찍는 로그가 프로토콜을 오염시키지 않도록,
    # 원래 stdout를 프로토콜 전용으로 떼어내고 fd1은 stderr로 돌린다.
    protocol = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)

    def emit(obj):
        protocol.write(json.dumps(obj) + "\n")
        protocol.flush()

    try:
        import mlx_speech
        import tts_engine  # reference_kwargs, _save_wav 재사용
        model = mlx_speech.tts.load(args.model)
    except Exception as e:  # noqa: BLE001
        emit({"ready": False, "error": str(e)})
        return 1
    emit({"ready": True})

    prepared_cache: dict = {}
    cache_max = max(1, int(os.getenv("TTS_REF_CACHE_MAX", "32")))

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
            handle = _reference_for(
                model, job["ref_audio"], job["ref_text"], prepared_cache, cache_max
            )
            if handle is not None:
                # 캐시된 레퍼런스 재사용 → 재인코딩 없음
                result = model.generate(job["text"], reference_audio=handle)
            else:
                # prepare_reference 미지원 모델: 기존 경로(요청마다 인코딩)
                kwargs = tts_engine.reference_kwargs(model, job["ref_audio"], job["ref_text"])
                result = model.generate(job["text"], **kwargs)
            tts_engine._save_wav(result, job["out_wav"])
            emit({"ok": True})
        except Exception as e:  # noqa: BLE001
            emit({"ok": False, "error": str(e)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
