# InfoHub AI - Database Backup Script
# Backs up PostgreSQL database with rotation

param(
    [string]$BackupDir = "C:\backups\infohub_ai",
    [int]$RetentionDays = 30
)

$ErrorActionPreference = "Stop"

# Configuration
$DbName = "infohub_ai"
$DbUser = "infohub_user"
$DbHost = "localhost"
$DbPort = 5432
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = Join-Path $BackupDir "infohub_ai_$Timestamp.sql"

# Create backup directory if it doesn't exist
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
    Write-Host "✓ Created backup directory: $BackupDir"
}

Write-Host "Starting database backup..."
Write-Host "Database: $DbName"
Write-Host "Output: $BackupFile"

# Perform backup using pg_dump
try {
    $env:PGPASSWORD = "changeme"  # In production, use secure password management
    
    & pg_dump `
        --host=$DbHost `
        --port=$DbPort `
        --username=$DbUser `
        --dbname=$DbName `
        --format=plain `
        --file=$BackupFile `
        --verbose
    
    if ($LASTEXITCODE -eq 0) {
        $BackupSize = (Get-Item $BackupFile).Length / 1MB
        Write-Host "✓ Backup completed successfully!"
        Write-Host "  Size: $([math]::Round($BackupSize, 2)) MB"
        Write-Host "  Location: $BackupFile"
    } else {
        throw "pg_dump failed with exit code $LASTEXITCODE"
    }
} catch {
    Write-Host "✗ Backup failed: $_" -ForegroundColor Red
    exit 1
} finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

# Compress backup
Write-Host "`nCompressing backup..."
try {
    $CompressedFile = "$BackupFile.gz"
    & gzip -9 $BackupFile
    
    if (Test-Path $CompressedFile) {
        $CompressedSize = (Get-Item $CompressedFile).Length / 1MB
        Write-Host "✓ Compression completed!"
        Write-Host "  Size: $([math]::Round($CompressedSize, 2)) MB"
    }
} catch {
    Write-Host "! Compression failed (backup still available uncompressed)" -ForegroundColor Yellow
}

# Clean up old backups
Write-Host "`nCleaning up old backups (retention: $RetentionDays days)..."
try {
    $CutoffDate = (Get-Date).AddDays(-$RetentionDays)
    $OldBackups = Get-ChildItem -Path $BackupDir -Filter "infohub_ai_*.sql*" |
                  Where-Object { $_.LastWriteTime -lt $CutoffDate }
    
    if ($OldBackups) {
        foreach ($file in $OldBackups) {
            Remove-Item $file.FullName -Force
            Write-Host "  Removed: $($file.Name)"
        }
        Write-Host "✓ Cleaned up $($OldBackups.Count) old backup(s)"
    } else {
        Write-Host "  No old backups to remove"
    }
} catch {
    Write-Host "! Cleanup failed: $_" -ForegroundColor Yellow
}

# Summary
Write-Host "`n======================================"
Write-Host "Backup Summary"
Write-Host "======================================"
Write-Host "Status: SUCCESS"
Write-Host "Timestamp: $Timestamp"
Write-Host "Location: $BackupDir"
$AllBackups = Get-ChildItem -Path $BackupDir -Filter "infohub_ai_*.sql*"
Write-Host "Total backups: $($AllBackups.Count)"
Write-Host "======================================`n"
