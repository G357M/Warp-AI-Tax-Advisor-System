# InfoHub AI Tax Advisor - Startup Script
# Runs on alternative ports to avoid conflicts

Write-Host "=" -ForegroundColor Cyan
Write-Host "🚀 Starting InfoHub AI Tax Advisor" -ForegroundColor Green
Write-Host "=" -ForegroundColor Cyan
Write-Host ""

# Check if other services are using default ports
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
$port3000 = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue

if ($port8000 -or $port3000) {
    Write-Host "⚠️  Ports 8000 or 3000 are in use!" -ForegroundColor Yellow
    Write-Host "   Using alternative ports:" -ForegroundColor Yellow
    Write-Host "   - Backend: http://localhost:8001" -ForegroundColor Cyan
    Write-Host "   - Frontend: http://localhost:3001" -ForegroundColor Cyan
    Write-Host ""
    
    $BACKEND_PORT = 8001
    $FRONTEND_PORT = 3001
} else {
    Write-Host "✅ Default ports available" -ForegroundColor Green
    Write-Host "   - Backend: http://localhost:8000" -ForegroundColor Cyan
    Write-Host "   - Frontend: http://localhost:3000" -ForegroundColor Cyan
    Write-Host ""
    
    $BACKEND_PORT = 8000
    $FRONTEND_PORT = 3000
}

# Start Backend
Write-Host "📦 Starting Backend Server..." -ForegroundColor Cyan
$env:API_PORT = $BACKEND_PORT
Start-Process pwsh -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; python test_server.py" -WindowStyle Normal

Start-Sleep -Seconds 3

# Wait for backend to be ready
Write-Host "⏳ Waiting for backend..." -ForegroundColor Yellow
$maxAttempts = 10
$attempt = 0
$backendReady = $false

while ($attempt -lt $maxAttempts -and -not $backendReady) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$BACKEND_PORT/health" -Method GET -TimeoutSec 2 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
            Write-Host "✅ Backend is ready!" -ForegroundColor Green
        }
    } catch {
        $attempt++
        Write-Host "   Attempt $attempt/$maxAttempts..." -ForegroundColor Gray
        Start-Sleep -Seconds 1
    }
}

if (-not $backendReady) {
    Write-Host "❌ Backend failed to start!" -ForegroundColor Red
    Write-Host "   Please check the backend window for errors." -ForegroundColor Yellow
    exit 1
}

# Start Frontend
Write-Host ""
Write-Host "🎨 Starting Frontend..." -ForegroundColor Cyan
$env:NEXT_PUBLIC_API_URL = "http://localhost:$BACKEND_PORT/api/v1"
$env:PORT = $FRONTEND_PORT
Start-Process pwsh -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\frontend'; npm run dev -- -p $FRONTEND_PORT" -WindowStyle Normal

Start-Sleep -Seconds 5

Write-Host ""
Write-Host "=" -ForegroundColor Cyan
Write-Host "✅ InfoHub AI Tax Advisor Started!" -ForegroundColor Green
Write-Host "=" -ForegroundColor Cyan
Write-Host ""
Write-Host "📍 Access URLs:" -ForegroundColor Yellow
Write-Host "   Main App:    http://localhost:$FRONTEND_PORT" -ForegroundColor Cyan
Write-Host "   Admin Panel: http://localhost:$FRONTEND_PORT/admin" -ForegroundColor Cyan
Write-Host "   API Docs:    http://localhost:$BACKEND_PORT/docs" -ForegroundColor Cyan
Write-Host "   Health:      http://localhost:$BACKEND_PORT/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "📝 To stop: Close both PowerShell windows" -ForegroundColor Gray
Write-Host ""
