@echo off
:: ============================================================
::  Nausort Media v2.0 — One-click build to .exe
::  Requirements: pip install pyinstaller pywebview Pillow
:: ============================================================

echo.
echo  ============================
echo   Nausort Media — Building .exe
echo  ============================
echo.

:: Install build dependencies
echo [1/3] Installing dependencies...
pip install pyinstaller pywebview Pillow --quiet

:: Clean previous build
echo [2/3] Cleaning previous build...
if exist dist\Nausort Media rmdir /s /q dist\Nausort Media
if exist build       rmdir /s /q build

:: Run PyInstaller
echo [3/3] Running PyInstaller...
pyinstaller build.spec --noconfirm

echo.
if exist dist\Nausort Media\Nausort Media.exe (
    echo  [OK] Build successful!
    echo  Output: dist\Nausort Media\Nausort Media.exe
    echo.
    echo  To distribute: copy the entire dist\Nausort Media\ folder.
) else (
    echo  [ERROR] Build failed. Check output above for errors.
)
echo.
pause
