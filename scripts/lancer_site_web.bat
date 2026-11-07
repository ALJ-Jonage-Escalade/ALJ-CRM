@echo off
chcp 65001 >nul
call "%~dp0..\code_source\scripts\lancer_site_web.bat" %*
