@echo off
REM Ежедневная пакетная проверка вручную на Windows (Планировщик заданий).
REM В Docker используйте: python main.py --schedule (см. docker-compose / Dockerfile).
REM Поле "Рабочая папка" (Start in): каталог проекта ssl_checker.
setlocal
cd /d "%~dp0.."
uv run python main.py --batch
exit /b %ERRORLEVEL%
