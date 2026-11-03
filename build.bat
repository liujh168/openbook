rem bhobk.exe 构建脚本。
rem 使用仓库自带的 TinyCC 编译 bhobk.c，并在编译失败时返回非零退出码。
@echo off
tcc\tcc.exe -include shim.h bhobk.c -o bhobk.exe
if errorlevel 1 exit /b 1
echo Build succeeded: bhobk.exe
