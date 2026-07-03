# Germes — локальный голосовой агент (v2)

Локальный голосовой агент с Hermes Agent в роли мозгов + локальными навыками.
- Два потока: **WakeWordListener** (фон) + **CommandProcessor** (очередь)
- Latency wake word: < 100 мс
- Локальные скиллы обрабатываются мгновенно (время, система, файлы)
- Если нет скилла — фоллбек на Hermes, ответ через TTS

## Архитектура v2

```
микрофон
    ├─► AudioStream (продюсер)
    │      ├─► WakeWordListener (partial-only, <10% CPU)
    │      └─► CommandCapture (полный STT после wake)
    └─► CommandProcessor — скиллы → Hermes — TTS
```

## Built-in skills

| Навык | Триггеры | Описание |
|-------|----------|--------|
| TimeSkill | «часы», «время», «сколько время» | Читает время и дату |
| SystemSkill | «оперативка», «память», «нагрузка» | CPU, RAM, диск |
| FileSkill | «файлы», «папка», «найди», «покажи» | Работа с файлами |
| MetaSkill | «помощь», «список команд» | Справка |
| WebSkill | «что такое», «кто такой», «где находится» | Веб-поиск через Hermes |

## Запуск

```
run.bat   # Windows
./run.sh  # WSL / git-bash
# или
.venv311\Scripts\python -m germes
```

Окно консоли останется открытым. Скажи «Гермес, привет».

## Диагностика

```
.venv311\Scripts\python -m germes.doctor
```

Проверяет: микрофон, модель, зависимости, Hermes.