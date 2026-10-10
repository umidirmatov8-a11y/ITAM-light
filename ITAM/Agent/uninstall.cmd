@echo off
rem Removes the ITAM agent from this computer.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Install-ITAMAgent.ps1" -Uninstall
exit /b %ERRORLEVEL%
