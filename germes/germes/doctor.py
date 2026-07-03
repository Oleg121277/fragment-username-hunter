"""Утилита диагностики: модель на месте, микрофон доступен, Hermes вызывается."""
from __future__ import annotations

import logging
import sys

import sounddevice as sd

from . import hermes_client
from .audio import list_input_devices
from .config import CONFIG
from .stt import STT

log = logging.getLogger("germes.doctor")


def main() -> int:
    print("== Germes doctor ==\n")

    # 1. Модель
    if not CONFIG.model_dir.exists():
        print(f"[✗] Vosk модель не найдена: {CONFIG.model_dir}")
        print("    Скачайте и распакуйте в эту папку либо укажите GERMES_MODEL_DIR.")
        return 1
    print(f"[✓] Vosk модель: {CONFIG.model_dir}")

    # 2. Микрофон
    try:
        print("\nДоступные устройства ввода:")
        list_input_devices()
        with sd.RawInputStream(
            samplerate=CONFIG.sample_rate,
            channels=1,
            dtype="int16",
            device=CONFIG.input_device,
            blocksize=CONFIG.block_size,
        ) as _:
            print(f"[✓] Микрофон открыт (rate={CONFIG.sample_rate}).")
    except Exception as exc:  # noqa: BLE001
        print(f"[✗] Микрофон недоступен: {exc}")
        return 1

    # 3. STT init
    try:
        STT()
        print("[✓] Vosk модель инициализирована.")
    except Exception as exc:  # noqa: BLE001
        print(f"[✗] Не удалось инициализировать Vosk: {exc}")
        return 1

    # 4. Hermes
    print("\nПробую вызвать Hermes...")
    ans = hermes_client.ask("Скажи 'ок' если ты меня слышишь", timeout=60)
    print(f"[✓] Hermes ответил: {ans!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
