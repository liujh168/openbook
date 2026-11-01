@echo off
rem Build with portable TinyCC
tcc\tcc.exe -include shim.h bhobk.c -o bhobk.exe
if errorlevel 1 exit /b 1
echo Build succeeded: bhobk.exe
