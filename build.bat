@echo off
rem Build with portable TinyCC
tcc\tcc.exe -DSQLITE_THREADSAFE=0 -DSQLITE_DISABLE_INTRINSIC -include shim.h -Isqlite-amalgamation-3540100 bhobk.c sqlite-amalgamation-3540100\sqlite3.c -o bhobk.exe
if errorlevel 1 exit /b 1
echo Build succeeded: bhobk.exe
