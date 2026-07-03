"""Конфиг Germes v2. Настраивается через .env и переменные окружения."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Config:
    # Vosk
    model_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT / _get("GERMES_MODEL_DIR", "models/vosk-model-small-ru-0.22")
    )
    wake_word: str = field(default_factory=lambda: _get("GERMES_WAKE_WORD", "гермес").lower())

    # TTS
    tts_voice: str = field(default_factory=lambda: _get("GERMES_TTS_VOICE", "ru-RU-SvetlanaNeural"))
    tts_rate: str = field(default_factory=lambda: _get("GERMES_TTS_RATE", "+30%"))

    # Brain (Hermes)
    brain_cmd: str = field(
        default_factory=lambda: _get("GERMES_BRAIN_CMD", 'hermes -z "{prompt}" --yolo')
    )
    brain_timeout: float = float(_get("GERMES_BRAIN_TIMEOUT", "60"))

    # Audio
    input_device: Optional[int] = None
    sample_rate: int = 16000
    block_size: int = 4000

    # Wake word detection
    wake_partial_threshold: float = 0.3   # уверенность partial для реакции
    wake_cooldown_sec: float = 1.5        # анти-дребезг после срабатывания

    # Command capture
    command_timeout: float = 6.0          # макс. длина команды после wake
    silence_to_send: float = 1.2          # тишина перед отправкой в brain
    rms_voice_threshold: float = 350.0    # порог «голоса» для VAD

    # Skills
    skills_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "germes" / "skills")
    skill_cache_ttl_sec: int = int(_get("GERMES_SKILL_CACHE_TTL", "3600"))
    auto_create_skills: bool = _get("GERMES_AUTO_CREATE_SKILLS", "true").lower() == "true"

    # Logging
    log_level: str = field(default_factory=lambda: _get("GERMES_LOG_LEVEL", "INFO").upper())

    # Shortcuts
    project_root: Path = PROJECT_ROOT  # convenience alias

    def __post_init__(self) -> None:
        dev = _get("GERMES_INPUT_DEVICE")
        if dev and dev.lstrip("-").isdigit():
            object.__setattr__(self, "input_device", int(dev))


CONFIG = Config()
