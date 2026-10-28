@echo off
title ALJ Escalade - Environnement de développement local
chcp 65001 > nul

:: ============================================================================
:: ALJ Escalade - Lanceur d'environnement de développement local Windows
::
:: 1. Vérification et démarrage des conteneurs Docker (dev/docker-compose.yml)
:: 2. Attente de la disponibilité de l'émulateur Firestore et de Mailpit
:: 3. Injection des variables de dev/dev.env et ensemencement (seed_emulator.py)
:: 4. Lancement du backend FastAPI (port 8080) et du serveur Vite (port 5173)
:: 5. Ouverture automatique du navigateur sur http://localhost:5173/bureau/
:: ============================================================================

:: 0. Positionnement dans le dossier code_source
if exist "%~dp0..\code_source\dev\docker-compose.yml" (
    cd /d "%~dp0..\code_source"
) else if exist "%~dp0..\dev\docker-compose.yml" (
    cd /d "%~dp0.."
) else (
    echo [ERREUR] Impossible de localiser le dossier code_source.
    pause
    exit /b 1
)

:: Enrichissement du PATH pour les outils Windows usuels
if exist "%LOCALAPPDATA%\Python\pythoncore-3.15-64\Scripts\uv.exe" set "PATH=%LOCALAPPDATA%\Python\pythoncore-3.15-64\Scripts;%PATH%"
if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
if exist "%LOCALAPPDATA%\Programs\uv" set "PATH=%LOCALAPPDATA%\Programs\uv;%PATH%"
if exist "%ProgramFiles%\Docker\Docker\resources\bin" set "PATH=%ProgramFiles%\Docker\Docker\resources\bin;%PATH%"
if exist "%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin" set "PATH=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin;%PATH%"
if exist "%ProgramFiles%\nodejs" set "PATH=%ProgramFiles%\nodejs;%PATH%"
if exist "%APPDATA%\npm" set "PATH=%APPDATA%\npm;%PATH%"

echo ====================================================
echo   ALJ ESCALADE - LANCEMENT DU SERVEUR WEB LOCAL
echo ====================================================
echo.

:: ----------------------------------------------------------------------------
:: 1. Verification et demarrage des conteneurs Docker
:: ----------------------------------------------------------------------------
echo [1/5] Verification de Docker...

where docker >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERREUR] Docker n'a pas ete trouve dans le PATH.
    echo Veuillez installer Docker Desktop et verifier qu'il est accessible :
    echo https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

:: Detection de la commande compose (docker compose ou docker-compose)
set "COMPOSE_CMD=docker compose"
docker compose version >nul 2>nul
if errorlevel 1 (
    docker-compose version >nul 2>nul
    if not errorlevel 1 (
        set "COMPOSE_CMD=docker-compose"
    ) else (
        echo.
        echo [ERREUR] Ni 'docker compose' ni 'docker-compose' n'ont ete trouves.
        echo.
        pause
        exit /b 1
    )
)

:: Verifier si le moteur Docker tourne
docker info >nul 2>nul
if not errorlevel 1 goto :docker_daemon_ready

echo Docker Desktop ne semble pas demarre.
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    echo Demarrage automatique de Docker Desktop...
    start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
) else if exist "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe" (
    echo Demarrage automatique de Docker Desktop...
    start "" "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
)
echo En attente de l'initialisation du moteur Docker...
set /a DOCKER_WAIT=0

:wait_docker_loop
timeout /t 3 /nobreak >nul
docker info >nul 2>nul
if not errorlevel 1 goto :docker_daemon_ready
set /a DOCKER_WAIT+=1
if %DOCKER_WAIT% geq 25 (
    echo.
    echo [ERREUR] Le moteur Docker n'a pas demarre apres 75 secondes.
    echo Veuillez lancer Docker Desktop manuellement puis relancer ce script.
    echo.
    pause
    exit /b 1
)
goto :wait_docker_loop

