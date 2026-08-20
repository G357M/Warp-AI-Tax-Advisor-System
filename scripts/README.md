# Scripts

Utility scripts for project management and operations.

## Available Scripts

### setup.py
Initialize the project and create database tables.

```bash
python scripts/setup.py
```

This script will:
- Verify database connection
- Create all required tables
- Create a default admin user (username: admin, password: changeme)

**Important**: Change the admin password after first setup!

## Future Scripts

### scrape.py
Run the InfoHub spider manually.

```bash
python scripts/scrape.py [--initial]
```

### migrate.py
Run database migrations.

```bash
python scripts/migrate.py
```

### reindex.py
Reindex all documents in the vector database.

```bash
python scripts/reindex.py
```

### backup_database.ps1
Create and rotate the owner-side PostgreSQL backup.

Configure credentials outside the repository with `PGPASSWORD`, `PGPASSFILE`
or the standard pgpass file. The script is non-interactive and emits a SHA-256
sidecar for the exact final artifact.

```powershell
./scripts/backup_database.ps1
```

### test_database_restore.sh
Plan and execute a SHA-pinned restore into an isolated disposable PostgreSQL
container. This never targets production resources.

```bash
./scripts/test_database_restore.sh --backup /restricted/path/infohub_ai.sql.gz
```
