#!/usr/bin/env bash
# ================================================================
#  setup.sh — Parrot TTS 서버 원클릭 셋업 & 실행 스크립트
#
#  하는 일 (리포지토리 경로를 기준(base)으로):
#    1) Python 3.13+ 가상환경(venv) 생성
#    2) 필요한 패키지 설치
#    3) TTS 모델 다운로드
#    4) 생성 mp3 보관용 output 폴더 생성
#    5) 선택한 경로들을 .parrot.env 에 저장 (tts.sh 가 읽음)
#    6) tts.sh 로 서버 기동
#
#  사용법:
#    ./setup.sh                    # 기본값으로 셋업 후 서버 시작
#    ./setup.sh --no-start         # 셋업만 하고 서버는 띄우지 않음
#    ./setup.sh --output ~/tts-out # 생성 mp3 저장 폴더 변경
#    ./setup.sh --help             # 전체 옵션 보기
#
#  모든 경로는 옵션 또는 동일 이름의 환경변수로 변경할 수 있습니다.
# ================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---- 기본값 (환경변수로도 덮어쓸 수 있음) --------------------------------
VENV_DIR="${PARROT_VENV:-$BASE_DIR/.venv}"
MODEL_DIR="${FISH_S2_MODEL_PATH:-$BASE_DIR/fishaudio-s2-pro-8bit-mlx}"
REFS_DIR="${TTS_REFS_DIR:-$BASE_DIR/refs}"
OUTPUT_DIR="${TTS_OUTPUT_DIR:-$BASE_DIR/output}"
TEMP_DIR="${TTS_TEMP_DIR:-/tmp/fish_tts_temp}"
PORT="${TTS_PORT:-8010}"
HOST="${TTS_HOST:-0.0.0.0}"
MODEL_REPO="${PARROT_MODEL_REPO:-mlx-community/fishaudio-s2-pro-8bit-mlx}"
PYTHON_BIN="${PARROT_PYTHON:-}"
START_SERVER=1

usage() {
  cat <<EOF
Parrot 셋업 스크립트

사용법: ./setup.sh [옵션]

경로 옵션 (미지정 시 리포지토리 경로 기준 기본값):
  --venv <경로>        가상환경 위치            (기본: $BASE_DIR/.venv)
  --model <경로>       모델 다운로드/사용 위치   (기본: $BASE_DIR/fishaudio-s2-pro-8bit-mlx)
  --refs <경로>        레퍼런스 음원 폴더        (기본: $BASE_DIR/refs)
  --output <경로>      생성 mp3 보관 폴더        (기본: $BASE_DIR/output)
  --temp <경로>        임시 작업 폴더            (기본: /tmp/fish_tts_temp)

기타 옵션:
  --port <포트>        서버 포트                (기본: 8010)
  --host <주소>        바인딩 주소              (기본: 0.0.0.0, 로컬 전용은 127.0.0.1)
  --model-repo <id>    HuggingFace 모델 저장소   (기본: $MODEL_REPO)
  --python <경로>      사용할 python 실행파일    (기본: python3.13 자동 탐색)
  --no-start           셋업만 하고 서버는 띄우지 않음
  -h, --help           이 도움말

모든 경로는 동일 이름의 환경변수(FISH_S2_MODEL_PATH, TTS_REFS_DIR,
TTS_OUTPUT_DIR, TTS_TEMP_DIR, TTS_PORT, TTS_HOST, PARROT_VENV)로도 지정할 수 있습니다.
EOF
}

# ---- 옵션 파싱 --------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --venv)       VENV_DIR="$2"; shift 2 ;;
    --model)      MODEL_DIR="$2"; shift 2 ;;
    --refs)       REFS_DIR="$2"; shift 2 ;;
    --output)     OUTPUT_DIR="$2"; shift 2 ;;
    --temp)       TEMP_DIR="$2"; shift 2 ;;
    --port)       PORT="$2"; shift 2 ;;
    --host)       HOST="$2"; shift 2 ;;
    --model-repo) MODEL_REPO="$2"; shift 2 ;;
    --python)     PYTHON_BIN="$2"; shift 2 ;;
    --no-start)   START_SERVER=0; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "❌ 알 수 없는 옵션: $1"; echo; usage; exit 1 ;;
  esac
done

