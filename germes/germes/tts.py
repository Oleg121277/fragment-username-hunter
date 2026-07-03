"""Синтез речи через edge-tts + воспроизведение через pygame.

edge-tts бесплатен и не требует ключей, но работает только онлайн.
Если нужна полная офлайн-работа — замените на silero (см. README).
"""
from __future__ import annotations

import asyncio
import io
import logging
import tempfile
from pathlib import Path

import edge_tts
import pygame

from .config import CONFIG

log = logging.getLogger("germes.tts")
pygame.mixer.init()

# Переиспользуемый event loop, чтобы не создавать/уничтожать на каждый speak()
_loop = asyncio.new_event_loop()


async def _synthesize(text: str, voice: str, rate: str = "+0%") -> bytes:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def speak(text: str) -> None:
    if not text or not text.strip():
        return
    log.info("🔊 speak: %s", text)
    try:
        audio = _loop.run_until_complete(
            _synthesize(text, CONFIG.tts_voice, CONFIG.tts_rate)
        )
    except Exception as exc:  # noqa: BLE001
        log.error("TTS упал: %s", exc)
        return
    if not audio:
        log.warning("TTS вернул пустой ответ")
        return

    # pygame не любит BytesIO с seek — пишем в tmp-файл
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio)
        path = f.name
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
