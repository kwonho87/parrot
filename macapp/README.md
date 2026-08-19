# Parrot 맥 앱

Parrot Python TTS 서버를 **기동·감시·모니터링**하는 macOS 메뉴바 앱입니다.
터미널이나 `tts.sh` 없이, 앱을 켜면 서버가 뜨고 메뉴바에서 상태를 한눈에 확인할 수 있습니다.

- 지원: macOS 14 (Sonoma) 이상, Apple Silicon
- 기술: SwiftUI, XcodeGen, XCTest
- 원칙: 앱은 서버의 **관리자 역할만** 합니다. TTS 생성 요청은 클라이언트가 `localhost:8010`을 직접 호출하며, 앱은 데이터 경로에 끼어들지 않습니다.

---

## 전체 구조

```text
Parrot.app (SwiftUI, 메뉴바 상주)
  ├─ 기동:   {parrot}/.venv 의 uvicorn(server.py)을 자식 프로세스로 실행
  ├─ 감시:   프로세스 종료 감지 → 백오프 재시작 (크래시 루프 보호)
  └─ 모니터: GET /status 2초 폴링 → 메뉴바 아이콘·대시보드에 반영

클라이언트 ── POST localhost:8010/tts ──▶ server.py
```

앱 없이도 `./tts.sh start`로 운영할 수 있습니다. 이미 서버가 떠 있는 상태에서
앱을 실행하면 죽이지 않고 **attach 모드**(모니터링만)로 동작합니다.

---

## 기능

### 메뉴바

| 아이콘 | 의미 |
|--------|------|
| 파형 (waveform) | 정상 대기 중 |
| 파형+마이크 | TTS 생성 작업 진행 중 |
| 파형+느낌표 | 오류 (크래시 반복, 경로 문제 등) |
| 파형+빗금 | 서버 중지됨 |

아이콘을 클릭하면 미니 패널이 열립니다:

- 상태 표시등 — 초록(실행 중) / 주황(프로세스는 살아있는데 응답 없음 — 생성 작업이 길어 이벤트 루프가 밀린 상황과 구분) / 노랑(시작 중) / 회색(중지) / 빨강(오류)
- 현재 생성 중인 작업(ref_id, 경과 시간), 큐 대기 수, 누적 성공/실패, 메모리, 모델 상주 여부
- 서버 시작 / 중지 버튼, 대시보드 열기, **로그인 시 자동 시작** 토글, 앱 종료

### 대시보드 창

미니 패널에서 "대시보드"를 누르면 열립니다 (640×560):

| 섹션 | 내용 |
|------|------|
| 서버 상태 | Uptime, 메모리(MB, 서버+자식 프로세스 RSS 합), 엔진(worker/api/cli), 모델 상주 여부 |
| 모델 폴더 | 현재 모델 경로 + 존재 여부 표시, **폴더 선택… 다이얼로그**, 서버 재시작 버튼 |
| 큐 | 현재 작업(텍스트 길이·경과 시간), 대기 건수, 누적 통계 |
| 최근 요청 | 최근 10건 테이블 — ref_id / 성공·실패(에러 메시지) / 소요 초 / 완료 시각 |
| 레퍼런스 음원 | `/refs` 목록, txt 누락 경고, 새로고침 |
| 로그 | `tts.log` 마지막 8KB tail (2초 갱신, 텍스트 선택 가능) |

### 설정 (⌘,)

| 항목 | 기본값 | 설명 |
|------|--------|------|
| 저장소 경로 | 자동 감지 | server.py와 `.venv`가 있는 parrot 폴더 |
| refs 폴더 | `{저장소}/refs` | 레퍼런스 wav+txt 폴더 |
| 모델 폴더 | `{저장소}/fishaudio-s2-pro-8bit-mlx` | 대시보드에서도 변경 가능 |
| 생성 mp3 저장 폴더 | `{저장소}/output` | 앱이 직접 띄운 서버가 생성 mp3를 보관하는 폴더(`TTS_OUTPUT_DIR`). 비우면 저장 안 함. attach된 외부 서버는 `.parrot.env` 설정을 따름 |
| 포트 | 8010 | 1~65535로 자동 클램프 |
| 생성 엔진 | `cli` (안정성 우선) | `cli`=요청마다 별도 프로세스에서 생성 (GPU/MLX 크래시가 나도 그 요청만 실패, 서버는 유지). `api`=모델 상주로 빠르지만 크래시 시 서버 프로세스 전체가 재시작됨 |
| 모델 idle TTL | 600초 | api 엔진에서 유휴 시 모델 언로드까지의 시간 |
| 앱 종료 시 서버 유지 | 꺼짐 | 켜면 앱을 꺼도 서버가 계속 돌아감 |

