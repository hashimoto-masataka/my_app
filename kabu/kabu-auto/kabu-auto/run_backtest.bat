@echo off
cd /d "%~dp0"
py run_backtest.py %*
pause
