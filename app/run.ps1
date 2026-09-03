# Lancement rapide — Vélib' Demo App (Windows)
$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppDir

Write-Host "=== Vélib' Demo App ===" -ForegroundColor Cyan

# Vérifier MongoDB
try {
    $mongo = docker ps --filter "name=gbfs_mongodb" --format "{{.Names}}" 2>$null
    if (-not $mongo) {
        Write-Host "MongoDB non démarré. Tentative: docker start gbfs_mongodb" -ForegroundColor Yellow
        docker start gbfs_mongodb 2>$null
        Start-Sleep 2
    }
} catch {
    Write-Host "Docker non disponible — démarrez Docker Desktop." -ForegroundColor Red
    exit 1
}

Write-Host "Installation des dépendances..." -ForegroundColor Gray
python -m pip install -q -r requirements.txt

$env:MONGO_URI = "mongodb://localhost:27017"

Write-Host "Serveur: http://localhost:8000" -ForegroundColor Green
Write-Host "Arrêt: Ctrl+C" -ForegroundColor Gray

python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000