# 상대경로를 절대경로로 정규화 (서버가 어디서 실행돼도 동일하게 동작하도록)
abspath() {
  local p="$1"
  case "$p" in
    /*) printf '%s\n' "$p" ;;
    "~"/*|"~") printf '%s\n' "${p/#\~/$HOME}" ;;
    *)  printf '%s\n' "$BASE_DIR/$p" ;;
  esac
}
VENV_DIR="$(abspath "$VENV_DIR")"
MODEL_DIR="$(abspath "$MODEL_DIR")"
REFS_DIR="$(abspath "$REFS_DIR")"
OUTPUT_DIR="$(abspath "$OUTPUT_DIR")"

echo "🦜 Parrot 셋업 시작"
echo "   리포지토리 : $BASE_DIR"
echo "   venv       : $VENV_DIR"
echo "   모델       : $MODEL_DIR  ($MODEL_REPO)"
echo "   refs       : $REFS_DIR"
echo "   output     : $OUTPUT_DIR"
echo "   temp       : $TEMP_DIR"
echo "   서버       : $HOST:$PORT"
echo

# ---- 1) Python 3.13+ 찾기 --------------------------------------------
find_python() {
  if [ -n "$PYTHON_BIN" ]; then echo "$PYTHON_BIN"; return; fi
  for c in python3.13 python3.14 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,13) else 1)' 2>/dev/null; then
        command -v "$c"; return
      fi
    fi
  done
  return 1
}

if ! PY="$(find_python)"; then
  echo "❌ Python 3.13 이상을 찾을 수 없습니다. 먼저 설치하세요:"
  echo "   brew install python@3.13"
  exit 1
fi
echo "🐍 Python: $PY ($("$PY" --version 2>&1))"

# ---- ffmpeg 확인 (mp3 인코딩 필수) ------------------------------------
if ! command -v ffmpeg >/dev/null 2>&1 \
   && [ ! -x /opt/homebrew/bin/ffmpeg ] && [ ! -x /usr/local/bin/ffmpeg ]; then
  echo "⚠️  ffmpeg 이 없습니다. mp3 인코딩에 필요합니다. 설치하세요:"
  echo "   brew install ffmpeg"
  echo "   (일단 계속 진행하지만, 설치 전에는 TTS 요청이 실패합니다.)"
fi

# ---- 2) venv 생성 -----------------------------------------------------
if [ -x "$VENV_DIR/bin/python" ]; then
  echo "📦 기존 venv 재사용: $VENV_DIR"
else
  echo "📦 venv 생성: $VENV_DIR"
  "$PY" -m venv "$VENV_DIR"
fi
VPY="$VENV_DIR/bin/python"

# ---- 3) 패키지 설치 ----------------------------------------------------
echo "⬇️  패키지 설치 중..."
"$VPY" -m pip install --upgrade pip >/dev/null
"$VPY" -m pip install \
  mlx-speech fastapi uvicorn python-multipart "huggingface_hub[cli]" psutil numpy soundfile
echo "✅ 패키지 설치 완료"

# ---- 4) 모델 다운로드 --------------------------------------------------
if [ -f "$MODEL_DIR/config.json" ]; then
  echo "✅ 모델이 이미 있습니다: $MODEL_DIR (건너뜀)"
else
  echo "⬇️  모델 다운로드: $MODEL_REPO -> $MODEL_DIR"
  mkdir -p "$MODEL_DIR"
  "$VPY" - "$MODEL_REPO" "$MODEL_DIR" <<'PYEOF'
import sys
from huggingface_hub import snapshot_download
repo, dest = sys.argv[1], sys.argv[2]
snapshot_download(repo_id=repo, local_dir=dest)
print("모델 다운로드 완료:", dest)
PYEOF
fi

# ---- 5) 폴더 준비 + 설정 파일 기록 ------------------------------------
mkdir -p "$REFS_DIR" "$OUTPUT_DIR"

ENV_FILE="$BASE_DIR/.parrot.env"
cat > "$ENV_FILE" <<EOF
# setup.sh 가 생성한 Parrot 설정 파일. tts.sh 가 시작 시 자동으로 읽습니다.
# 실행 전에 같은 이름의 환경변수를 export 하면 그 값이 우선합니다.
export PARROT_VENV="\${PARROT_VENV:-$VENV_DIR}"
export FISH_S2_MODEL_PATH="\${FISH_S2_MODEL_PATH:-$MODEL_DIR}"
export TTS_REFS_DIR="\${TTS_REFS_DIR:-$REFS_DIR}"
export TTS_OUTPUT_DIR="\${TTS_OUTPUT_DIR:-$OUTPUT_DIR}"
export TTS_TEMP_DIR="\${TTS_TEMP_DIR:-$TEMP_DIR}"
export TTS_PORT="\${TTS_PORT:-$PORT}"
export TTS_HOST="\${TTS_HOST:-$HOST}"
EOF
echo "📝 설정 저장: $ENV_FILE"

echo
echo "✅ 셋업 완료!"

# ---- 6) 서버 시작 -----------------------------------------------------
if [ "$START_SERVER" -eq 1 ]; then
  echo "🚀 서버를 시작합니다..."
  exec "$BASE_DIR/tts.sh" start
else
  echo "서버를 시작하려면:  ./tts.sh start"
fi