경로 자동 감지:

- 저장소: 앱 번들이 `{저장소}/macapp/dist/Parrot.app`에서 실행 중이면 그 저장소를 사용. `/Applications` 등으로 복사한 경우 설정(⌘,)에서 저장소 경로를 직접 지정.
- refs: `{저장소}/refs` (설정에서 외부 폴더로 변경 가능)

설정은 UserDefaults에 저장되며, 경로·포트 변경은 **서버 재시작 후 반영**됩니다.

- `.parrot.env` 동기화: `setup.sh`가 저장소에 `.parrot.env`를 만들어 두었다면, 저장된 설정이 없는 항목(포트, 생성 mp3 저장 폴더, refs·모델 경로)의 **초기 기본값을 그 파일에서 가져옵니다**. 덕분에 setup.sh로 포트를 바꿔 띄운 서버에도 앱이 중복 실행 없이 attach됩니다. (이미 설정 화면에서 바꾼 값이 있으면 그 값이 우선)

### 안정성 (자동 복구)

- 서버 프로세스가 죽으면 자동 재시작: **1초 → 5초 → 15초** 백오프
- 연속 3회 실패하면 crash loop로 판단하고 중단 — 메뉴바가 빨간 오류 상태가 되고 로그 경로를 안내
- 60초 이상 안정 구동 후의 크래시는 카운터가 리셋되어 다시 1초부터
- 백오프 대기 중에 "서버 중지"를 누르면 예약된 재시작도 취소됨
- 서버 중지는 SIGTERM 후 5초 내에 안 죽으면 SIGKILL
- 앱은 기본 생성 엔진을 `cli`(안정성 우선)로 둔다 — 일부 환경에서 mlx/Metal GPU 오류로
  서버 프로세스 전체가 abort되는 경우가 있는데, cli 모드는 요청마다 별도 프로세스에서
  생성하므로 그런 크래시가 나도 서버 본체는 살아있고 해당 요청만 재시도 대상이 된다.
  속도가 더 중요하면 설정에서 `api`로 바꿀 수 있다.

### 종료 동작

| 상황 | 앱 종료 시 |
|------|-----------|
| 앱이 띄운 서버 | 함께 종료 (SIGTERM 전달 후 종료) |
| "서버 유지" 설정 켬 | 서버 유지 |
| attach 모드 (외부에서 띄운 서버) | 절대 건드리지 않음 |

---

## 초기 세팅

앱은 Python 런타임과 모델을 번들하지 않으므로 서버 쪽 세팅이 먼저 필요합니다.
아래는 저장소 경로가 `~/parrot`인 기준입니다(다른 경로라면 그에 맞게 바꾸세요 —
앱 설정에서도 저장소 경로를 지정할 수 있습니다).

### 1. 기본 도구

```bash
# Homebrew가 없다면
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install python@3.13 ffmpeg git xcodegen
```

### 2. 저장소 받기

```bash
cd ~
git clone https://github.com/kwonho87/parrot.git
cd parrot
```

### 3. Python venv + 패키지

`mlx-speech`는 Python 3.13 이상이 필요합니다. 반드시 `python3.13`으로 venv를 만드세요:

```bash
python3.13 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install mlx-speech fastapi uvicorn python-multipart huggingface_hub \
                      psutil numpy soundfile
```

### 4. 모델 다운로드 (수 GB — 시간 걸림)

```bash
.venv/bin/hf download mlx-community/fishaudio-s2-pro-8bit-mlx \
  --local-dir ./fishaudio-s2-pro-8bit-mlx

ls ./fishaudio-s2-pro-8bit-mlx    # model.safetensors, config.json 등이 보여야 함
```

### 5. 레퍼런스 음원 확인

`refs/` 폴더에 `wav + txt` 쌍이 있어야 합니다. 추가 방법은 루트 README의
"레퍼런스 음원 추가 방법"을 참고하세요.

```bash
ls refs/
```

### 6. 앱 빌드 및 실행

앱은 소스에서 직접 빌드합니다 (Xcode + xcodegen 필요):

```bash
./macapp/build-app.sh          # → macapp/dist/Parrot.app 생성 (Release + ad-hoc 서명)
open macapp/dist/Parrot.app
```

메뉴바에 파형 아이콘이 뜨고 서버가 자동 기동됩니다.
`/Applications`로 복사해 쓰려면 `cp -R macapp/dist/Parrot.app /Applications/` 후 실행하세요.

