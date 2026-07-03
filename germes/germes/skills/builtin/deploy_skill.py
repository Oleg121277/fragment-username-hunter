"""Built-in skill: Деплой файла на GitHub Pages по команде 'деплой в гитхаб'."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from germes.skills import BuiltinSkill, SkillResult, SkillRegistry

# Путь к скрипту деплоя
DEPLOY_SCRIPT = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "deploy_to_github_pages.py"


class DeploySkill(BuiltinSkill):
    keywords = ("деплой", "deploy", "гитхаб", "github", "pages", "загрузи на")
    patterns = (
        r"\b(деплой|deploy)\b.*\b(гитхаб|github|pages)\b",
        r"\b(загрузи|отправь)\b.*\b(на\s+)?(гитхаб|github)\b",
    )

    def can_handle(self, text: str) -> bool:
        return self._match_keywords(text) or self._match_patterns(text)

    def run(self, text: str, **ctx) -> SkillResult:
        low = text.lower()

        # Пытаемся извлечь путь к файлу из текста
        file_path = self._extract_file_path(text)

        if not file_path:
            # Проверяем контекст — возможно файл передан через ctx
            file_path = ctx.get("file_path") or ctx.get("attached_file")

        if not file_path:
            return SkillResult(
                text="Какой файл задеплоить? Назови путь или прикрепи файл.",
                continue_listening=True,
            )

        fp = Path(file_path).resolve()
        if not fp.exists():
            return SkillResult(text=f"Файл не найден: {fp}")

        # Извлекаем имя репо если указано
        repo_match = re.search(r"(?:в|as|как)\s+(\S+)", low)
        repo_name = repo_match.group(1) if repo_match else None

        cmd = [sys.executable, str(DEPLOY_SCRIPT), str(fp)]
        if repo_name:
            cmd.append(repo_name)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            output = result.stdout + result.stderr

            # Ищем URL в выводе
            url_match = re.search(r"(https://\S+\.github\.io/\S+)", output)
            if url_match:
                url = url_match.group(1).rstrip("/")
                return SkillResult(text=f"Готово! Сайт доступен: {url}")

            if result.returncode != 0:
                return SkillResult(text=f"Ошибка деплоя: {output[-300:]}")

            return SkillResult(text=f"Деплой завершён. Вывод: {output[-200:]}")

        except subprocess.TimeoutExpired:
            return SkillResult(text="Деплой занял слишком много времени (>3 мин).")
        except Exception as e:
            return SkillResult(text=f"Ошибка: {e}")

    @staticmethod
    def _extract_file_path(text: str) -> str | None:
        """Пытаемся вытащить путь к файлу из текста команды."""
        # Ищем quoted path
        m = re.search(r'["\']([^"\']+\.(?:html?|css|js|txt|md))["\']', text, re.I)
        if m:
            return m.group(1)

        # Ищем unquoted path с расширением
        m = re.search(r'([\w./\\:-]+\.(?:html?|css|js|txt|md))\b', text, re.I)
        if m:
            candidate = m.group(1)
            if Path(candidate).exists():
                return candidate

        return None


def register(registry: SkillRegistry) -> None:
    registry.register(DeploySkill(registry))
