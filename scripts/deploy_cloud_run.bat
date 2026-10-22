@echo off
chcp 65001 >nul
call "%~dp0..\code_source\scripts\deploy_cloud_run.bat"
