@echo off
setlocal

set PORT=31031
echo [stop] stopping processes listening on port %PORT% ...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%PORT% ^| findstr LISTENING') do (
  echo [stop] taskkill /PID %%a /F
  taskkill /PID %%a /F >nul 2>nul
)

echo [stop] done

