@echo off
cd /d "%~dp0"
python collector.py --snapshot PREMARKET >> collector.log 2>&1
