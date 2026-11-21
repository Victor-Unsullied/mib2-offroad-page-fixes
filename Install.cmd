@echo off
setlocal
pushd "%~dp0" || exit /b 1
py -3 -B install.py %*
set "installer_code=%errorlevel%"
popd
if "%~1"=="" pause
exit /b %installer_code%
