"""Command Processor — обрабатывает команды после wake word.
- Очередь команд (deduplication по тексту + времени)
- Сначала ищет локальный навык (SkillRegistry)
- Если нет — фоллбек на Hermes
- Кэширует ответы Hermes для повторных запросов
- Управляет TTS (не даёт говорить дважды одновременно)"""
from __future__ import annotations

import hashlib
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import CONFIG
from .hermes_client import ask
from .skills import REGISTRY, SkillResult
from .tool_executor import process_response
from .tts import speak

log = logging.getLogger("germes.cmd_processor")


@dataclass
class Command:
    text: str
    timestamp: float = field(default_factory=time.monotonic)
    dedup_key: str = field(init=False)

    def __post_init__(self) -> None:
        # Ключ дедупа: нормализованный текст + окно времени
        norm = self.text.lower().strip(" ,.!?")
        self.dedup_key = hashlib.md5(norm.encode()).hexdigest()[:12]


class CommandProcessor:
    """
    Поток обработки команд:
    - Принимает команды из внешнего вызова (on_command)
    - Дедуплицирует (если та же команда пришла < 2 сек назад — игнор)
    - Пробует локальные навыки (REGISTRY)
    - Фоллбек на Hermes
    - TTS с защитой от одновременного воспроизведения
    """

    def __init__(self) -> None:
        self._queue: "queue.Queue[Command]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_spoken: dict[str, float] = {}  # dedup_key -> timestamp
        self._dedup_window = 2.0  # сек
        self._tts_lock = threading.Lock()
        self._speaking = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="CommandProcessor", daemon=True)
        self._thread.start()
        log.info("CommandProcessor started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        log.info("CommandProcessor stopped")

    def submit(self, text: str) -> bool:
        """Добавить команду в очередь. Вернёт False, если задедуплицировано."""
        cmd = Command(text=text)
        now = time.monotonic()

        # Dedup: если та же команда была совсем недавно — дроп
        last = self._last_spoken.get(cmd.dedup_key, 0)
        if now - last < self._dedup_window:
            log.debug("Dedup: drop '%s' (last %.1fs ago)", text, now - last)
            return False

        self._queue.put(cmd)
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                cmd = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            self._process_command(cmd)

    def _process_command(self, cmd: Command) -> None:
        text = cmd.text
        log.info("🎯 Processing command: %s", text)

        # 1. Попытка локального навыка
        skill = REGISTRY.find_skill(text)
        if skill:
            log.info("  -> Local skill: %s", skill.__class__.__name__)
            try:
                result = skill.run(text)
                self._speak_result(result)
                self._last_spoken[cmd.dedup_key] = time.monotonic()
                return
            except Exception as exc:
                log.error("Skill %s failed: %s", skill.__class__.__name__, exc)
                # Падаем на фоллбек

        # 2. Фоллбек на Hermes
        log.info("  -> Hermes fallback")
        try:
            raw_answer = ask(text, timeout=CONFIG.brain_timeout)
            # Перехватчик: извлечь и выполнить tool_calls из ответа
            cleaned_answer, tool_results = process_response(raw_answer)
            if tool_results:
                log.info("  -> Executed %d tool(s)", len(tool_results))
                for tr in tool_results:
                    log.info("     [%s] exit=%s", tr["tool"], tr["result"]["exit_code"])
                # Если были инструменты — озвучиваем результат последнего или очищенный текст
                last_output = tool_results[-1]["result"].get("output", "")
                speak_text = cleaned_answer if cleaned_answer else last_output
            else:
                speak_text = cleaned_answer
            result = SkillResult(text=speak_text or "Готово.")
            self._speak_result(result)
        except Exception as exc:
            log.error("Hermes failed: %s", exc)
            self._speak_result(SkillResult(text="Извини, не получилось."))

        self._last_spoken[cmd.dedup_key] = time.monotonic()

    def _speak_result(self, result: SkillResult) -> None:
        """Озвучить результат с блокировкой (не две речи одновременно)."""
        if not result.text:
            return
        with self._tts_lock:
            if self._speaking:
                log.debug("TTS busy, waiting...")
            self._speaking = True
            try:
                speak(result.text)
            finally:
                self._speaking = False


# Глобальный процессор
PROCESSOR = CommandProcessor()