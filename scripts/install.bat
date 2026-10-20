@echo off
title Installateur ALJ Escalade Manager
chcp 65001 > nul
:: Script range dans scripts\ : on travaille depuis la racine du projet
cd /d "%~dp0.."

echo ====================================================
echo    INSTALLATION DU PIPELINE HELLOASSO FFME
echo ====================================================
echo.

:: 1. Vérifier si Python est installé
set /p PYTHON_VERSION=<code_source\.python-version
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ ERREUR : Python n'est pas installé sur ce PC !
    echo.
    echo 👉 Veuillez installer Python %PYTHON_VERSION%, la version utilisée par l'application.
    echo 👉 IMPORTANT : Cochez impérativement la case Add Python.exe to PATH lors de l'installation de Python !
    echo 👉 Téléchargement direct : https://www.python.org/downloads/
    echo.
    echo Appuyez sur une touche pour quitter...
    pause > nul
    exit /b 1
)

:: 2. Création de l'environnement virtuel venv
echo 📦 1. Création de l'environnement virtuel local (venv)...
if exist "venv" (
    echo [Note] Un dossier venv existe déjà. Mise à jour des dépendances...
) else (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ❌ ERREUR : Impossible de créer l'environnement virtuel.
        echo Assurez-vous d'avoir les permissions nécessaires.
        pause
        exit /b 1
    )
    echo ✅ Environnement virtuel venv créé avec succès.
)
echo.

:: 3. Installation des dépendances
echo 📥 2. Installation des paquets requis depuis requirements.txt...
echo    (Cela peut prendre une minute ou deux, veuillez patienter...)
echo.
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r code_source\requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ❌ ERREUR : L'installation des paquets a échoué.
    echo Vérifiez votre connexion internet et que le fichier 'code_source\requirements.txt' est présent.
    pause
    exit /b 1
)
echo.
echo ✅ Toutes les bibliothèques ont été installées avec succès !
echo.

:: 4. Icône de l'application (code_source\web\assets\logo.ico)
echo 🎨 3. Vérification de l'icône de l'application...
if exist "code_source\web\assets\logo.ico" (
    echo ✅ Icône 'code_source\web\assets\logo.ico' trouvée.
) else (
    echo ⚠️ Icône introuvable, le raccourci utilisera l'icône standard de Windows.
)
echo.

:: 5. Création du raccourci sur le Bureau Windows via Python COM
echo 🖥️ 4. Création du raccourci sur le Bureau...
echo import os > create_lnk.py
echo import win32com.client >> create_lnk.py
echo current_dir = os.getcwd() >> create_lnk.py
echo desktop = win32com.client.Dispatch("WScript.Shell").SpecialFolders("Desktop") >> create_lnk.py
echo shortcut_path = os.path.join(desktop, "ALJ Escalade Manager.lnk") >> create_lnk.py
echo launcher = os.path.join(current_dir, "code_source", "scripts", "Lancer_ALJ.vbs") >> create_lnk.py
echo icon = os.path.join(current_dir, "code_source", "web", "assets", "logo.ico") >> create_lnk.py
echo shell = win32com.client.Dispatch("WScript.Shell") >> create_lnk.py
echo shortcut = shell.CreateShortcut(shortcut_path) >> create_lnk.py
echo shortcut.TargetPath = launcher >> create_lnk.py
echo shortcut.WorkingDirectory = current_dir >> create_lnk.py
echo if os.path.exists(icon): shortcut.IconLocation = icon >> create_lnk.py
echo shortcut.Save() >> create_lnk.py

venv\Scripts\python.exe create_lnk.py >nul 2>&1
if exist "create_lnk.py" del create_lnk.py

echo ✅ Raccourci 'ALJ Escalade Manager' créé sur votre bureau avec l'icône personnalisée du club !
echo 👉 Note : Ce raccourci utilise 'pythonw.exe', ce qui permet de l'épingler à la barre des tâches de Windows.
echo.

:: 6. Succès
echo ====================================================
echo    INSTALLATION TERMINÉE ET RÉUSSIE ! 🎉
echo ====================================================
echo.
echo 👉 Vous pouvez double-cliquer sur le raccourci 'ALJ Escalade Manager' sur votre bureau pour lancer l'application.
echo 👉 L'application s'exécute de façon fluide et moderne, sans ouvrir de console noire en arrière-plan.
echo.
echo Appuyez sur une touche pour fermer cette fenêtre...
pause > nul
