"""Поток аудио с микрофона. Общий продюсер — одна очередь для wake-listener и command-capture."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Iterator, Optional

import numpy as np
import sounddevice as sd

from .config import CONFIG

log = logging.getLogger("germes.audio")


def list_input_devices() -> None:
    """Напечатать доступные устройства ввода — удобно для отладки."""
    print(sd.query_devices())


class AudioStream:
    """
    Единый аудио-продюсер: открывает микрофон, кладёт PCM-блоки в общую очередь.
    Потребители (WakeWordListener, CommandCapture) забирают оттуда.
    """

    def __init__(self) -> None:
        self._stream: Optional[sd.RawInputStream] = None
        self._queue: "queue.Queue[bytes]" = queue.Queue(maxsize=100)
        self._callback = self._make_callback()
        self._running = False

    def _make_callback(self):
        def _cb(indata, frames, time, status):
            if status:
                log.debug("sounddevice status: %s", status)
            try:
                self._queue.put_nowait(bytes(indata))
            except queue.Full:
                pass  # дропаем старый, если не успевают забирать
        return _cb

    def start(self) -> None:
        if self._running:
            return
        try:
            self._stream = sd.RawInputStream(
                samplerate=CONFIG.sample_rate,
                blocksize=CONFIG.block_size,
                dtype="int16",
                channels=1,
                device=CONFIG.input_device,
                callback=self._callback,
            )
            self._stream.start()
        except sd.PortAudioError as exc:
            log.error(
                "Не удалось открыть микрофон: %s. Запустите `python -m germes doctor` для диагностики.",
                exc,
            )
            raise
        self._running = True
        log.info("AudioStream started (sr=%d, block=%d)", CONFIG.sample_rate, CONFIG.block_size)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        # Очистить очередь
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        log.info("AudioStream stopped")

    def get_block(self, timeout: float = 0.2) -> Optional[bytes]:
        """Взять блок из очереди (блокирующе)."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_queue(self) -> "queue.Queue[bytes]":
        """Получить ссылку на очередь для внешних потребителей."""
        return self._queue

    @property
    def is_running(self) -> bool:
        return self._running


# Глобальный синглтон для простоты (можно заменить на DI)
AUDIO_STREAM = AudioStream()