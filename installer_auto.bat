@echo off
REM ==========================================================================
REM  Installe la mise a jour automatique quotidienne - Windows
REM ==========================================================================
REM  Usage :  installer_auto.bat            installe a 07:00
REM           installer_auto.bat 06:30      installe a une autre heure
REM           installer_auto.bat --retirer  desinstalle
REM
REM  Cree une tache planifiee qui lance maj.py SANS ouvrir de fenetre
REM  (via un petit script VBS intermediaire).
REM ==========================================================================
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
set "DIR=%CD%"
set "TACHE=PronosFoot-MAJ"

set "ARG=%~1"
if "%ARG%"=="" set "ARG=07:00"

echo == Installation de la mise a jour automatique ==
echo    dossier : %DIR%

REM ------------------------------------------------------------ desinstallation
if "%ARG%"=="--retirer" goto RETIRER

REM ------------------------------------------------------------------ python
set "PY="
set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
for /f "delims=" %%i in ('where python 2^>nul')   do if not defined PY  set "PY=%%i"
for /f "delims=" %%i in ('where py 2^>nul')       do if not defined PY  set "PY=%%i"

if not defined PY (
  echo ERREUR : Python est introuvable.
  echo Telecharge-le sur https://python.org et coche "Add Python to PATH"
  echo pendant l'installation, puis relance ce script.
  goto FIN_ERREUR
)
if not defined PYW set "PYW=%PY%"
echo    python  : %PY%

REM ------------------------------------------------------- dependances
"%PY%" -c "import numpy, scipy, pandas" >nul 2>nul
if errorlevel 1 (
  echo ERREUR : les bibliotheques numpy / scipy / pandas manquent.
  echo Installe-les avec :
  echo     "%PY%" -m pip install numpy scipy pandas
  goto FIN_ERREUR
)
echo    dependances numpy / scipy / pandas : OK

REM --------------------------------------------- script de lancement silencieux
REM pythonw.exe n'ouvre pas de fenetre, mais on passe par un VBS pour garantir
REM qu'aucune fenetre console n'apparait, meme si pythonw est remplace par python.
set "VBS=%DIR%\maj_silencieux.vbs"
> "%VBS%" echo Set sh = CreateObject("WScript.Shell")
>>"%VBS%" echo sh.CurrentDirectory = "%DIR%"
>>"%VBS%" echo sh.Run """%PYW%"" ""%DIR%\maj.py""", 0, False
echo    lanceur silencieux : %VBS%

REM ------------------------------------------------------------ tache planifiee
schtasks /Create /F /TN "%TACHE%" /TR "wscript.exe \"%VBS%\"" /SC DAILY /ST %ARG% >nul
if errorlevel 1 (
  echo ERREUR : la creation de la tache planifiee a echoue.
  echo Si le message parle de droits, relance ce script en tant
  echo qu'administrateur.
  goto FIN_ERREUR
)

echo.
echo -^> Tache planifiee "%TACHE%" installee : tous les jours a %ARG%.
echo    La fenetre ne s'ouvrira pas, tout se passe en arriere-plan.
echo.
echo == Verification ==
echo    Test immediat :            "%PY%" maj.py --check
echo    Voir le journal :          notepad "%DIR%\data\maj.log"
echo    Choisir le dossier cloud : "%PY%" maj.py --config
echo.
echo == Desinstallation ==
echo    installer_auto.bat --retirer
goto FIN

:RETIRER
schtasks /Delete /F /TN "%TACHE%" >nul 2>nul
if errorlevel 1 (echo -> aucune tache "%TACHE%" n'etait installee.) else (echo -^> tache planifiee "%TACHE%" supprimee.)
if exist "%DIR%\maj_silencieux.vbs" del "%DIR%\maj_silencieux.vbs"
echo -> lanceur silencieux supprime.
goto FIN

:FIN_ERREUR
echo.
pause
exit /b 1

:FIN
echo.
pause
exit /b 0
