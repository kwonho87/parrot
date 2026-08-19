import os
import pathlib

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

# server.py를 import 하기 전에 반드시 설정되어야 한다
os.environ["TTS_REFS_DIR"] = str(FIXTURES / "refs")
os.environ["TTS_TEMP_DIR"] = "/tmp/fish_tts_test_temp"
os.environ["TTS_ENGINE"] = "cli"  # 테스트에서는 mlx_speech import 방지
os.environ["TTS_LOG_DIR"] = "/tmp/fish_tts_test_logs"  # 저장소 logs/ 오염 방지
