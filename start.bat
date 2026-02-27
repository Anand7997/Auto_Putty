@echo off
echo 🚀 IXIGO TEST AUTOMATION SYSTEM
echo =====================================
echo.
echo Starting Frontend + Backend...
echo.
echo ✅ Frontend: React + Vite (Port 5173)
echo ✅ Backend: Flask API (Port 5000)
echo ✅ Database: SQL Server (Ixigo_TestAutomation)
echo.

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js is not installed. Please install Node.js first.
    pause
    exit /b 1
)

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python first.
    pause
    exit /b 1
)

REM Install dependencies if node_modules doesn't exist
if not exist "node_modules" (
    echo 📦 Installing dependencies...
    npm run setup
)

echo 🎯 Starting the system...
npm start

pause
