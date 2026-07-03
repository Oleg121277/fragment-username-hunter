"""Built-in skill: Память (запоминание фактов).
Формат: 'Гермес, запомни: мой любимый цвет — красный' → сохранит в memory.json
'Гермес, вспомни цвет' → прочитает и озвучит."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from germes.skills import BuiltinSkill, SkillResult, SkillRegistry
from germes.config import CONFIG

MEMORY_FILE = CONFIG.project_root / "memory.json"


class MemorySkill(BuiltinSkill):
    keywords = ("запомни", "вспомни", "помни", "помню", "запомню")

    def can_handle(self, text: str) -> bool:
        low = text.lower()
        return any(kw in low for kw in self.keywords)

    def run(self, text: str, **ctx) -> SkillResult:
        low = text.lower()

        # Запомнить
        m = re.search(r"(?:запомни|запомню|помни)\s*[:\s\-]?\s*(.+)", low)
        if m:
            fact = m.group(1).strip(" .,:;")
            if not fact:
                return SkillResult(text="Что запомнить?")
            memory = self._load()
            key = re.sub(r"[^а-яё]+", "_", fact.lower())[:32] or str(len(memory))
            memory[key] = {"fact": fact, "saved": datetime.now().isoformat()}
            self._save(memory)
            return SkillResult(text=f"Запомнила: {fact}")

        # Вспомнить
        m = re.search(r"(?:вспомни|помню|напомни)\s+(.+)", low)
        if m:
            query = m.group(1).strip(" .,:;")
            memory = self._load()
            # Простая фильтрация по ключу/факту
            matches = [v["fact"] for k, v in memory.items() if query in k or query in v.get("fact", "")]
            if not matches:
                return SkillResult(text="Ничего не запоминала.")
            return SkillResult(text="Вспомнила: " + "; ".join(matches[:3]))

        return SkillResult(text="Скажи: «Гермес, запомни: ...» или «Гермес, вспомни про ...»")

    def _load(self) -> dict:
        if MEMORY_FILE.exists():
            try:
                return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save(self, data: dict) -> None:
        MEMORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def register(registry: SkillRegistry) -> None:
    registry.register(MemorySkill(registry))