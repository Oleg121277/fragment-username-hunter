"""Главный цикл Germes v2 — два потока:
1. WakeWordListener — ловит wake word в фоне (partial-only, быстрый)
2. CommandProcessor — обрабатывает команды: локальные навыки → Hermes → TTS

Аудио: общий AudioStream (callback -> очередь) для обоих потребителей.
"""
from __future__ import annotations

import logging
import queue
import signal
import sys
import threading
import time

import numpy as np

from .audio import AUDIO_STREAM
from .cmd_processor import PROCESSOR
from .config import CONFIG
from .stt import STT
from .tts import speak
from .wake_listener import WakeWordListener

log = logging.getLogger("germes.main")


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, CONFIG.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _rms(data: bytes) -> float:
    arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    if not arr.size:
        return 0.0
    return float(np.sqrt(np.mean(arr * arr)))


class Germes:
    def __init__(self) -> None:
        self._stt = STT()
        self._wake_listener: WakeWordListener | None = None
        self._stop = threading.Event()
        self._capturing = False  # флаг: сейчас захватываем команду после wake

    def _on_wake(self) -> None:
        """Callback от WakeWordListener: начать захват команды."""
        if self._capturing:
            log.debug("Wake while already capturing, ignoring")
            return
        log.info("🔔 Wake callback triggered")
        self._capturing = True
        # TTS: "Слушаю"
        speak("Слушаю.")
        # Запускаем захват в отдельном потоке, чтобы не блокировать wake-listener
        threading.Thread(target=self._capture_and_submit, name="CommandCapture", daemon=True).start()

    def _capture_and_submit(self) -> None:
        """Полноценный STT захват команды после wake word."""
        try:
            cmd = self._capture_command()
            if cmd:
                PROCESSOR.submit(cmd)
        finally:
            self._capturing = False
            # Сбрасываем wake-listener recognizer
            if self._wake_listener:
                from vosk import KaldiRecognizer
                self._wake_listener._rec = KaldiRecognizer(self._stt._model, CONFIG.sample_rate)
                self._wake_listener._rec.SetWords(True)

    def _capture_command(self) -> str:
        """После wake word: слушаем полноценный STT пока не замолчат."""
        self._stt.reset()
        deadline = time.monotonic() + CONFIG.command_timeout
        last_voice = time.monotonic()
        accumulated: list[str] = []

        log.info("Слушаю команду…")
        while time.monotonic() < deadline and not self._stop.is_set():
            try:
                data = AUDIO_STREAM.get_block(timeout=0.2)
            except Exception:
                continue
            if data is None:
                continue

            text = self._stt.accept_waveform(data)
            if text:
                accumulated.append(text)
                log.debug("  + %s", text)

            if _rms(data) > CONFIG.rms_voice_threshold:
                last_voice = time.monotonic()

            if time.monotonic() - last_voice > CONFIG.silence_to_send and accumulated:
                break

        final = self._stt.final()
        if final:
            accumulated.append(final)

        command = " ".join(accumulated).strip()
        if not command:
            speak("Не расслышала.")
            return ""

        # Убираем само wake word из команды
        wake = CONFIG.wake_word
        if command.lower().startswith(wake):
            command = command[len(wake):].strip(" ,.-")

        log.info("Command captured: %s", command)
        return command

    def start(self) -> int:
        _setup_logging()
        log.info("Germes v2 запускается. Wake word: «%s»", CONFIG.wake_word)

        # Запускаем аудио
        AUDIO_STREAM.start()

        # Запускаем WakeWordListener
        self._wake_listener = WakeWordListener(
            on_wake=self._on_wake,
            model=self._stt._model,
        )
        self._wake_listener.start()

        # Запускаем CommandProcessor
        PROCESSOR.start()

        # Главный цикл: просто держим процесс живым, сигналы обрабатываем
        try:
            while not self._stop.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            log.info("Пока!")
        finally:
            self.stop()
        return 0

    def stop(self) -> None:
        self._stop.set()
        if self._wake_listener:
            self._wake_listener.stop()
        PROCESSOR.stop()
        AUDIO_STREAM.stop()


def run() -> int:
    def _sigint(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGINT, _sigint)
    signal.signal(signal.SIGTERM, _sigint)

    app = Germes()
    return app.start()


if __name__ == "__main__":
    sys.exit(run())