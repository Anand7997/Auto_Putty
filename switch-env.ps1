param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("local", "team", "server")]
    [string]$Environment
)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Environment Configuration Switcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

switch ($Environment) {
    "local" {
        Write-Host "Switching to LOCAL DEVELOPMENT environment..." -ForegroundColor Yellow
        try {
            Copy-Item .env.local .env -Force
            Write-Host "✓ Successfully switched to local environment" -ForegroundColor Green
            Write-Host "✓ Frontend: http://localhost:8081/" -ForegroundColor Green
            Write-Host "✓ Backend: http://localhost:5000/" -ForegroundColor Green
        } catch {
            Write-Host "✗ Error: Could not find .env.local file" -ForegroundColor Red
        }
    }
    "team" {
        Write-Host "Switching to TEAM COLLABORATION environment..." -ForegroundColor Yellow
        try {
            Copy-Item .env.team .env -Force
            Write-Host "✓ Successfully switched to team environment" -ForegroundColor Green
            Write-Host "✓ Frontend: https://29tv5wlb-8081.inc1.devtunnels.ms/" -ForegroundColor Green
            Write-Host "✓ Backend: https://29tv5wlb-5000.inc1.devtunnels.ms/" -ForegroundColor Green
        } catch {
            Write-Host "✗ Error: Could not find .env.team file" -ForegroundColor Red
        }
    }
    "server" {
        Write-Host "Switching to SERVER DEPLOYMENT environment..." -ForegroundColor Yellow
        try {
            Copy-Item .env.server .env -Force
            Write-Host "✓ Successfully switched to server environment" -ForegroundColor Green
            Write-Host "✓ Frontend: http://10.30.3.85:8081/" -ForegroundColor Green
            Write-Host "✓ Backend: http://10.30.3.85:5000/" -ForegroundColor Green
        } catch {
            Write-Host "✗ Error: Could not find .env.server file" -ForegroundColor Red
        }
    }
}

Write-Host ""
$start = Read-Host "Would you like to start the application now? (y/n)"
if ($start -eq "y" -or $start -eq "Y") {
    Write-Host ""
    Write-Host "Starting the application..." -ForegroundColor Yellow
    npm run start
} else {
    Write-Host ""
    Write-Host "Environment switched. Run 'npm run start' when ready." -ForegroundColor Cyan
}

Write-Host ""