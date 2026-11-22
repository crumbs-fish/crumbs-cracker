@echo off
setlocal
set "HERE=%~dp0"
where py >nul 2>nul
if not errorlevel 1 goto use_py
python "%HERE%crumbs_cracker.py" %*
exit /b %errorlevel%

:use_py
py -3 "%HERE%crumbs_cracker.py" %*
exit /b %errorlevel%
