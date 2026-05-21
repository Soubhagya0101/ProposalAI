@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\ksoub\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
set "PROPOSALAI_GOOGLE_SHEET_ID=1m2syNh-oDujGYPVo-Fd3-ZFPJFy6wJmruH9moKYA-88"

echo Starting ProposalAI revenue ops...
"%PYTHON_EXE%" -m revenue_ops init
"%PYTHON_EXE%" -m revenue_ops daily

start "" "http://127.0.0.1:8765"
"%PYTHON_EXE%" -m revenue_ops dashboard
