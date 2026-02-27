@echo off
echo 🚀 Starting Permanent Allure Server
echo ====================================

cd /d "%~dp0backend"

echo 📂 Current directory: %CD%
echo 📊 Checking for allure-results...

if not exist "allure-results" (
    echo ❌ No allure-results directory found!
    echo 🔧 Please run a test first with: python run_test_with_allure.py "TestCaseName"
    pause
    exit /b 1
)

echo ✅ Found allure-results directory
echo 🌐 Starting Allure server on port 8888...

"C:\Users\VAnand\AppData\Roaming\npm\allure.cmd" serve allure-results --port 8888 --host 127.0.0.1

echo 🛑 Allure server stopped
pause
