# Parrot 🦜

> Apple Silicon에서 손쉽게 목소리를 클로닝하는 로컬 TTS 서버

[English](README.md) | **한국어**

Apple Silicon(macOS + MLX)에서 동작하는 로컬 FastAPI 기반 TTS 서버입니다. `refs` 폴더에 짧은 레퍼런스 음성과 그 스크립트만 넣으면, 요청한 문장을 그 목소리로 읽은 MP3를 생성해 반환합니다. 앵무새처럼 목소리를 따라 하며, 알림음·내레이션·짧은 음성 합성 등에 로컬에서 사용할 수 있습니다.

요청은 내부 큐(`asyncio.Queue`)에 들어가 1개씩 순서대로 처리되며, 기본 엔진(`TTS_ENGINE=worker`)은 모델을 격리된 자식 프로세스에 상주시켜 반복 요청을 빠르게 처리하고 일정 시간 idle이면 자동으로 언로드합니다.

동작 흐름:

```text
클라이언트
  -> POST http://localhost:8010/tts   { "ref_id": "...", "text": "..." }
  -> server.py (직렬 큐)
  -> fishaudio-s2-pro-8bit-mlx
  -> MP3 bytes 반환
```

---

## 환경 정보

| 항목 | 값 |
|------|-----|
| 모델 | `fishaudio-s2-pro-8bit-mlx` |
| 런타임 | Apple Silicon macOS + MLX |
| Python | `3.13` 이상 |
| Python 패키지 | `mlx-speech`, `fastapi`, `uvicorn`, `python-multipart`, `psutil`, `numpy`, `soundfile` |
| 외부 도구 | `ffmpeg` (MP3 인코딩) |
| 기본 venv 경로 | `{parrot}/.venv` |
| 기본 모델 경로 | `{parrot}/fishaudio-s2-pro-8bit-mlx` |
| 기본 refs 경로 | `{parrot}/refs` (외부 폴더는 `TTS_REFS_DIR`로 지정) |
| 기본 임시 경로 | `/tmp/fish_tts_temp` |
| 포트 | `8010` |

모델은 Hugging Face의 `mlx-community/fishaudio-s2-pro-8bit-mlx` 계열 MLX 모델을 사용합니다.

---

## 폴더 구조

```text
parrot/
├── fishaudio-s2-pro-8bit-mlx/   # 모델 파일 (git에 포함하지 않음, 로컬에 내려받음)
├── refs/                        # 레퍼런스 음원(wav + txt)
├── output/                      # 생성된 mp3 (git 제외, setup.sh가 생성)
├── .venv/                       # Python 가상환경 (git에 포함하지 않음)
├── setup.sh                     # 원클릭 셋업 + 실행 스크립트
├── server.py                    # FastAPI 서버
├── tts_engine.py                # 생성 엔진 (worker / api / cli)
├── tts_worker.py                # 모델 상주 격리 워커
├── tts_queue.py                 # 직렬 처리 큐
├── tts_logging.py               # 로깅 설정
├── tts.sh                       # start/stop/status 스크립트
├── macapp/                      # (선택) 메뉴바 관리 앱 소스
└── README.md
```

---

## refs 파일 규칙

레퍼런스 음원은 `wav + txt` 쌍으로 구성합니다.

```text
refs/
├── myvoice.wav
├── myvoice.txt
└── ...
```

규칙:

- `ref_id`는 확장자를 제외한 파일명입니다. 예: `myvoice`
- `myvoice.wav`가 있으면 `myvoice.txt`도 있어야 합니다.
- `txt` 파일에는 wav에서 실제로 말하는 내용을 최대한 정확히 적습니다.
- 레퍼런스 음원은 짧고 깨끗한 음성일수록 품질이 좋습니다.

> ⚠️ 레퍼런스로 사용하는 음성은 본인 소유이거나 사용 권한이 있는 것만 사용하세요. 타인의 목소리를 동의 없이 복제·배포하면 초상(음성)권·퍼블리시티권 문제가 될 수 있습니다.

