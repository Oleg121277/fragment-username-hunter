@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
REM Запуск Germes. Использует .venv311 (Python 3.11), т.к. pygame/sounddevice
REM не имеют wheels под 3.14. Создаёт venv при первом запуске.
setlocal
cd /d %~dp0

set "VENV_DIR=.venv311"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "LOG_FILE=%~dp0germes.log"

REM Дублируем stdout/stderr в файл для последующего просмотра
if not exist "%LOG_FILE%" type nul > "%LOG_FILE%"
echo. >> "%LOG_FILE%"
echo ===== %DATE% %TIME% ===== >> "%LOG_FILE%"

call :log "Germes start"
call :log "CWD: %CD%"

REM Создаём venv на 3.11, если ещё нет
if not exist "%VENV_PY%" (
  call :log "Создаю venv 3.11..."
  where py >nul 2>&1
  if %errorlevel%==0 (
    call :log "Использую py -3.11"
    py -3.11 -m venv "%VENV_DIR%" || (
      call :log "py -3.11 провалился, пробую прямой путь"
      if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" -m venv "%VENV_DIR%" || (
          call :log "Не удалось создать venv. Поставь Python 3.11 вручную."
          goto :err
        )
      ) else (
        call :log "Python 3.11 не найден. Установи python.org/downloads/release/python-3119/"
        goto :err
      )
    )
  ) else (
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
      "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" -m venv "%VENV_DIR%" || (
        call :log "Не удалось создать venv."
        goto :err
      )
    ) else (
      call :log "Python 3.11 не найден."
      goto :err
    )
  )
)

if not exist "%VENV_PY%" (
  call :log "python.exe не найден в %VENV_DIR%"
  goto :err
)

REM Установить зависимости, если чего-то не хватает
"%VENV_PY%" -c "import vosk, sounddevice, pygame, edge_tts" >nul 2>&1
if errorlevel 1 (
  call :log "Ставлю зависимости..."
  "%VENV_PY%" -m pip install -U pip >> "%LOG_FILE%" 2>&1
  "%VENV_PY%" -m pip install -r requirements.txt >> "%LOG_FILE%" 2>&1
  if errorlevel 1 (
    call :log "pip install провалился — смотри %LOG_FILE%"
    goto :err
  )
)

REM Проверяем модель
if not exist "models\vosk-model-small-ru-0.22\conf" (
  call :log "Vosk модель не найдена в models\vosk-model-small-ru-0.22"
  call :log "Скачай https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
  call :log "и распакуй в models\"
  goto :err
)

call :log "Запускаю Germes..."
call :log "Скажи 'Гермес, привет'. Для выхода — Ctrl+C."
"%VENV_PY%" -m germes %*
set RC=%ERRORLEVEL%
call :log "Germes завершилась с кодом %RC%"
if not "%RC%"=="0" goto :err
exit /b %RC%

:err
echo.
echo ============================================
echo  Germes остановилась с ошибкой. Лог: %LOG_FILE%
echo ============================================
echo.
pause
exit /b 1

:log
echo [%TIME%] %~1
echo [%TIME%] %~1 >> "%LOG_FILE%"
goto :eof
