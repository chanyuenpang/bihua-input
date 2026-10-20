@echo off
rem Run from an ASCII build directory containing SetupBootstrap.cpp and payload.zip.
call "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat" -arch=amd64 -host_arch=amd64
if errorlevel 1 exit /b 1
if "%1"=="uninstall" (
  cl /nologo /EHsc /std:c++17 /utf-8 /MT /O2 /DBIHUA_UNINSTALL SetupBootstrap.cpp /Fe:Uninstall.exe /Fo:uninstall.obj /link /SUBSYSTEM:WINDOWS ole32.lib shell32.lib user32.lib gdi32.lib uuid.lib comctl32.lib
  exit /b
)
rc /nologo setup.rc
if errorlevel 1 exit /b 1
cl /nologo /EHsc /std:c++17 /utf-8 /MT /O2 SetupBootstrap.cpp setup.res /Fe:BihuaInput-0.6.29-setup.exe /Fo:setup.obj /link /SUBSYSTEM:WINDOWS ole32.lib shell32.lib user32.lib gdi32.lib uuid.lib comctl32.lib
exit /b %errorlevel%
