@echo off
echo.
echo ========================================
echo   Environment Configuration Switcher
echo ========================================
echo.
echo Choose your environment:
echo 1. Local Development (localhost)
echo 2. Team Collaboration (dev tunnels)
echo 3. Server Deployment (10.30.3.85)
echo 4. Exit
echo.
set /p choice="Enter your choice (1-4): "

if "%choice%"=="1" (
    echo.
    echo Switching to LOCAL DEVELOPMENT environment...
    copy .env.local .env >nul 2>&1
    if %errorlevel%==0 (
        echo ✓ Successfully switched to local environment
        echo ✓ Frontend: http://localhost:8081/
        echo ✓ Backend: http://localhost:5000/
    ) else (
        echo ✗ Error: Could not find .env.local file
    )
) else if "%choice%"=="2" (
    echo.
    echo Switching to TEAM COLLABORATION environment...
    copy .env.team .env >nul 2>&1
    if %errorlevel%==0 (
        echo ✓ Successfully switched to team environment
        echo ✓ Frontend: https://29tv5wlb-8081.inc1.devtunnels.ms/
        echo ✓ Backend: https://29tv5wlb-5000.inc1.devtunnels.ms/
    ) else (
        echo ✗ Error: Could not find .env.team file
    )
) else if "%choice%"=="3" (
    echo.
    echo Switching to SERVER DEPLOYMENT environment...
    copy .env.server .env >nul 2>&1
    if %errorlevel%==0 (
        echo ✓ Successfully switched to server environment
        echo ✓ Frontend: http://10.30.3.85:8081/
        echo ✓ Backend: http://10.30.3.85:5000/
    ) else (
        echo ✗ Error: Could not find .env.server file
    )
) else if "%choice%"=="4" (
    echo Goodbye!
    exit /b 0
) else (
    echo Invalid choice. Please run the script again.
)

echo.
echo Would you like to start the application now? (y/n)
set /p start="Enter your choice: "

if /i "%start%"=="y" (
    echo.
    echo Starting the application...
    npm run start
) else (
    echo.
    echo Environment switched. Run 'npm run start' when ready.
)

echo.
pause