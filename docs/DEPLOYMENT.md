# Руководство по развертыванию InfoHub.ge AI Tax Advisor

## Содержание
1. [Предварительные требования](#предварительные-требования)
2. [Локальное развертывание](#локальное-развертывание)
3. [Docker развертывание](#docker-развертывание)
4. [Production развертывание](#production-развертывание)
5. [Конфигурация](#конфигурация)
6. [Мониторинг](#мониторинг)
7. [Troubleshooting](#troubleshooting)

## Предварительные требования

### Для локального развертывания
- Python 3.11 или выше
- Node.js 18 или выше
- PostgreSQL 15+
- Redis 7+
- Git

### Для Docker развертывания
- Docker 24.0+
- Docker Compose 2.20+
- 16GB RAM (минимум)
- 50GB свободного места на диске

### Для Production
- Linux сервер (Ubuntu 22.04 LTS рекомендуется)
- 32GB RAM (рекомендуется)
- 200GB SSD
- Доменное имя
- SSL сертификаты

## Локальное развертывание

### 1. Клонирование репозитория

```bash
git clone https://github.com/yourusername/infohub-ai-tax-advisor.git
cd infohub-ai-tax-advisor
```

### 2. Backend Setup

```bash
# Перейти в директорию backend
cd backend

# Создать виртуальное окружение
python -m venv venv

# Активировать окружение
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt

# Установить spaCy модели
python -m spacy download en_core_web_sm
python -m spacy download ru_core_news_sm
```

### 3. Настройка базы данных

```bash
# Создать PostgreSQL базу данных
createdb infohub_ai

# Или через psql:
psql -U postgres
CREATE DATABASE infohub_ai;
CREATE USER infohub_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE infohub_ai TO infohub_user;
\q
```

### 4. Конфигурация окружения

```bash
# Копировать пример конфигурации
cp .env.example .env

# Отредактировать .env файл
nano .env
```

Минимальная конфигурация:
```env
DATABASE_URL=postgresql://infohub_user:your_password@localhost:5432/infohub_ai
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=your_openai_key
SECRET_KEY=generate_random_secret_key
```

### 5. Выполнение миграций

```bash
# Инициализация Alembic (если еще не инициализирован)
alembic init alembic

# Выполнить миграции
alembic upgrade head

# Или использовать скрипт
python scripts/migrate.py
```

### 6. Запуск Backend

```bash
# Development режим
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Или
python -m api.main
```

### 7. Frontend Setup

```bash
# Открыть новый терминал
cd frontend

# Установить зависимости
npm install

# Создать .env.local
cp .env.example .env.local

# Настроить API URL
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Запустить dev сервер
npm run dev
```

### 8. Запуск Workers (опционально)

```bash
# Открыть новый терминал
cd backend
source venv/bin/activate  # или venv\Scripts\activate на Windows

# Запустить Celery worker
celery -A scraper.tasks worker --loglevel=info

# Запустить Celery beat (в другом терминале)
celery -A scraper.tasks beat --loglevel=info

# Запустить Flower для мониторинга (в другом терминале)
celery -A scraper.tasks flower --port=5555
```

### 9. Проверка установки

Откройте в браузере:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/docs
- Flower: http://localhost:5555

## Docker развертывание

### 1. Подготовка

```bash
# Клонировать репозиторий
git clone https://github.com/yourusername/infohub-ai-tax-advisor.git
cd infohub-ai-tax-advisor

# Создать .env файл
cp .env.example .env
nano .env
```

### 2. Настройка .env

```env
# Обязательные настройки
POSTGRES_PASSWORD=strong_password_here
OPENAI_API_KEY=your_openai_key
SECRET_KEY=your_secret_key
CHROMA_AUTH_TOKEN=random_token_here
```

### 3. Сборка и запуск

```bash
# Перейти в директорию docker
cd docker

# Сборка образов
docker-compose build

# Запуск всех сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f
```

### 4. Инициализация базы данных

```bash
# Выполнить миграции
docker-compose exec backend alembic upgrade head

# Создать admin пользователя
docker-compose exec backend python scripts/create_admin.py
```

### 5. Первичный сбор данных

```bash
# Запустить scraping
docker-compose exec backend python scripts/scrape.py --initial

# Или через API (если backend запущен)
curl -X POST http://localhost:8080/api/v1/admin/scrape \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 6. Остановка и обновление

```bash
# Остановка всех сервисов
docker-compose down

# Остановка с удалением volumes (ВНИМАНИЕ: удалит все данные)
docker-compose down -v

# Обновление и перезапуск
git pull
docker-compose build
docker-compose up -d
```

## Production развертывание

### 1. Подготовка сервера

```bash
# Обновить систему
sudo apt update && sudo apt upgrade -y

# Установить зависимости
sudo apt install -y docker.io docker-compose nginx certbot python3-certbot-nginx

# Настроить firewall
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

### 2. Клонирование и настройка

```bash
# Создать директорию для приложения
sudo mkdir -p /opt/infohub-ai
sudo chown $USER:$USER /opt/infohub-ai
cd /opt/infohub-ai

# Клонировать репозиторий
git clone https://github.com/yourusername/infohub-ai-tax-advisor.git .

# Создать production .env
cp .env.example .env
nano .env
```

### 3. Production конфигурация

```env
# Environment
ENVIRONMENT=production
DEBUG=false

# Security
SECRET_KEY=generate_with_openssl_rand_hex_32
JWT_SECRET_KEY=generate_another_random_key

# Database
POSTGRES_PASSWORD=strong_random_password

# API Keys
OPENAI_API_KEY=your_production_key

# Domain
DOMAIN=yourdomain.com
```

### 4. SSL сертификаты

```bash
# Получить SSL сертификат
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Автоматическое обновление
sudo certbot renew --dry-run
```

### 5. Nginx конфигурация

```bash
# Создать конфигурацию Nginx
sudo nano /etc/nginx/sites-available/infohub-ai
```

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
```

```bash
# Активировать конфигурацию
sudo ln -s /etc/nginx/sites-available/infohub-ai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 6. Запуск в production

```bash
# Перейти в директорию docker
cd /opt/infohub-ai/docker

# Сборка production образов
docker-compose -f docker-compose.prod.yml build

# Запуск
docker-compose -f docker-compose.prod.yml up -d

# Проверка
docker-compose -f docker-compose.prod.yml ps
```

### 7. Systemd service (опционально)

```bash
# Создать systemd service
sudo nano /etc/systemd/system/infohub-ai.service
```

```ini
[Unit]
Description=InfoHub AI Tax Advisor
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/infohub-ai/docker
ExecStart=/usr/bin/docker-compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker-compose -f docker-compose.prod.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
# Активировать service
sudo systemctl daemon-reload
sudo systemctl enable infohub-ai
sudo systemctl start infohub-ai
```

## Мониторинг

### 1. Health Checks

```bash
# Backend health
curl http://localhost:8080/health

# Database connection
docker-compose exec postgres pg_isready

# Redis
docker-compose exec redis redis-cli ping
```

### 2. Логи

```bash
# Все логи
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f backend

# Последние 100 строк
docker-compose logs --tail=100 backend
```

### 3. Metrics

- Prometheus: http://localhost:9090
- Grafana: Настроить отдельно
- Flower: http://localhost:5555

### 4. Backup

```bash
# Backup базы данных
docker-compose exec postgres pg_dump -U infohub_user infohub_ai > backup_$(date +%Y%m%d).sql

# Backup volumes
docker run --rm -v infohub_postgres_data:/data -v $(pwd):/backup ubuntu tar czf /backup/postgres_data_$(date +%Y%m%d).tar.gz /data
```

## Troubleshooting

### Backend не запускается

```bash
# Проверить логи
docker-compose logs backend

# Проверить переменные окружения
docker-compose exec backend env | grep DATABASE_URL

# Проверить подключение к БД
docker-compose exec backend python -c "from core.database import engine; print(engine.url)"
```

### Ошибки базы данных

```bash
# Пересоздать базу
docker-compose down
docker volume rm infohub_postgres_data
docker-compose up -d postgres
docker-compose exec backend alembic upgrade head
```

### Проблемы с векторной БД

```bash
# Перезапустить ChromaDB
docker-compose restart chromadb

# Очистить и переиндексировать
docker-compose exec backend python scripts/reindex.py
```

### Медленная работа

```bash
# Проверить использование ресурсов
docker stats

# Увеличить лимиты в docker-compose.yml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
```

### Проблемы с scraping

```bash
# Проверить логи scraper
docker-compose logs celery-worker

# Запустить вручную
docker-compose exec backend python scripts/scrape.py --verbose

# Проверить доступность infohub.ge
curl -I https://infohub.ge
```

## Обновление

### Minor updates

```bash
git pull
docker-compose build
docker-compose up -d
```

### Major updates с миграциями

```bash
# Backup
./scripts/backup.sh

# Остановить сервисы
docker-compose down

# Обновить код
git pull

# Сборка
docker-compose build

# Миграции
docker-compose up -d postgres redis
docker-compose exec backend alembic upgrade head

# Запуск всех сервисов
docker-compose up -d
```

## Контакты и поддержка

- Email: support@yourcompany.com
- Issues: https://github.com/yourusername/infohub-ai-tax-advisor/issues
- Documentation: https://docs.yourcompany.com