:docker_daemon_ready
echo Demarrage des conteneurs Docker (Firebase emulator + Mailpit)...
%COMPOSE_CMD% -f dev\docker-compose.yml up -d
if errorlevel 1 (
    echo.
    echo [ERREUR] Echec du demarrage de docker compose.
    echo.
    pause
    exit /b 1
)
echo [OK] Conteneurs Docker demarres.
echo.

:: ----------------------------------------------------------------------------
:: 2. Attente de la disponibilite de l'emulateur et de Mailpit
:: ----------------------------------------------------------------------------
echo [2/5] Attente de la disponibilite de Firestore (:8081) et de Mailpit (:8025)...

set /a SERVICES_WAIT=0
:wait_services_loop
set FIRESTORE_OK=0
set MAILPIT_OK=0

curl.exe -sf --connect-timeout 2 --max-time 3 "http://127.0.0.1:8081/" >nul 2>nul
if %errorlevel% equ 0 set FIRESTORE_OK=1

curl.exe -sf --connect-timeout 2 --max-time 3 "http://127.0.0.1:8025/" >nul 2>nul
if %errorlevel% equ 0 set MAILPIT_OK=1

if %FIRESTORE_OK% equ 1 if %MAILPIT_OK% equ 1 goto :services_ready

timeout /t 2 /nobreak >nul
set /a SERVICES_WAIT+=1
if %SERVICES_WAIT% lss 45 goto :wait_services_loop

echo.
echo [ERREUR] Delai d'attente depasse pour les services Docker :
if %FIRESTORE_OK% equ 0 echo   - Firestore emulator :8081 ne repond pas.
if %MAILPIT_OK% equ 0 echo   - Mailpit :8025 ne repond pas.
echo.
pause
exit /b 1

:services_ready
echo [OK] Emulateur Firestore et Mailpit operationnels.
echo.

:: ----------------------------------------------------------------------------
:: 3. Injection automatique des variables dev/dev.env et ensemencement
:: ----------------------------------------------------------------------------
echo [3/5] Configuration de l'environnement et ensemencement des donnees...

if not exist "dev\dev.env" (
    echo.
    echo [ERREUR] Fichier dev\dev.env introuvable.
    echo.
    pause
    exit /b 1
)

echo Chargement des variables d'environnement depuis dev\dev.env...
for /f "usebackq eol=# tokens=1* delims==" %%A in ("dev\dev.env") do (
    set "%%A=%%B"
)
set "PORT=8080"
set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"

:: Detection de Python / uv
set "PYTHON_RUN="
set "UVICORN_RUN="
where uv >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_RUN=uv run python"
    set "UVICORN_RUN=uv run python -m uvicorn server:app --app-dir src --host 127.0.0.1 --port 8080 --reload --reload-dir src"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_RUN=.venv\Scripts\python.exe"
    set "UVICORN_RUN=.venv\Scripts\python.exe -m uvicorn server:app --app-dir src --host 127.0.0.1 --port 8080 --reload --reload-dir src"
) else (
    set "PYTHON_RUN=python"
    set "UVICORN_RUN=python -m uvicorn server:app --app-dir src --host 127.0.0.1 --port 8080 --reload --reload-dir src"
)

echo Ensemencement de l'emulateur avec les donnees de test (Harry Potter)...
call %PYTHON_RUN% dev\seed\seed_emulator.py
if errorlevel 1 (
    echo.
    echo [ATTENTION] L'ensemencement a renvoye une erreur - code %errorlevel%.
    echo.
) else (
    echo [OK] Base de test initialisee.
)
echo.

:: ----------------------------------------------------------------------------
:: 4. Lancement du backend FastAPI et du serveur Vite dans des terminaux dedies
:: ----------------------------------------------------------------------------
echo [4/5] Lancement des serveurs dans des fenetres dediees...

:: Verification de Node / npm pour le frontend
where npm >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERREUR] Node.js / npm introuvable.
    echo Veuillez installer Node.js depuis https://nodejs.org/ pour executer le frontend.
    echo.
    pause
    exit /b 1
)

:: Installation eventuelle des dependances frontend si absentes
if not exist "frontend\node_modules\" (
    echo Installation initiale des dependances frontend...
    pushd frontend
    call npm ci --no-fund --no-audit
    popd
)