---

## 빠른 시작 (원클릭 셋업)

`setup.sh`는 아래 과정을 명령 한 번으로 처리합니다. 리포지토리 경로를 기준(base)으로 venv 생성, 패키지 설치, 모델 다운로드, `output/` 폴더 생성, 선택한 경로들을 `.parrot.env`에 저장, 서버 기동까지 한 번에 합니다.

```bash
brew install python@3.13 ffmpeg   # 사전 준비 (최초 1회)
./setup.sh
```

끝나면 서버가 이미 `http://localhost:8010`에서 실행 중입니다. 이후에는 `./tts.sh start|stop|status|restart`로 관리합니다.

### 경로 변경

모든 경로는 옵션 또는 동일 이름의 환경변수로 바꿀 수 있습니다. 리포지토리 경로는 기본값일 뿐입니다.

```bash
# 생성 mp3·모델 저장 위치와 포트를 다르게 지정
./setup.sh --output ~/tts-out --model /Volumes/ext/fish-model --port 9000

# 환경변수로도 동일하게 지정 가능
TTS_OUTPUT_DIR=~/tts-out ./setup.sh
```

| 옵션 | 환경변수 | 기본값 |
|------|---------|--------|
| `--venv` | `PARROT_VENV` | `{parrot}/.venv` |
| `--model` | `FISH_S2_MODEL_PATH` | `{parrot}/fishaudio-s2-pro-8bit-mlx` |
| `--refs` | `TTS_REFS_DIR` | `{parrot}/refs` |
| `--output` | `TTS_OUTPUT_DIR` | `{parrot}/output` |
| `--temp` | `TTS_TEMP_DIR` | `/tmp/fish_tts_temp` |
| `--port` | `TTS_PORT` | `8010` |
| `--host` | `TTS_HOST` | `0.0.0.0` |
| `--model-repo` | `PARROT_MODEL_REPO` | `mlx-community/fishaudio-s2-pro-8bit-mlx` |
| `--python` | `PARROT_PYTHON` | `python3.13+` 자동 탐색 |

그 외 옵션: `--no-start`(셋업만 하고 서버는 띄우지 않음), `--help`(전체 목록). 선택한 경로는 `.parrot.env`에 저장되고 `tts.sh`가 시작할 때마다 읽으므로, 이후 `./tts.sh start`도 같은 경로를 재사용합니다. 우선순위는 **미리 export한 환경변수 > `.parrot.env` > 기본값** 이라서, `TTS_OUTPUT_DIR=/other ./tts.sh start`처럼 한 번만 덮어쓸 수도 있습니다.

수동으로 단계별 설치를 원하면 아래 섹션을 따르세요.

---

## 수동 세팅 (단계별)

각 단계를 직접 이해하거나 세부 설정을 바꾸고 싶다면, 저장소 루트에서 아래 순서대로 실행하세요. (아래 과정은 모두 `setup.sh`로 자동화되어 있습니다 — 맨 끝의 안내 참고.)

### 1. 사전 준비 설치

`mlx-speech`는 Python 3.13 이상이 필요합니다. macOS 기본 `python3`가 3.9인 경우가 많으므로 `python@3.13`을 설치하세요. mp3 인코딩에는 `ffmpeg`이 필요합니다.

```bash
brew install python@3.13 ffmpeg
```

### 2. 가상환경 생성

저장소 루트에서 `python3.13`으로 venv를 만듭니다.

```bash
cd parrot
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

이미 Python 3.9로 `.venv`를 만들었다면 `rm -rf .venv` 후 이 단계를 다시 실행하세요.

### 3. 패키지 설치

```bash
pip install mlx-speech fastapi uvicorn python-multipart huggingface_hub psutil numpy soundfile
```

### 4. 모델 내려받기

모델은 git에 포함하지 않고 로컬의 `fishaudio-s2-pro-8bit-mlx` 폴더에 내려받아 둡니다.

```bash
hf download mlx-community/fishaudio-s2-pro-8bit-mlx \
  --local-dir ./fishaudio-s2-pro-8bit-mlx
