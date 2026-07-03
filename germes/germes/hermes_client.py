"""Клиент к Hermes Agent. Держим как thin wrapper над subprocess, чтобы
не зависеть от внутреннего API Hermes (он нестабильный)."""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import threading
from typing import Optional

from .config import CONFIG

log = logging.getLogger("germes.brain")


def ask(prompt: str, timeout: float = 120.0) -> str:
    """Отправить prompt в Hermes и вернуть финальный ответ как строку.

    Используем режим `-z` (zero-prompt) — Hermes выполнит один проход и напечатает
    ответ. Флаг -Q подавляет баннер/спиннер, чтобы остался только текст ответа.
    """
    if not prompt.strip():
        return ""

    # Передаём prompt через переменную окружения, чтобы избежать проблем
    # с экранированием кавычек и спецсимволов в Windows cmd/shell
    safe_prompt = prompt.strip()
    cmd_str = CONFIG.brain_cmd.format(prompt="{GERMES_PROMPT}")
    cmd = shlex.split(cmd_str, posix=False)
    # Заменяем плейсхолдер на реальное значение после split
    cmd = [c.replace("{GERMES_PROMPT}", safe_prompt) for c in cmd]
    log.info("→ Hermes: %s", prompt)
    log.debug("exec: %s", cmd)

    try:
        env = os.environ.copy()
        env["GERMES_PROMPT"] = safe_prompt
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except FileNotFoundError:
        log.error(
            "Hermes не найден в PATH. Установите его или поправьте GERMES_BRAIN_CMD в .env."
        )
        return "Извини, мозг сейчас недоступен."
    except subprocess.TimeoutExpired:
        log.warning("Hermes не ответил за %.0f сек", timeout)
        return "Думаю слишком долго, спроси ещё раз."

    if result.returncode != 0:
        log.warning("Hermes rc=%s stderr=%s", result.returncode, result.stderr[:300])
    out = (result.stdout or "").strip()
    if not out:
        return "Не поняла, можешь повторить?"
    log.info("← Hermes: %s", out[:200])
    return out
