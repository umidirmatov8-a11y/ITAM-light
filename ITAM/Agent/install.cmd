@echo off
rem ITAM agent installer. Parameters are optional: -ServerUrl http://itam:8080 -EnrollmentKey KEY
rem Without parameters the settings come from agent.config.json in this folder or from Group Policy.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Install-ITAMAgent.ps1" %*
exit /b %ERRORLEVEL%