```

모델 저장 위치를 바꾸려면 서버 실행 전에 `FISH_S2_MODEL_PATH`를 지정합니다.

```bash
export FISH_S2_MODEL_PATH=/path/to/fishaudio-s2-pro-8bit-mlx
```

### 5. (선택) 생성된 mp3 저장 위치 지정

기본적으로 생성된 mp3는 응답 후 삭제됩니다. 사본을 남기려면 `TTS_OUTPUT_DIR`에 폴더를 지정하세요(없으면 생성됩니다).

```bash
export TTS_OUTPUT_DIR="$(pwd)/output"
```

### 6. 서버 시작

```bash
./tts.sh start
```

그다음 `http://localhost:8010/health`을 열어 확인합니다. 서버 관리(`start`/`stop`/`status`/`restart`)는 다음 섹션에서 다룹니다.

> 💡 **위 6단계를 한 번에:** 위의 모든 과정(venv, 패키지, 모델 다운로드, `output/` 폴더, 서버 시작)은 `./setup.sh` 한 번으로 자동 수행됩니다. 위의 **[빠른 시작](#빠른-시작-원클릭-셋업)**을 참고하세요. 수동 단계는 각 부분을 직접 실행·조정하고 싶을 때만 사용하면 됩니다.

---

## 서버 실행

```bash
cd parrot
./tts.sh start     # 시작
./tts.sh status    # 상태 확인
./tts.sh stop      # 종료
./tts.sh restart   # 재시작
```

로그 확인:

```bash
tail -f parrot/tts.log
```

---

## Parrot 맥 앱 (선택)

메뉴바에서 TTS 서버를 기동·감시·모니터링하는 macOS 앱 소스가 `macapp/`에 포함되어 있습니다 (macOS 14+). 설계·기능·문제 해결은 **[macapp/README.md](macapp/README.md)** 참고.

앱은 소스에서 직접 빌드합니다 (Xcode + xcodegen 필요):

```bash
./macapp/build-app.sh
open macapp/dist/Parrot.app
```

- 앱 실행 시 서버 자동 기동 (이미 `tts.sh`로 떠 있으면 attach만 함)
- 크래시 시 자동 재시작 (1s→5s→15s, 3연속 실패 시 중단)
- 앱 종료 시 서버도 종료 (설정에서 "서버 유지" 선택 가능)
- 설정(⌘,)에서 경로·포트·모델 TTL 변경

---

## API

### 헬스 체크

```bash
curl http://localhost:8010/health
```

```json
{"status":"ok"}
```

### 상태 조회

```bash
curl http://localhost:8010/status
```

```json
{
  "server": "ok",
  "uptime_sec": 1234,
  "queue_len": 0,
  "current_job": null,
  "recent": [{"ref_id": "myvoice", "text_len": 10, "ok": true, "error": null, "duration_sec": 8.2, "finished_at": "2026-08-19T12:00:00"}],
  "totals": {"ok": 12, "error": 0},
  "engine": "worker",
  "model_resident": true,
  "memory_mb": 3100
}
```

### 레퍼런스 목록 조회

```bash
curl http://localhost:8010/refs
```

```json
{
  "refs": [
    {"ref_id": "myvoice", "has_txt": true}
  ]
}
```

### TTS 생성

```bash
curl -X POST http://localhost:8010/tts \
  -H "Content-Type: application/json" \
  -d '{"ref_id":"myvoice","text":"좋은 아침이에요. 이제 일어날 시간입니다."}' \
  --output test.mp3
```

응답은 `audio/mpeg` MP3 바이너리입니다. 위 예시는 현재 폴더에 `test.mp3`를 저장합니다.

요청 파라미터:

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `ref_id` | string | Y | `refs` 폴더의 파일명, 확장자 제외 |
| `text` | string | Y | 생성할 문장 |

---

## 레퍼런스 음원 추가 방법

`refs/`(또는 `TTS_REFS_DIR`로 지정한 폴더)에 `wav + txt` 쌍을 넣으면 됩니다.

```bash
cp 새목소리.wav parrot/refs/new_ref.wav
echo "wav 파일에서 실제로 말하는 내용을 여기에 입력" > parrot/refs/new_ref.txt

curl http://localhost:8010/refs
```

서버 재시작 없이도 `/refs` 목록과 `/tts` 생성에 바로 반영됩니다.

---

## 다른 서비스에서 호출하기

같은 머신의 다른 프로세스는 `http://localhost:8010/tts`로 호출합니다. Docker 컨테이너 등 다른 네트워크 네임스페이스에서 호스트의 서버를 호출하려면 호스트 주소를 사용합니다.

```text
# 컨테이너에서 호스트의 TTS 서버 호출
http://host.docker.internal:8010/tts
```

이 경우 서버가 컨테이너에서 접근 가능한 인터페이스에 바인딩되어 있어야 합니다(`TTS_HOST` 참고). 아래 **보안 주의**를 반드시 확인하세요.

---

## 환경 변수

`server.py`와 `tts.sh`는 아래 환경 변수를 지원합니다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `FISH_S2_MODEL_PATH` | `{parrot}/fishaudio-s2-pro-8bit-mlx` | 모델 폴더 경로 |
| `TTS_REFS_DIR` | `{parrot}/refs` | 레퍼런스 음원 폴더. 외부 폴더를 쓰려면 지정 (저장소 `refs/`를 먼저 찾고 없으면 이 폴더로 폴백) |
| `TTS_TEMP_DIR` | `/tmp/fish_tts_temp` | WAV/MP3 임시 생성 폴더 |
| `TTS_OUTPUT_DIR` | *(빈 값)* | 생성된 mp3 보관 폴더. 지정하면 결과 mp3를 `{시각}_{ref_id}_{id}.mp3` 형식으로 함께 저장. 빈 값이면 보관하지 않음(응답 후 삭제). `setup.sh`는 `{parrot}/output`으로 설정 |
| `TTS_PORT` | `8010` | `tts.sh`가 사용하는 서버 포트 |
| `TTS_HOST` | `0.0.0.0` | `tts.sh`의 서버 바인딩 주소. 로컬 전용으로 제한하려면 `127.0.0.1` (아래 보안 주의 참고) |
| `TTS_ENGINE` | `worker` | `worker`=모델을 격리 자식 프로세스에 상주(빠름+크래시 격리, 권장), `api`=in-process 상주(빠르지만 크래시 시 서버 전체 종료), `cli`=요청마다 mlx-speech CLI 실행. 초기화 실패 시 cli 폴백 |
| `TTS_WORKER_TIMEOUT` | `120` | worker 엔진에서 생성 결과 대기 타임아웃(초). 초과 시 워커 kill 후 재기동 |
| `TTS_WORKER_STARTUP_TIMEOUT` | `120` | worker 모델 로드(ready) 대기 타임아웃(초) |
| `TTS_MODEL_TTL_SEC` | `600` | worker/api 엔진에서 idle 시 모델 언로드까지의 초. `0` 이하면 언로드하지 않고 영구 상주(콜드스타트 제거, 단 메모리를 계속 점유 — 전용 머신에서만 권장) |
| `TTS_REF_CACHE_MAX` | `32` | worker 엔진이 레퍼런스 인코딩 결과를 ref별로 캐시하는 최대 개수. 같은 목소리 반복 생성 시 레퍼런스 재인코딩을 건너뛴다(초과 시 오래된 것부터 제거) |
| `TTS_MP3_BITRATE` | `96k` | 출력 mp3 비트레이트. 음성엔 낮춰도 충분(예: `64k`), 응답 크기·인코딩 시간 감소 |
| `TTS_MP3_CHANNELS` | `1` | 출력 mp3 채널 수. 음성은 모노(`1`) 권장 |
| `TTS_MP3_SAMPLE_RATE` | `24000` | 출력 mp3 샘플레이트(Hz). 빈 문자열이면 원본 유지 |
| `TTS_MP3_TAIL_SILENCE_SEC` | `0.5` | 출력 mp3 끝에 덧붙이는 무음 길이(초). 알람음처럼 반복 재생 시 문장이 곧바로 이어지지 않게 한다. `0` 이하면 추가 안 함 |
| `TTS_LOG_DIR` | `{parrot}/logs` | 서버 로그 폴더. `tts.log`가 1시간마다 회전되고 7일 지난 로그는 자동 삭제. 기존 `{parrot}/tts.log`는 stdout/stderr 안전망(크래시 출력용)으로만 사용 |

예시:

```bash
cd parrot
FISH_S2_MODEL_PATH=/path/to/fishaudio-s2-pro-8bit-mlx ./tts.sh start
```

---

## 보안 주의

- **인증이 없습니다.** 이 서버에는 API 키·토큰 같은 접근 제어가 없습니다. 서버에 접근할 수 있는 누구나 `/tts`로 음성을 생성하고 `/refs`로 레퍼런스 목록을 조회할 수 있습니다.
- **기본 바인딩은 `0.0.0.0`** — `tts.sh`는 기본적으로 모든 네트워크 인터페이스에 바인딩하므로 같은 네트워크의 다른 기기에서도 접근할 수 있습니다. 로컬에서만 쓸 거라면 `TTS_HOST=127.0.0.1 ./tts.sh start`로 실행하세요. 다른 기기/컨테이너에서 접근해야 한다면 방화벽으로 신뢰하는 출처만 허용하고, 공용 네트워크에는 노출하지 마세요.
- **레퍼런스 음원 권리** — 위 "refs 파일 규칙"의 주의사항을 확인하세요.

---

## 문제 해결

### `mlx-speech: command not found`

가상환경이 활성화되지 않았거나 패키지가 설치되지 않은 상태입니다.

```bash
cd parrot
source .venv/bin/activate
pip install mlx-speech
```

### `No matching distribution found for mlx-speech`

대부분 Python 3.9 venv에서 설치했을 때 발생합니다. Python 버전을 확인합니다.

```bash
python --version
```

`Python 3.13.x`가 아니라면 venv를 다시 만듭니다.

```bash
cd parrot
deactivate 2>/dev/null || true
rm -rf .venv
brew install python@3.13
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install mlx-speech fastapi uvicorn python-multipart huggingface_hub psutil numpy soundfile
```

### `ffmpeg` 오류

MP3 변환에 `ffmpeg`가 필요합니다.

```bash
brew install ffmpeg
```

### 모델 파일을 찾지 못하는 경우

`FISH_S2_MODEL_PATH` 또는 `{parrot}/fishaudio-s2-pro-8bit-mlx` 경로를 확인합니다.

```bash
ls -la parrot/fishaudio-s2-pro-8bit-mlx
```

### 다른 기기/컨테이너에서 호출이 안 되는 경우

먼저 호스트에서 서버가 응답하는지 확인합니다.

```bash
curl http://localhost:8010/health
```

그 다음 서버가 외부에서 접근 가능한 주소에 바인딩되어 있는지(`TTS_HOST`), 방화벽이 포트 `8010`을 막고 있지 않은지 확인합니다.

---

## 라이선스

이 저장소의 코드는 [MIT License](LICENSE)로 배포됩니다.

TTS 모델(`fishaudio-s2-pro-8bit-mlx`)은 이 저장소에 포함되지 않으며, 별도로 내려받아 사용합니다. 모델에는 각자의 라이선스가 적용되므로 [Hugging Face 모델 페이지](https://huggingface.co/mlx-community/fishaudio-s2-pro-8bit-mlx)의 라이선스를 확인하세요.