> ad-hoc 서명 앱을 `/Applications` 등으로 옮기면 Gatekeeper가 막을 수 있습니다.
> 그때는 `xattr -dr com.apple.quarantine /Applications/Parrot.app` 후 실행하세요.

### 7. 동작 확인

```bash
sleep 5
curl http://localhost:8010/health     # {"status":"ok"}
curl http://localhost:8010/refs        # 레퍼런스 목록

curl -X POST http://localhost:8010/tts \
  -H "Content-Type: application/json" \
  -d '{"ref_id":"myvoice","text":"좋은 아침이에요. 이제 일어날 시간입니다."}' \
  --output /tmp/test.mp3
file /tmp/test.mp3 && afplay /tmp/test.mp3   # 소리로 확인
```

`myvoice`는 `refs/`에 있는 실제 `ref_id`로 바꾸세요.

생성 후 `/status`에서 `engine`을 확인할 수 있습니다:

- `"engine": "worker"` / `"api"` — 모델 상주 모드 정상. 같은 요청을 한 번 더 보내면
  모델 로드가 생략되어 눈에 띄게 빨라집니다.
- `"engine": "cli"` — 상주 엔진 초기화가 실패해 CLI 방식으로 폴백된 상태입니다.
  동작에는 문제없지만 상주 효과가 없으니 `tts.log`를 확인하세요.

### 부팅 시 자동 시작

메뉴바의 파형 아이콘 클릭 → **"로그인 시 자동 시작"** 토글 ON.
(시스템 설정 > 일반 > 로그인 항목에 Parrot가 등록됩니다.)

### 경로가 자동 감지와 다를 때

메뉴바 패널에 "venv를 찾을 수 없습니다" 또는 "모델 폴더가 없습니다"가 뜨면:

1. 설정(⌘,)에서 **저장소 경로**를 실제 parrot 폴더로 지정
2. 대시보드의 **"모델 폴더"** 섹션에서 폴더 선택
3. "서버 재시작" 버튼 클릭

### tts.sh와의 관계

- 앱 사용 중에도 `./tts.sh status`로 상태 확인 가능 (같은 서버를 봅니다)
- `tts.sh start`로 먼저 띄운 뒤 앱을 켜면 앱은 attach 모드(모니터링만)로 동작
- 앱을 쓰는 동안에는 `tts.sh stop`을 쓰지 마세요 — 앱이 크래시로 판단해
  자동 재시작합니다. 서버를 내리려면 앱의 "서버 중지" 버튼이나 앱 종료를 사용하세요.

---

## 앱 설계 (코드 구조)

```text
macapp/
├── project.yml               # XcodeGen 정의 (.xcodeproj는 생성물이라 git 제외)
├── build-app.sh              # Release 빌드 + ad-hoc 서명 + dist/ 갱신
├── dist/Parrot.app          # 빌드 산출물 (git 제외 — build-app.sh로 생성)
├── Parrot/
│   ├── ParrotApp.swift      # @main. MenuBarExtra + 대시보드 Window + Settings 씬.
│   │                         #   label의 .task에서 서버 자동 기동 (XCTest 호스트에선 스킵)
│   ├── AppDelegate.swift     # 앱 종료 시 관리 중인 서버 정리 (keepServerOnQuit/attach 존중)
│   ├── ServerManager.swift   # 핵심 상태머신. Process로 uvicorn 실행/감시.
│   │                         #   상태: stopped/starting/running/attached/failed
│   │                         #   startOrAttach() → /health 응답 시 attach, 아니면 launch
│   │                         #   stop() → SIGTERM + 5초 후 SIGKILL
│   │                         #   restart() → 종료 완료를 폴링 대기 후 start (레이스 없음)
│   │                         #   로그는 O_APPEND로 tts.log에 리다이렉트
│   ├── RestartPolicy.swift   # 백오프·crash loop 판단 (순수 로직, 단위 테스트 대상)
│   ├── StatusPoller.swift    # GET /status 2초 폴링, /refs 새로고침
│   ├── LogTailer.swift       # tts.log 마지막 8KB tail (UTF-8 경계 안전)
│   ├── AppSettings.swift     # UserDefaults 설정 싱글턴 + 경로 자동 감지/검증
│   ├── Models.swift          # /status·/refs JSON 디코딩 (snake_case 변환)
│   ├── MenuPanelView.swift   # 메뉴바 미니 패널
│   ├── DashboardView.swift   # 대시보드 창
│   ├── SettingsView.swift    # 설정 화면
│   └── LoginItemToggle.swift # SMAppService 로그인 아이템 등록
└── ParrotTests/             # XCTest — Models 디코딩, RestartPolicy, AppSettings, LogTailer
```

