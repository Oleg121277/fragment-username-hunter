"""Built-in skill: Текущее время и дата."""
from __future__ import annotations

from datetime import datetime

from germes.skills import BuiltinSkill, SkillResult, SkillRegistry


class TimeSkill(BuiltinSkill):
    keywords = ("время", "который час", "сколько времени", "дата", "число", "день недели")
    patterns = (r"\b(сколько|который)\s+(времени|час)", r"\b(какое|какая)\s+(число|дата)")

    def can_handle(self, text: str) -> bool:
        return self._match_keywords(text) or self._match_patterns(text)

    def run(self, text: str, **ctx) -> SkillResult:
        now = datetime.now()
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%d.%m.%Y (%A)")
        weekdays = {
            "Monday": "понедельник", "Tuesday": "вторник", "Wednesday": "среда",
            "Thursday": "четверг", "Friday": "пятница", "Saturday": "суббота", "Sunday": "воскресенье"
        }
        for en, ru in weekdays.items():
            date_str = date_str.replace(en, ru)
        return SkillResult(text=f"Сейчас {time_str}, {date_str}.")


def register(registry: SkillRegistry) -> None:
    registry.register(TimeSkill(registry))