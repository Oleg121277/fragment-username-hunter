"""Базовые классы и реестр навыков (skills) для Germes.

Архитектура:
- Skill: базовый класс навыка, может быть синхронным или асинхронным.
- SkillRegistry: хранит навыки, умеет искать по intent/ключевым словам,
  кэширует результаты Hermes, умеет автосоздавать навык через Hermes.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from germes.config import CONFIG
from germes.hermes_client import ask

log = logging.getLogger("germes.skills")


@dataclass
class SkillResult:
    """Результат выполнения навыка."""
    text: str                 # что сказать пользователю
    data: Any = None          # доп. данные (для UI, логов и т.п.)
    continue_listening: bool = False  # ждать продолжение диалога


class Skill(ABC):
    """Базовый класс навыка. Наследники должны реализовать can_handle и run."""

    # Ключевые слова/фразы, по которым навык может сработать (для быстрого префильтра)
    keywords: tuple[str, ...] = ()
    # Регулярки для более точного 매칭 (опционально)
    patterns: tuple[str, ...] = ()
    # Приоритет: выше — важнее. built-in = 100, автосозданные = 10
    priority: int = 50
    # Требует ли интернет (для отсечения в офлайне)
    needs_net: bool = False

    def __init__(self, registry: Optional["SkillRegistry"] = None) -> None:
        self.registry = registry

    @abstractmethod
    def can_handle(self, text: str) -> bool:
        """Быстрая проверка: может ли навык обработать этот текст?"""

    @abstractmethod
    def run(self, text: str, **ctx) -> SkillResult:
        """Синхронное выполнение. Для асинхронных — используй AsyncSkill."""

    # Удобный хелпер для patterns
    def _match_patterns(self, text: str) -> bool:
        if not self.patterns:
            return False
        low = text.lower()
        return any(re.search(p, low) for p in self.patterns)

    def _match_keywords(self, text: str) -> bool:
        if not self.keywords:
            return False
        low = text.lower()
        return any(kw in low for kw in self.keywords)


class AsyncSkill(Skill):
    """Асинхронный навык (для сетевых запросов и т.п.)."""

    @abstractmethod
    async def arun(self, text: str, **ctx) -> SkillResult:
        pass

    def run(self, text: str, **ctx) -> SkillResult:
        return asyncio.run(self.arun(text, **ctx))


class BuiltinSkill(Skill):
    """Маркер для встроенных навыков — они всегда загружаются первыми."""
    priority: int = 100


@dataclass
class SkillCacheEntry:
    skill_code: str
    created_at: float
    hits: int = 0


class SkillRegistry:
    """Реестр навыков: загрузка built-in, дискавери files, кэш, автосоздание."""

    def __init__(self) -> None:
        self._skills: list[Skill] = []
        self._cache: dict[str, SkillCacheEntry] = {}
        self._cache_file = CONFIG.skills_dir / "cache.json"
        self._loaded_builtin = False
        self._lock = asyncio.Lock() if asyncio else None
        self._ensure_dirs()
        self._load_cache()

    def _ensure_dirs(self) -> None:
        CONFIG.skills_dir.mkdir(parents=True, exist_ok=True)
        (CONFIG.skills_dir / "builtin").mkdir(exist_ok=True)
        (CONFIG.skills_dir / "auto").mkdir(exist_ok=True)

    def _load_cache(self) -> None:
        if self._cache_file.exists():
            try:
                data = json.loads(self._cache_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    self._cache[k] = SkillCacheEntry(**v)
            except Exception as exc:  # noqa: BLE001
                log.warning("Не удалось прочитать кэш скиллов: %s", exc)

    def _save_cache(self) -> None:
        try:
            data = {k: v.__dict__ for k, v in self._cache.items()}
            self._cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("Не удалось сохранить кэш скиллов: %s", exc)

    def register(self, skill: Skill) -> None:
        """Добавить навык в реестр (сортировка по priority desc)."""
        self._skills.append(skill)
        self._skills.sort(key=lambda s: s.priority, reverse=True)

    def load_builtin(self) -> None:
        """Загрузить встроенные навыки из skills/builtin/*.py."""
        if self._loaded_builtin:
            return
        builtin_dir = CONFIG.skills_dir / "builtin"
        if not builtin_dir.exists():
            return
        for py_file in builtin_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"germes.skills.builtin.{py_file.stem}", py_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                # Ожидаем, что модуль экспортирует класс SkillClass или register()
                if hasattr(module, "register"):
                    module.register(self)
                elif hasattr(module, "SkillClass"):
                    self.register(module.SkillClass(self))
                log.info("Загружен builtin skill: %s", py_file.stem)
            except Exception as exc:  # noqa: BLE001
                log.error("Ошибка загрузки builtin %s: %s", py_file, exc)
        self._loaded_builtin = True

    def find_skill(self, text: str) -> Optional[Skill]:
        """Найти подходящий навык (быстрый проход по keywords/patterns)."""
        self.load_builtin()
        for skill in self._skills:
            if skill.can_handle(text):
                log.debug("Skill matched: %s for '%s'", skill.__class__.__name__, text)
                return skill
        return None

    async def get_or_create_skill(self, intent: str, text: str) -> Optional[Skill]:
        """Получить навык из кэша или автосоздать через Hermes."""
        cache_key = hashlib.sha256(f"{intent}:{text}".encode()).hexdigest()[:16]

        # Проверка кэша
        entry = self._cache.get(cache_key)
        if entry is not None:
            if time.time() - entry.created_at < CONFIG.skill_cache_ttl_sec:
                entry.hits += 1
                self._save_cache()
                # TODO: десериализовать код и вернуть skill — пока возвращаем None
                # (нужен динамический импорт/экзекьют кода)
                return None

        if not CONFIG.auto_create_skills:
            return None

        # Автосоздание через Hermes
        log.info("Автосоздание навыка для: %s", text)
        prompt = (
            "Ты — генератор навыков для голосового ассистента Germes (Python). "
            "Пользователь сказал: '{text}'. Намерение: '{intent}'. "
            "Напиши класс навыка, наследуясь от germes.skills.Skill. "
            "Только код класса, без лишних слов. Используй keywords/patterns для быстрого матчинга. "
            "Метод run(text, **ctx) -> SkillResult(text='...')."
        ).format(text=text, intent=intent)

        try:
            code = ask(prompt, timeout=CONFIG.brain_timeout)
            if not code or len(code) < 50:
                return None

            # Сохраняем в кэш
            self._cache[cache_key] = SkillCacheEntry(
                skill_code=code,
                created_at=time.time(),
            )
            self._save_cache()

            # Динамическая загрузка (упрощённо — exec в изолированном namespace)
            # В продакшене лучше отдельный процесс/подпроцесс.
            namespace = {"Skill": Skill, "SkillResult": SkillResult, "re": re}
            exec(code, namespace)
            for obj in namespace.values():
                if isinstance(obj, type) and issubclass(obj, Skill) and obj is not Skill:
                    skill = obj(self)
                    self.register(skill)
                    log.info("Автосоздан и зарегистрирован навык: %s", obj.__name__)
                    return skill
        except Exception as exc:  # noqa: BLE001
            log.error("Автосоздание навыка провалилось: %s", exc)
        return None

    def list_skills(self) -> list[str]:
        return [s.__class__.__name__ for s in self._skills]


# Глобальный реестр
REGISTRY = SkillRegistry()