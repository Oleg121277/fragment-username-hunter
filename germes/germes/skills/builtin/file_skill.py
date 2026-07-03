"""Built-in skill: Работа с файлами (поиск, чтение, список)."""
from __future__ import annotations

import os
from pathlib import Path

from germes.skills import BuiltinSkill, SkillResult, SkillRegistry


class FileSkill(BuiltinSkill):
    keywords = ("файл", "папка", "директория", "найди", "покажи", "прочитай", "создай", "удали")
    patterns = (r"\b(найди|покажи|прочитай)\b.*\b(файл|папку)\b", r"\b(создай|удали)\b.*\b(файл|папку)\b")

    def can_handle(self, text: str) -> bool:
        return self._match_keywords(text) or self._match_patterns(text)

    def run(self, text: str, **ctx) -> SkillResult:
        low = text.lower()
        cwd = Path.cwd()

        # Список файлов
        if any(w in low for w in ("список", "покажи", "что есть", "файлы")):
            files = list(cwd.iterdir())[:20]
            if not files:
                return SkillResult(text="Папка пуста.")
            lines = [f"{'📁' if f.is_dir() else '📄'} {f.name}" for f in files]
            return SkillResult(text="Файлы в " + str(cwd) + ":\n" + "\n".join(lines))

        # Поиск
        if "найди" in low or "поиск" in low:
            # Пытаемся вытащить запрос
            import re
            m = re.search(r"(?:найди|поиск)\s+(.+)", low)
            query = m.group(1).strip() if m else ""
            if not query:
                return SkillResult(text="Что искать? Скажи: «найди файл с именем...»")
            matches = []
            for root, dirs, files in os.walk(cwd):
                for name in files + dirs:
                    if query.lower() in name.lower():
                        matches.append(Path(root) / name)
                if len(matches) > 30:
                    break
            if not matches:
                return SkillResult(text=f"Ничего не найдено по '{query}'.")
            lines = [str(p.relative_to(cwd)) for p in matches[:15]]
            return SkillResult(text=f"Найдено {len(matches)}:\n" + "\n".join(lines))

        return SkillResult(text="Не поняла команду про файлы. Попробуй: «покажи файлы» или «найди ...»")


def register(registry: SkillRegistry) -> None:
    registry.register(FileSkill(registry))