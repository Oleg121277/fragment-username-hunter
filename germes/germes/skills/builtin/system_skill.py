"""Built-in skill: Системная информация (CPU, RAM, диск, батарея)."""
from __future__ import annotations

import platform
import shutil

import psutil

from germes.skills import BuiltinSkill, SkillResult, SkillRegistry


class SystemSkill(BuiltinSkill):
    keywords = ("система", "процессор", "память", "оперативка", "оперативки", "диск", "батарея", "заряд", "нагрузка", "cpu", "ram")
    patterns = (r"\b(сколько|какая)\s+(память|оперативка|место|загрузка)", r"\b(статус|состояние)\s+системы")

    def can_handle(self, text: str) -> bool:
        return self._match_keywords(text) or self._match_patterns(text)

    def run(self, text: str, **ctx) -> SkillResult:
        low = text.lower()
        parts = []

        if any(w in low for w in ("процессор", "cpu", "нагрузк")):
            cpu = psutil.cpu_percent(interval=0.3)
            parts.append(f"CPU {cpu:.0f}%")

        if any(w in low for w in ("память", "оперативк", "ram", "памяти")):
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            parts.append(f"RAM {used_gb:.1f}/{total_gb:.1f} ГБ ({mem.percent:.0f}%)")

        if any(w in low for w in ("диск", "место", "диска", "свободн")):
            from pathlib import Path as _Path
            disk_path = str(_Path.home()) if platform.system() == "Windows" else "/"
            disk = shutil.disk_usage(disk_path)
            free_gb = disk.free / (1024**3)
            total_gb = disk.total / (1024**3)
            parts.append(f"Диск {free_gb:.0f}/{total_gb:.0f} ГБ свободно")

        if any(w in low for w in ("батаре", "заряд", "батарею")):
            try:
                bat = psutil.sensors_battery()
                if bat:
                    parts.append(f"Батарея {bat.percent:.0f}%{' заряжается' if bat.power_plugged else ''}")
                else:
                    parts.append("Батарея: нет данных")
            except Exception:
                parts.append("Батарея: недоступно")

        if not parts:
            # Общая сводка
            cpu = psutil.cpu_percent(interval=0.2)
            mem = psutil.virtual_memory()
            from pathlib import Path as _Path
            disk_path = str(_Path.home()) if platform.system() == "Windows" else "/"
            disk = shutil.disk_usage(disk_path)
            try:
                bat = psutil.sensors_battery()
                bat_str = f", батарея {bat.percent:.0f}%" if bat else ""
            except Exception:
                bat_str = ""
            parts.append(
                f"CPU {cpu:.0f}%, RAM {mem.percent:.0f}%, "
                f"диск {disk.free/(1024**3):.0f}/{disk.total/(1024**3):.0f} ГБ{bat_str}"
            )

        return SkillResult(text="; ".join(parts) + ".")


def register(registry: SkillRegistry) -> None:
    registry.register(SystemSkill(registry))