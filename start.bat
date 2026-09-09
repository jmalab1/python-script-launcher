@echo off
if not exist dist\launchctl.exe (
    echo dist\launchctl.exe not found - run "make go-build" or "make go-release-local" first 1>&2
    exit /b 1
)
dist\launchctl.exe
pause
