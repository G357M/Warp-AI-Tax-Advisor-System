> **Актуальное production-состояние:** см. `docs/CURRENT_STATE.md`

# 🚀 Installation Guide - tax-advisor.ge / InfoHub

## Quick Start (Test Mode)

Если нужно быстро протестировать UI и API без AI:

```bash
# 1. Установить минимальные зависимости
pip install fastapi uvicorn[standard] pydantic

# 2. Запустить тестовый сервер
python test_server.py

# 3. В другом терминале - запустить frontend
cd frontend
npm install
npm run dev
```

**Результат:** 
- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- Admin Panel: http://localhost:3000/admin

---

## Full Installation (Production Mode)

### Шаг 1: Обновить pip

```bash
python -m pip install --upgrade pip
```

### Шаг 2: Установить Core Dependencies

```bash
pip install fastapi uvicorn[standard] pydantic pydantic-settings python-dotenv
pip install "pydantic[email]"
pip install sqlalchemy psycopg2-binary redis
pip install python-jose[cryptography] passlib[bcrypt] bcrypt
pip install prometheus-client psutil
```

### Шаг 3: Установить AI/ML Libraries

⚠️ **Внимание:** Это займет 5-10 минут и требует ~3GB места

```bash
pip install sentence-transformers torch
pip install openai
pip install langchain langchain-core langchain-openai
```

### Шаг 4: Установить Optional Dependencies

```bash
# Web scraping (optional)
pip install beautifulsoup4 requests aiohttp

# Testing (optional)
pip install pytest pytest-asyncio pytest-cov locust
```

### Шаг 5: Настроить Environment Variables

Создать `.env` файл:

```bash
# Database
DATABASE_URL=postgresql://infohub_user:changeme@localhost:5432/infohub_ai

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI
OPENAI_API_KEY=your-api-key-here

# JWT
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# App
APP_NAME=InfoHub AI Tax Advisor
APP_VERSION=1.0.0
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO

# API
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=["http://localhost:3000"]
```

### Шаг 6: Установить Services

**Windows (Docker Desktop):**

```bash
# Install PostgreSQL and Redis via Docker
docker run -d --name infohub-postgres -e POSTGRES_USER=infohub_user -e POSTGRES_PASSWORD=changeme -e POSTGRES_DB=infohub_ai -p 5432:5432 postgres:15

docker run -d --name infohub-redis -p 6379:6379 redis:7-alpine
```

**Или локально:**
- PostgreSQL: https://www.postgresql.org/download/windows/
- Redis: https://github.com/microsoftarchive/redis/releases

### Шаг 7: Initialize Database

```bash
python -m backend.core.database
```

### Шаг 8: Запустить Систему

```bash
# Terminal 1 - Backend
python -m backend.api.main

# Terminal 2 - Frontend
cd frontend
npm install
npm run dev
```

---

## Troubleshooting

### Проблема: ModuleNotFoundError

**Решение:** Установить отсутствующий модуль

```bash
pip install <module-name>
```

### Проблема: Database connection failed

**Решение:** Проверить что PostgreSQL запущен

```bash
# Check PostgreSQL status
docker ps | grep postgres

# Or restart
docker restart infohub-postgres
```

### Проблема: Redis connection failed

**Решение:** Проверить что Redis запущен

```bash
# Check Redis status
docker ps | grep redis

# Or restart
docker restart infohub-redis
```

### Проблема: Model download takes too long

**Решение:** Модель sentence-transformers загружается при первом запуске (~500MB). Это происходит один раз.

Можно установить HuggingFace токен для быстрой загрузки:

```bash
# Set HuggingFace token
set HF_TOKEN=your-token-here
```

### Проблема: Pillow build error

**Решение:** Pillow не критичен для базовой работы. Можно пропустить.

Или установить Visual C++ Build Tools:
https://visualstudio.microsoft.com/visual-cpp-build-tools/

---

## System Requirements

### Minimum:
- Python 3.11+
- 4GB RAM
- 10GB disk space
- Internet connection (first run)

### Recommended:
- Python 3.12+
- 8GB+ RAM
- 20GB+ disk space
- SSD storage
- GPU (optional, for faster embeddings)

---

## Verification

### Test Backend:

```bash
# Check health
curl http://localhost:8000/health

# Check API docs
# Open: http://localhost:8000/docs
```

### Test Frontend:

```bash
# Open: http://localhost:3000
```

### Test Admin Panel:

```bash
# Open: http://localhost:3000/admin
```

---

## Next Steps

1. **Load test documents:**
   ```bash
   python -m backend.scripts.load_test_data
   ```

2. **Run tests:**
   ```bash
   pytest backend/tests/ -v
   ```

3. **Start scraper:**
   - Go to Admin Panel > Scraper
   - Enter URL: https://infohub.rs.ge/ka
   - Click "Start Scraping"

4. **Monitor metrics:**
   - Metrics: http://localhost:8000/metrics
   - Setup Grafana: Import `monitoring/grafana-dashboard.json`

---

## Common Commands

```bash
# Install all requirements (may fail on some packages)
pip install -r backend/requirements.txt

# Install only critical packages
pip install fastapi uvicorn[standard] pydantic sqlalchemy redis python-jose passlib bcrypt

# Run tests
pytest backend/tests/ -v

# Run load tests
locust -f backend/tests/load_test.py --host=http://localhost:8000

# Format code
black backend/
isort backend/

# Type checking
mypy backend/
```

---

## Development Mode

```bash
# Backend with auto-reload
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# Frontend with hot reload
cd frontend
npm run dev
```

---

## Production Deployment

See `PRODUCTION_READINESS.md` for full production deployment guide.

Quick deploy:

```bash
# Build Docker images
docker-compose build

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f
```

---

## Support

- **Documentation:** See `README.md`, `PROJECT_STATUS.md`, `100_PERCENT_COMPLETE.md`
- **API Docs:** http://localhost:8000/docs
- **Issues:** https://github.com/G357M/Warp-AI-Tax-Advisor-System/issues

---

**Built with ❤️ by Warp AI Assistant**
