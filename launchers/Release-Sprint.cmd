@echo off
REM AntiStallClaude - STOP (disarm) a sprint. Human-only.
REM Double-click this. Pick the project folder, then type your release passphrase in the
REM masked box. A wrong passphrase does nothing. The agent cannot do this for you.
setlocal
set "AS=%~dp0hooks\antistall.py"
if not exist "%AS%" set "AS=%USERPROFILE%\.claude\hooks\antistall.py"
if not exist "%AS%" (
  echo Could not find antistall.py. Install AntiStall first ^(install.py --global^), then re-run.
  pause
  exit /b 1
)
set "PYW="
for %%P in (pythonw.exe) do if not defined PYW set "PYW=%%~$PATH:P"
if defined PYW (
  start "" "%PYW%" "%AS%" release --all
) else (
  python3 "%AS%" release --all
)
exit /b 0
