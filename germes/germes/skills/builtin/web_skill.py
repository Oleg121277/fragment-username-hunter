"""Built-in skill: Веб-поиск и быстрые ответы (через Hermes с toolset web)."""
from __future__ import annotations

from germes.skills import BuiltinSkill, SkillResult, SkillRegistry
from germes.hermes_client import ask


class WebSkill(BuiltinSkill):
    keywords = ("найди в интернете", "поищи", "гугл", "что такое", "кто такой", "википедия")
    patterns = (r"\b(найди|поищи|погугли)\s+в\s+(интернете|сети|веб)", r"^\s*что\s+такое\s+", r"^\s*кто\s+такой\s+")

    def can_handle(self, text: str) -> bool:
        return self._match_keywords(text) or self._match_patterns(text)

    def run(self, text: str, **ctx) -> SkillResult:
        # Делегируем Hermes с toolset web
        prompt = (
            "Ответь кратко (1-2 предложения) на русском. "
            "Если нужен поиск — используй инструмент web. Вопрос: "
        ) + text
        try:
            answer = ask(prompt, timeout=30)
            return SkillResult(text=answer)
        except Exception as exc:
            return SkillResult(text=f"Не удалось поискать: {exc}")


def register(registry: SkillRegistry) -> None:
    registry.register(WebSkill(registry))