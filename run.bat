@echo off
echo ========================================
echo   YouTube Summarizer - Launch Script
echo ========================================
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo [1/4] Creation de l'environnement virtuel...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install dependencies
echo [2/4] Installation des dependances...
pip install -r requirements.txt >nul 2>&1

REM Check if .env exists
if not exist ".env" (
    echo [3/4] Creation du fichier de configuration...
    copy .env.example .env
    echo.
    echo ========================================
    echo   IMPORTANT: Editez le fichier .env
    echo   et ajoutez votre cle API OpenRouter
    echo ========================================
    echo.
    notepad .env
    pause
    exit /b
)

echo [4/4] Lancement de l'interface...
echo.
echo Ouvrez votre navigateur a l'adresse:
echo http://localhost:8501
echo.
streamlit run app.py

pause