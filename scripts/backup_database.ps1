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
$PartialBackupFile = "$BackupFile.partial"
$FinalBackupFile = $BackupFile

if ($RetentionDays -lt 1) {
    throw "RetentionDays must be at least 1"
}

# Create backup directory if it doesn't exist
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
    Write-Host "✓ Created backup directory: $BackupDir"
}

Write-Host "Starting database backup..."
Write-Host "Database: $DbName"
Write-Host "Output: $BackupFile"

# Perform an atomic backup using credentials supplied by libpq configuration.
# Supported non-interactive sources include PGPASSWORD, PGPASSFILE and the
# standard pgpass file. Credentials are never embedded in this repository.
try {
    $PgDumpPath = (Get-Command pg_dump -CommandType Application -ErrorAction Stop).Source
    foreach ($target in @($PartialBackupFile, $BackupFile, "$BackupFile.gz")) {
        if (Test-Path -LiteralPath $target) {
            throw "Backup target already exists: $target"
        }
    }

    & $PgDumpPath `
        --host=$DbHost `
        --port=$DbPort `
        --username=$DbUser `
        --dbname=$DbName `
        --no-password `
        --no-owner `
        --no-privileges `
        --format=plain `
        --file=$PartialBackupFile `
        --verbose
    
    if ($LASTEXITCODE -eq 0) {
        Move-Item -LiteralPath $PartialBackupFile -Destination $BackupFile
        $BackupSize = (Get-Item $BackupFile).Length / 1MB
        Write-Host "✓ Backup completed successfully!"
        Write-Host "  Size: $([math]::Round($BackupSize, 2)) MB"
        Write-Host "  Location: $BackupFile"
    } else {
        throw "pg_dump failed with exit code $LASTEXITCODE"
    }
} catch {
    if (Test-Path -LiteralPath $PartialBackupFile) {
        Remove-Item -LiteralPath $PartialBackupFile -Force
    }
    Write-Host "✗ Backup failed: $_" -ForegroundColor Red
    exit 1
}

# Compress backup
Write-Host "`nCompressing backup..."
try {
    $CompressedFile = "$BackupFile.gz"
    & gzip -9 -- $BackupFile
    
    if ($LASTEXITCODE -ne 0) {
        throw "gzip failed with exit code $LASTEXITCODE"
    }
    if (Test-Path -LiteralPath $CompressedFile) {
        $FinalBackupFile = $CompressedFile
        $CompressedSize = (Get-Item $CompressedFile).Length / 1MB
        Write-Host "✓ Compression completed!"
        Write-Host "  Size: $([math]::Round($CompressedSize, 2)) MB"
    } else {
        throw "gzip completed without creating $CompressedFile"
    }
} catch {
    $CompressedFile = "$BackupFile.gz"
    if (Test-Path -LiteralPath $CompressedFile) {
        Remove-Item -LiteralPath $CompressedFile -Force
    }
    if (-not (Test-Path -LiteralPath $BackupFile)) {
        Write-Host "✗ Compression failed and no complete uncompressed backup remains" -ForegroundColor Red
        exit 1
    }
    Write-Host "! Compression failed (backup still available uncompressed)" -ForegroundColor Yellow
}

# Pin the exact artifact consumed by the restore drill.
$BackupHash = (Get-FileHash -LiteralPath $FinalBackupFile -Algorithm SHA256).Hash.ToLowerInvariant()
$ChecksumFile = "$FinalBackupFile.sha256"
$ChecksumLine = "$BackupHash  $(Split-Path -Leaf $FinalBackupFile)$([Environment]::NewLine)"
[System.IO.File]::WriteAllText(
    $ChecksumFile,
    $ChecksumLine,
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "✓ SHA-256: $BackupHash"
Write-Host "  Checksum: $ChecksumFile"

# Clean up old backups
Write-Host "`nCleaning up old backups (retention: $RetentionDays days)..."
try {
    $CutoffDate = (Get-Date).AddDays(-$RetentionDays)
    $OldBackups = Get-ChildItem -Path $BackupDir -Filter "infohub_ai_*.sql*" |
                  Where-Object { $_.LastWriteTime -lt $CutoffDate }
    
    if ($OldBackups) {
        foreach ($file in $OldBackups) {
            Remove-Item -LiteralPath $file.FullName -Force
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
Write-Host "Backup: $FinalBackupFile"
Write-Host "SHA-256: $BackupHash"
$AllBackups = Get-ChildItem -Path $BackupDir -Filter "infohub_ai_*.sql*"
Write-Host "Total backup artifacts: $($AllBackups.Count)"
Write-Host "======================================`n"
