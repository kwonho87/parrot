#!/bin/zsh
# ================================================================
#  tts.sh — Fish-Speech S2 Pro MLX TTS 서버 start/stop 스크립트
#
#  사용법:
#    ./tts.sh start    서버 시작
#    ./tts.sh stop     서버 종료
#    ./tts.sh status   상태 확인
#    ./tts.sh restart  재시작
#
#  서버 파일:  {parrot}/server.py
#  venv:       {parrot}/.venv
#  포트:       8010
# ================================================================

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$BASE_DIR/.venv"
PID_FILE="$BASE_DIR/tts.pid"
LOG_FILE="$BASE_DIR/tts.log"
PORT=8010
PYTHON="$VENV/bin/python"
# 레퍼런스 음원 폴더. 저장소 refs/가 기본이며, 외부 폴더를 쓰려면 TTS_REFS_DIR로 지정.
DEFAULT_REFS_DIR="$BASE_DIR/refs"
# 바인딩 주소. 기본은 모든 인터페이스(0.0.0.0) — 같은 네트워크/컨테이너에서 접근 가능.
# 로컬 전용으로 제한하려면 TTS_HOST=127.0.0.1 로 실행.
HOST="${TTS_HOST:-0.0.0.0}"

port_pid() {
  lsof -ti tcp:$PORT -sTCP:LISTEN 2>/dev/null | head -n 1
}

start() {
  if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    echo "✅ TTS 서버가 이미 실행 중입니다. (PID: $(cat $PID_FILE))"
    return
  fi

  EXISTING_PID=$(port_pid)
  if [ -n "$EXISTING_PID" ]; then
    echo "$EXISTING_PID" > "$PID_FILE"
    echo "✅ TTS 서버가 이미 포트 $PORT 에서 실행 중입니다. (PID: $EXISTING_PID)"
    echo "   http://localhost:$PORT/health"
    return
  fi

  if [ ! -x "$PYTHON" ]; then
    echo "❌ venv python 을 찾을 수 없습니다: $PYTHON"
    return
  fi

  echo "🚀 TTS 서버 시작 중..."
  export PATH="$VENV/bin:$PATH"
  export FISH_S2_MODEL_PATH="${FISH_S2_MODEL_PATH:-$BASE_DIR/fishaudio-s2-pro-8bit-mlx}"
  export TTS_REFS_DIR="${TTS_REFS_DIR:-$DEFAULT_REFS_DIR}"
  export TTS_TEMP_DIR="${TTS_TEMP_DIR:-/tmp/fish_tts_temp}"
  nohup "$PYTHON" -m uvicorn server:app \
    --host "$HOST" \
    --port $PORT \
    --app-dir "$BASE_DIR" \
    >> "$LOG_FILE" 2>&1 &

  echo $! > "$PID_FILE"
  sleep 1

  if kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    echo "✅ TTS 서버 시작 완료! (PID: $(cat $PID_FILE), PORT: $PORT)"
    echo "   http://localhost:$PORT/health"
  else
    echo "❌ 서버 시작 실패. 로그 확인: $LOG_FILE"
  fi
}

stop() {
  if [ ! -f "$PID_FILE" ]; then
    PID=$(port_pid)
    if [ -z "$PID" ]; then
      echo "⚠️  PID 파일이 없고 포트 $PORT 에 실행 중인 서버도 없습니다."
      return
    fi
  else
    PID=$(cat "$PID_FILE")
  fi

  if kill -0 $PID 2>/dev/null; then
    kill $PID
    rm "$PID_FILE"
    echo "🛑 TTS 서버 종료 완료. (PID: $PID)"
  else
    echo "⚠️  프로세스가 이미 종료되어 있어요."
    rm "$PID_FILE"
  fi
}

status() {
  if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    echo "✅ 실행 중 (PID: $(cat $PID_FILE))"
    echo "   http://localhost:$PORT/health"
  elif [ -n "$(port_pid)" ]; then
    PID=$(port_pid)
    echo "✅ 실행 중 (PID: $PID, PID 파일 없음)"
    echo "   http://localhost:$PORT/health"
  else
    echo "🔴 중지됨"
  fi
}

case "$1" in
  start)   start ;;
  stop)    stop ;;
  status)  status ;;
  restart) stop; sleep 1; start ;;
  *)
    echo "사용법: tts.sh [start|stop|status|restart]"
    ;;
esac
