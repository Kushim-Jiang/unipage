@echo off
cd /d "%~dp0"

:: Kill old processes silently
taskkill /f /im uvicorn.exe >nul 2>&1
for /f "tokens=2 delims= " %%P in ('tasklist /fi "imagename eq python.exe" /fo list ^| findstr /B "PID:"' 2^>nul) do (
  tasklist /fi "pid eq %%P" /fo csv 2>nul | findstr /i "uvicorn" >nul && taskkill /f /pid %%P >nul 2>&1
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
