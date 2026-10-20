@echo off
title Installateur ALJ Escalade Manager
:: Script range dans code_source\scripts\ : on travaille depuis code_source\
cd /d "%~dp0.."

echo ====================================================
echo    INSTALLATION DU PIPELINE HELLOASSO FFME
echo ====================================================
echo.

:: 1. Verifier si Python est installe
python --version >nul 2>&1
if %errorlevel% == 0 goto :python_ok
echo [ERREUR] Python n'est pas installe sur ce PC !
echo.
set /p PYTHON_VERSION=<.python-version
echo Veuillez installer Python %PYTHON_VERSION% (version utilisee par l'application).
echo IMPORTANT : Cochez imperativement la case "Add Python.exe to PATH" lors de l'installation de Python !
echo Telechargement direct : https://www.python.org/downloads/
echo.
echo Appuyez sur une touche pour quitter...
pause > nul
exit /b 1

:python_ok

:: 2. Creation de l'environnement virtuel venv
echo [1/4] Creation de l'environnement virtuel local...
if exist "venv" goto :venv_exists
python -m venv venv
if %errorlevel% == 0 goto :venv_created
echo [ERREUR] Impossible de creer l'environnement virtuel.
echo Assurez-vous d'avoir les permissions necessaires.
pause
exit /b 1

:venv_exists
echo [Note] Un dossier venv existe deja. Mise a jour des dependances...
goto :venv_done

:venv_created
echo [OK] Environnement virtuel venv cree avec succes.

:venv_done
echo.

:: 3. Installation des dependances
echo [2/4] Installation des paquets requis depuis requirements.txt...
echo      (Cela peut prendre une minute ou deux, veuillez patienter...)
echo.
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if %errorlevel% == 0 goto :pip_ok
echo.
echo [ERREUR] L'installation des paquets a echoue.
echo Verifiez votre connexion internet et que le fichier 'requirements.txt' est present.
pause
exit /b 1

:pip_ok
echo.
echo [OK] Toutes les bibliotheques ont ete installees avec succes !
echo.

:: 4. Icone de l'application (web\assets\logo.ico)
echo [3/4] Verification de l'icone de l'application...
if exist "web\assets\logo.ico" goto :icon_ok
echo [Note] Icone introuvable, le raccourci utilisera l'icone standard de Windows.
goto :icon_done

:icon_ok
echo [OK] Icone 'web\assets\logo.ico' trouvee.

:icon_done
echo.

:: 5. Creation du raccourci sur le Bureau Windows via Python COM
echo [4/4] Creation du raccourci sur le Bureau...
echo import os > create_lnk.py
echo import win32com.client >> create_lnk.py
echo current_dir = os.getcwd() >> create_lnk.py
echo desktop = win32com.client.Dispatch("WScript.Shell").SpecialFolders("Desktop") >> create_lnk.py
echo shortcut_path = os.path.join(desktop, "ALJ Escalade Manager.lnk") >> create_lnk.py
echo launcher = os.path.join(current_dir, "scripts", "Lancer_ALJ.vbs") >> create_lnk.py
echo icon = os.path.join(current_dir, "web", "assets", "logo.ico") >> create_lnk.py
echo shell = win32com.client.Dispatch("WScript.Shell") >> create_lnk.py
echo shortcut = shell.CreateShortcut(shortcut_path) >> create_lnk.py
echo shortcut.TargetPath = launcher >> create_lnk.py
echo shortcut.WorkingDirectory = current_dir >> create_lnk.py
echo if os.path.exists(icon): shortcut.IconLocation = icon >> create_lnk.py
echo shortcut.Save() >> create_lnk.py

venv\Scripts\python.exe create_lnk.py >nul 2>&1
if exist "create_lnk.py" del create_lnk.py

echo [OK] Raccourci 'ALJ Escalade Manager' cree sur votre bureau avec l'icone personnalisee du club !
echo Note : Ce raccourci utilise 'Lancer_ALJ.vbs', ce qui evite d'ouvrir une console noire.
echo.

:: 6. Succes
echo ====================================================
echo    INSTALLATION TERMINEE ET REUSSIE !
echo ====================================================
echo.
echo Vous pouvez double-cliquer sur le raccourci 'ALJ Escalade Manager' sur votre bureau pour lancer l'application.
echo L'application s'execute de facon fluide et moderne, sans ouvrir de console noire en arriere-plan.
echo.
echo Appuyez sur une touche pour fermer cette fenetre...
pause > nul
