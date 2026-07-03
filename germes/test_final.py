"""Final integration test for Germes agent."""
import sys

print("=== GERMES FINAL INTEGRATION TEST ===")
print(f"Python: {sys.version}")

# 1. Config
from germes.config import CONFIG
assert CONFIG.wake_word == "гермес", f"Wake word mismatch: {CONFIG.wake_word}"
assert CONFIG.tts_voice == "ru-RU-DmitryNeural", f"Voice mismatch: {CONFIG.tts_voice}"
assert CONFIG.tts_rate == "+20%", f"Rate mismatch: {CONFIG.tts_rate}"
print(f"[PASS] Config: wake={CONFIG.wake_word}, voice={CONFIG.tts_voice}, rate={CONFIG.tts_rate}")

# 2. STT + Whisper
from germes.stt import STT, contains_wake_word, transcribe_with_whisper
assert contains_wake_word("гермес привет")
assert not contains_wake_word("малина")
print("[PASS] STT: wake detection OK, whisper imported")

# 3. TTS
from germes.tts import speak
print("[PASS] TTS: import OK")

# 4. Skills
from germes.skills import REGISTRY
REGISTRY.load_builtin()
skills = REGISTRY.list_skills()
assert len(skills) >= 7
print(f"[PASS] Skills: {len(skills)} loaded")

# 5. Audio
from germes.audio import AUDIO_STREAM
print("[PASS] Audio: OK")

# 6. Main
from germes.__main__ import Germes
app = Germes()
print("[PASS] Main: Germes instantiated")

print()
print("========================================")
print(" ALL CHECKS PASSED — GERMES READY")
print(" Voice: ru-RU-DmitryNeural (+20%)")
print(" STT: Vosk (wake) + faster-whisper (cmd)")
print(" Encoding: UTF-8 (chcp 65001 in run.bat)")
print("========================================")
