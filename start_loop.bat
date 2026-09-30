@echo off
REM 每 30 分鐘掃描一次並在發現新貨/補貨時通知。
REM 直接關閉此視窗即停止。
cd /d "%~dp0"
python monitor.py --loop 30
pause
