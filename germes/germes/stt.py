"""Распознавание речи: Vosk (wake-word) + faster-whisper (команды).

Vosk — лёгкий, работает в реальном времени для детекции wake-word.
faster-whisper — точный и быстрый перевод/транскрипция после активации.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from vosk import KaldiRecognizer, Model, SetLogLevel

from .config import CONFIG

log = logging.getLogger("germes.stt")

# Vosk и так тихий, но уберём спам варнингов в наш логгер
SetLogLevel(-1)

# Lazy-load faster-whisper (тяжёлая зависимость, грузим по требованию)
_whisper_model = None


def _get_whisper_model():
    """Ленивая загрузка модели faster-whisper."""
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            log.info("Загружаю faster-whisper модель (base)...")
            _whisper_model = WhisperModel(
                "base",
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
            )
            log.info("faster-whisper загружен")
        except Exception as exc:
            log.error("Не удалось загрузить faster-whisper: %s", exc)
            raise
    return _whisper_model


def transcribe_with_whisper(audio_path: str) -> str:
    """Транскрибировать аудиофайл через faster-whisper.

    Args:
        audio_path: путь к WAV/MP3 файлу

    Returns:
        Распознанный текст (русский язык по умолчанию)
    """
    model = _get_whisper_model()
    segments, info = model.transcribe(
        audio_path,
        language="ru",
        beam_size=5,
        vad_filter=True,
    )
    text_parts = [segment.text.strip() for segment in segments]
    return " ".join(text_parts).strip()


class STT:
    """Обёртка над Vosk. Один раз загружает модель, дальше feed'им аудио-чанки."""

    def __init__(self, model_path: Optional[str] = None) -> None:
        path = str(model_path or CONFIG.model_dir)
        log.info("Загружаю Vosk модель из %s ...", path)
        self._model = Model(path)
        self._rec: Optional[KaldiRecognizer] = None
        self.reset()

    def reset(self) -> None:
        """Новый сеанс распознавания (после wake word или после отправки)."""
        self._rec = KaldiRecognizer(self._model, CONFIG.sample_rate)
        # Подсказки по грамматике делают wake-word точнее, но и ломают
        # свободные команды. Используем открытый словарь.
        self._rec.SetWords(True)

    def accept_waveform(self, data: bytes) -> str:
        """Скормить PCM-чанк. Вернуть готовый текст, если Vosk закрыл сегмент, иначе ''."""
        if self._rec is None:
            self.reset()
        assert self._rec is not None
        if self._rec.AcceptWaveform(data):
            return json.loads(self._rec.Result()).get("text", "")
        return ""

    def partial(self) -> str:
        if self._rec is None:
            return ""
        try:
            return json.loads(self._rec.PartialResult()).get("partial", "")
        except Exception:  # noqa: BLE001
            return ""

    def final(self) -> str:
        if self._rec is None:
            return ""
        text = json.loads(self._rec.FinalResult()).get("text", "")
        self.reset()
        return text


def contains_wake_word(text: str, wake: Optional[str] = None) -> bool:
    """Детектор wake-word: ищем слово целиком, а не подстроку.

    Защищаемся от ложных срабатываний на 'мгермес', 'аннгермес' и т.п.
    Word boundary = граница слова, найденная re. Также принимаем начало
    строки и позицию после цифры/буквы как границу — Vosk часто выдаёт
    слитный текст без пробелов, и жёсткий \b не справляется.
    """
    if not text:
        return False
    needle = (wake or CONFIG.wake_word).lower().strip()
    if not needle:
        return False
    # Надёжная проверка word boundary через regex
    pattern = rf'(?<!\w){re.escape(needle)}(?!\w)'
    return bool(re.search(pattern, text, re.IGNORECASE))
