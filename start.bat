@echo off
cd /d "%~dp0"

:: Kill old processes silently
taskkill /f /im uvicorn.exe >nul 2>&1
:: Kill any python process still listening on port 8001 (backend)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8001 " ^| findstr "LISTENING" 2^>nul') do (
  taskkill /f /pid %%P >nul 2>&1
)
taskkill /f /im node.exe >nul 2>&1

:: Launch backend hidden via PowerShell
start /B powershell -WindowStyle Hidden -Command "uvicorn backend.main:app --reload --port 8001"

:: Wait for backend readiness (silent)
:wait
>nul 2>&1 powershell -Command "try{$c=New-Object System.Net.Sockets.TcpClient; $c.Connect('127.0.0.1',8001); $c.Close(); exit 0} catch{exit 1}" && goto :frontend
>nul 2>&1 timeout /t 1
goto :wait

:frontend
:: Launch frontend hidden via PowerShell
start /B powershell -WindowStyle Hidden -Command "cd frontend; npm run dev"

:: Exit this batch window immediately
exit
