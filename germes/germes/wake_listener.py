"""WakeWordListener — лёгкий поток, который крутится в фоне и слушает
partial-результаты Vosk. Не нагружает CPU: только partial, никакого accept_waveform.

Использует глобальный AudioStream для получения аудио.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Callable, Optional

from vosk import KaldiRecognizer, SetLogLevel

from .audio import AUDIO_STREAM
from .config import CONFIG
from .stt import contains_wake_word

log = logging.getLogger("germes.wake_listener")

# Убираем спам Vosk
SetLogLevel(-1)


class WakeWordListener:
    """Фоновый слушатель wake word."""

    def __init__(
        self,
        on_wake: Callable[[], None],
        model,
        wake_word: Optional[str] = None,
    ) -> None:
        self._on_wake = on_wake
        self._model = model
        self._wake_word = wake_word or CONFIG.wake_word
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._rec: Optional[KaldiRecognizer] = None
        self._last_wake = 0.0
        self._cooldown = CONFIG.wake_cooldown_sec

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._rec = KaldiRecognizer(self._model, CONFIG.sample_rate)
        self._rec.SetWords(True)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="WakeWordListener", daemon=True)
        self._thread.start()
        log.info("WakeWordListener started (wake='%s')", self._wake_word)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        log.info("WakeWordListener stopped")

    def _run(self) -> None:
        audio_q = AUDIO_STREAM.get_queue()
        while not self._stop.is_set():
            try:
                data = audio_q.get(timeout=0.2)
            except queue.Empty:
                continue

            # Проверяем и final (AcceptWaveform=True), и partial
            text = ""
            if self._rec.AcceptWaveform(data):
                try:
                    text = json.loads(self._rec.Result()).get("text", "")
                except Exception:  # noqa: BLE001
                    text = ""
            else:
                try:
                    text = json.loads(self._rec.PartialResult()).get("partial", "")
                except Exception:  # noqa: BLE001
                    text = ""

            if text and contains_wake_word(text, self._wake_word):
                now = time.monotonic()
                if now - self._last_wake > self._cooldown:
                    self._last_wake = now
                    log.info("Wake word detected in partial: %s", text)
                    self._on_wake()
                    # После срабатывания сбрасываем recognizer, чтобы не сработать дважды
                    self._rec = KaldiRecognizer(self._model, CONFIG.sample_rate)
                    self._rec.SetWords(True)