:: Demarrage du backend FastAPI
curl.exe -sf --connect-timeout 1 --max-time 2 "http://127.0.0.1:8080/health" >nul 2>nul
if %errorlevel% equ 0 (
    echo [OK] Serveur Backend FastAPI deja actif sur le port 8080.
) else (
    echo Demarrage du serveur Backend FastAPI sur le port 8080...
    start "ALJ Escalade - Backend FastAPI [Port 8080]" /d "%CD%" cmd /k "title ALJ Escalade - Backend FastAPI [Port 8080] & echo ==================================================== & echo   ALJ ESCALADE - BACKEND FASTAPI (PORT 8080) & echo ==================================================== & echo. & %PYTHON_RUN% dev\check_env.py & %UVICORN_RUN%"
)

:: Demarrage du frontend Vite
curl.exe -sf --connect-timeout 1 --max-time 2 "http://localhost:5173/" >nul 2>nul
if %errorlevel% equ 0 (
    echo [OK] Serveur Frontend Vite deja actif sur le port 5173.
) else (
    echo Demarrage du serveur Frontend Vite sur le port 5173...
    start "ALJ Escalade - Frontend Vite [Port 5173]" /d "%CD%\frontend" cmd /k "title ALJ Escalade - Frontend Vite [Port 5173] & echo ==================================================== & echo   ALJ ESCALADE - FRONTEND VITE (PORT 5173) & echo ==================================================== & echo. & call npm run dev"
)

echo [OK] Serveurs backend et frontend lances dans leurs terminaux respectifs.
echo.

:: ----------------------------------------------------------------------------
:: 5. Attente de Vite et ouverture automatique du navigateur
:: ----------------------------------------------------------------------------
echo [5/5] En attente de la disponibilite du serveur Vite (port 5173)...

set /a VITE_WAIT=0
:wait_vite_loop
curl.exe -sf --connect-timeout 1 --max-time 2 "http://localhost:5173/" >nul 2>nul
if %errorlevel% equ 0 goto :open_browser

timeout /t 1 /nobreak >nul
set /a VITE_WAIT+=1
if %VITE_WAIT% lss 30 goto :wait_vite_loop

:open_browser
echo [OK] Serveur Vite accessible.
echo.
echo Ouverture automatique du navigateur...
start "" "http://localhost:5173/bureau/"

:: ----------------------------------------------------------------------------
:: Synthese et statut
:: ----------------------------------------------------------------------------
echo.
echo ====================================================
echo   ALJ ESCALADE - APPLICATION LOCALE DEMARREE
echo ====================================================
echo.
echo Acces Web :
echo   - Portail Bureau (Vite SPA)   : http://localhost:5173/bureau/
echo   - API Backend (FastAPI)       : http://localhost:8080/
echo   - Documentation API Swagger   : http://localhost:8080/docs
echo   - Health check                : http://localhost:8080/health
echo   - Firebase Emulator UI        : http://localhost:4000/
echo   - Mailpit (Capture e-mails)   : http://localhost:8025/
echo.
echo Comptes de test (Firebase Auth emulator) :
echo   - Admin    : albus.dumbledore@alj-escalade.fr
echo   - Coach    : severus.snape@hogwarts.example
echo   - Lecture  : argus.filch@hogwarts.example
echo.
echo Instructions :
echo   - Les fenetres FastAPI et Vite doivent rester ouvertes pendant l'utilisation.
echo   - Pour arreter un serveur : fermez sa fenetre ou faites Ctrl+C.
echo.
echo Appuyez sur une touche pour afficher les options d'arret ou fermer ce lanceur...
pause >nul
echo.
set /p STOP_DOCKER="Voulez-vous arreter les conteneurs Docker maintenant ? (o/N) : "
if /i "%STOP_DOCKER%"=="o" (
    echo Arret des conteneurs Docker en cours...
    %COMPOSE_CMD% -f dev\docker-compose.yml down
    echo [OK] Conteneurs Docker arretes.
)