### 서버 기동 방식

ServerManager는 아래와 동일한 프로세스를 자식으로 실행합니다:

```bash
{저장소}/.venv/bin/python -m uvicorn server:app \
  --host 0.0.0.0 --port {포트} --app-dir {저장소}
```

환경변수로 설정을 전달합니다: `TTS_REFS_DIR`, `TTS_MODEL_PATH`,
`TTS_OUTPUT_DIR`, `TTS_MODEL_TTL_SEC`, `TTS_TEMP_DIR`. 즉 `tts.sh`와 동일한 방식으로 서버를
띄우므로 두 방식을 오가도 서버 동작이 달라지지 않습니다. 바인딩 주소의
보안 주의는 루트 [README](../README.md)의 "보안 주의" 섹션을 참고하세요.

### 서버와의 계약

앱이 의존하는 서버 엔드포인트는 3개뿐입니다:

- `GET /health` — attach 판단·생존 확인
- `GET /status` — 큐 길이, 현재 작업, 최근 10건, 누적 통계, 엔진, 모델 상주, 메모리(MB)
- `GET /refs` — 레퍼런스 음원 목록

`/status` 응답 형식은 루트 README의 "상태 조회" 섹션 참고. 필드가 추가되어도
앱 디코딩은 깨지지 않습니다 (미지의 키 무시).

---

## 개발 / 빌드

빌드 도구 (개발 머신에만 필요 — 실행만 할 맥에는 불필요):

```bash
xcode-select --install   # 또는 Xcode 설치
brew install xcodegen
```

빌드:

```bash
./macapp/build-app.sh
# → macapp/dist/Parrot.app 생성 (Release + ad-hoc 서명)
```

`.xcodeproj`는 git에 없습니다 — `cd macapp && xcodegen generate`로 언제든 재생성되며,
Xcode에서 열어 개발하려면 생성 후 `Parrot.xcodeproj`를 열면 됩니다.
Swift 파일을 추가/삭제하면 `xcodegen generate`를 다시 실행해야 합니다.

테스트:

```bash
cd macapp
xcodegen generate
xcodebuild -project Parrot.xcodeproj -scheme Parrot -destination 'platform=macOS' test
```

서명은 ad-hoc(본인 맥 전용)입니다. Apple Developer 계정·공증 없이 동작하지만,
불특정 다수 배포에는 적합하지 않습니다.

---

## 문제 해결

### 메뉴바가 빨간 오류 상태일 때

패널을 열면 원인이 표시됩니다:

- **"venv를 찾을 수 없습니다"** — 설정(⌘,)에서 저장소 경로 확인, 루트 README의 최초 세팅 진행
- **"모델 폴더가 없습니다"** — 대시보드 "모델 폴더"에서 올바른 폴더 선택, 또는 모델 다운로드
- **"서버가 반복 종료되어 재시작을 중단했습니다"** — 대시보드의 로그 섹션(또는 `tts.log`)에서 크래시 원인 확인 후 "서버 시작"으로 수동 재시도

### "연결됨 (외부 실행)"이라고 뜰 때

포트 8010에 이미 서버가 있어 attach 모드로 동작 중입니다. 앱에서 중지/재시작할 수 없고
(`tts.sh stop`으로 내리면 됩니다), 앱 종료 시에도 그 서버는 유지됩니다.

### 상태 표시등이 주황(응답 없음)일 때

프로세스는 살아있지만 `/status` 응답이 5초 안에 오지 않는 상태입니다. 대부분 긴 TTS
생성 작업 중 이벤트 루프가 밀린 것으로, 작업이 끝나면 초록으로 돌아옵니다.

### 포트 충돌

다른 프로세스가 8010을 쓰고 있으면 attach 판단이 잘못될 수 있습니다.
`lsof -ti tcp:8010`으로 확인하고, 필요하면 설정에서 포트를 바꾸세요
(클라이언트 쪽 호출 URL도 함께 변경 필요).

### 서버 자체 문제 (mlx-speech, ffmpeg, 모델 등)

앱이 아니라 서버 영역입니다 — 루트 [README](../README.md)의 "문제 해결" 섹션 참고.
`/status`의 `engine`이 `cli`로 나오면 상주 엔진 초기화가 실패해 CLI 방식으로
폴백된 것이니 `tts.log`를 확인하세요.
