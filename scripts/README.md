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

### backup.sh
Backup database and volumes.

```bash
./scripts/backup.sh
```
