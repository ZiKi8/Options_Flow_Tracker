@echo off
cd /d "%~dp0"
python collector.py --snapshot EOD >> collector.log 2>&1
