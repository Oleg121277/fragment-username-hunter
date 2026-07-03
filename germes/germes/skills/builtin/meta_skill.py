"""Built-in skill: Управление Germes (настройки, перезапуск, справка)."""
from __future__ import annotations

from germes.skills import BuiltinSkill, SkillResult, SkillRegistry
from germes import config


class MetaSkill(BuiltinSkill):
    keywords = ("помощь", "команды", "что умеешь", "настройки", "где", "лог", "лог файл", "перезапуск", "выключись", "стоп")
    patterns = (r"\b(что\s+ты\s+умеешь|список\s+команд|помощь)", r"\b(перезапусти|выключи|стоп)\b")

    def can_handle(self, text: str) -> bool:
        return self._match_keywords(text) or self._match_patterns(text)

    def run(self, text: str, **ctx) -> SkillResult:
        low = text.lower()

        if any(w in low for w in ("помощ", "команд", "умееш", "что\s+ты")):
            return SkillResult(text=(
                "Я умею: время и дата, системная инфа (CPU/RAM/диск/батарея), "
                "файлы и папки, поиск в интернете. "
                "Скажи «Гермес, помощь» для повторки. "
                "Настройки в .env: голос, модель, таймауты."
            ))

        if any(w in low for w in ("лог", "где", "лог файл")):
            log_path = config.CONFIG.model_dir.parent / "germes.log"
            return SkillResult(text=f"Лог тут: {log_path}")

        if any(w in low for w in ("перезапуст", "выключи", "стоп")):
            return SkillResult(text="Перезапускай через run.bat. Чтобы выключить — закрой окно.", continue_listening=False)

        return SkillResult(text="Не понял. Скажи «Гермес, помощь».")


def register(registry: SkillRegistry) -> None:
    registry.register(MetaSkill(registry))