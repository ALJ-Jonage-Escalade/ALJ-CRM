@echo off
title ALJ Escalade - Serveur Web Local
chcp 65001 > nul
cd /d "%~dp0..\code_source"

echo ====================================================
echo   LANCEMENT DU SERVEUR WEB LOCAL ALJ ESCALADE
echo ====================================================
echo.
echo URL du portail Bureau : http://127.0.0.1:8000/bureau/
echo URL Compétitions     : http://127.0.0.1:8000/competitions
echo URL Annuaire         : http://127.0.0.1:8000/index
echo Documentation API    : http://127.0.0.1:8000/docs
echo.

:: Page Bureau = application Vue, servie depuis frontend\dist\ : la compiler à chaque lancement
:: (le code a pu changer depuis la dernière fois). Nécessite Node.js (version : frontend\.nvmrc)
where npm >nul 2>nul
if errorlevel 1 goto :sans_npm
echo Compilation de l'interface web...
pushd frontend
if not exist "node_modules\" call npm ci --no-fund --no-audit
call npm run build
if not errorlevel 1 goto :compilation_ok
echo Échec de la compilation : réinstallation des dépendances puis nouvel essai...
call npm ci --no-fund --no-audit
call npm run build
if not errorlevel 1 goto :compilation_ok
popd
echo.
echo ATTENTION : la compilation de l'interface web a échoué, voir les messages ci-dessus.
goto :verifier_dist

:compilation_ok
popd
echo.
goto :serveur

:sans_npm
echo ATTENTION : Node.js / npm introuvable, l'interface web ne peut pas être compilée.
echo Installer Node.js depuis https://nodejs.org/ puis relancer ce script.

:verifier_dist
if exist "frontend\dist\index.html" goto :dist_ancienne
echo La page Bureau affichera "Interface web non compilée".
echo.
pause
goto :serveur
:dist_ancienne
echo La dernière version compilée sera utilisée, elle peut être périmée.
echo.
pause

:serveur
start "" "http://127.0.0.1:8000/bureau/"

if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -m uvicorn server:app --app-dir src --host 127.0.0.1 --port 8000 --reload
) else if exist "..\venv\Scripts\python.exe" (
    ..\venv\Scripts\python.exe -m uvicorn server:app --app-dir src --host 127.0.0.1 --port 8000 --reload
) else (
    python -m uvicorn server:app --app-dir src --host 127.0.0.1 --port 8000 --reload
)

pause
