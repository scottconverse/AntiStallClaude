@echo off
REM AntiStallClaude - set the human RELEASE PASSPHRASE.
REM Double-click this. A masked password box appears; type your passphrase there.
REM Only a salted hash is stored - the agent never sees what you type. No CLI needed.
setlocal
set "AS=%~dp0hooks\antistall.py"
if not exist "%AS%" set "AS=%USERPROFILE%\.claude\hooks\antistall.py"
if not exist "%AS%" (
  echo Could not find antistall.py. Install AntiStall first ^(install.py --global^), then re-run.
  pause
  exit /b 1
)
REM Prefer pythonw.exe (windowless) so ONLY the password box shows - no console window.
set "PYW="
for %%P in (pythonw.exe) do if not defined PYW set "PYW=%%~$PATH:P"
if defined PYW (
  start "" "%PYW%" "%AS%" set-release-secret
) else (
  REM Fallback: python3 still pops the GUI dialog (a brief console may appear).
  python3 "%AS%" set-release-secret
)
exit /b 0
