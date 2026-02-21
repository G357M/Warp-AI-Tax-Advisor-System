# InfoHub RAG System - Web Scraping Setup

Инструкции по настройке автоматического scraping для наполнения векторной базы данных.

## 📋 Обзор

Система scraping предназначена для:
- Сбора налоговых документов с infohub.rs.ge
- Обработки и создания embeddings
- Загрузки в ChromaDB для RAG
- Автоматического ежедневного обновления

## 🚀 Быстрый старт

### 1. Тестовый запуск (локально)

Запустить тестовый scrape на 5 страницах:

```bash
cd backend
python scripts/populate_vector_db.py --max-pages 5 --initial-run
```

Проверить результаты:

```bash
# Показать состояние scraper
python scripts/populate_vector_db.py --show-state

# Проверить количество документов в vector store
python -c "from rag.vector_store import vector_store; print(f'Documents: {vector_store.get_count()}')"
```

### 2. Развёртывание на сервере (Hetzner)

#### SSH к серверу

```bash
ssh root@46.224.145.5
cd /root/infohub
```

#### Копировать скрипты на сервер

```bash
# На локальной машине (Windows)
scp backend/scripts/populate_vector_db.py root@46.224.145.5:/root/infohub/backend/scripts/
scp backend/scripts/setup_cron.sh root@46.224.145.5:/root/infohub/backend/scripts/
```

Или через Git:

```bash
# На сервере
cd /root/infohub
git pull origin main
```

#### Настроить cron job

```bash
# На сервере
cd /root/infohub/backend/scripts
chmod +x setup_cron.sh
./setup_cron.sh
```

Это создаст:
- `/root/infohub/run_scraper.sh` - обёртка для запуска scraper
- Cron job, запускающийся каждый день в 3:00 AM
- Директорию `/root/infohub/logs/` для логов

#### Тестовый запуск на сервере

```bash
# Запустить вручную
/root/infohub/run_scraper.sh

# Или через docker exec напрямую
docker exec infohub-backend-1 python /app/scripts/populate_vector_db.py --max-pages 10 --initial-run
```

## 🔧 Параметры scraping

### Параметры скрипта

```bash
python scripts/populate_vector_db.py [OPTIONS]
```

Опции:
- `--start-url URL` - начальный URL (default: https://infohub.rs.ge/ka)
- `--max-pages N` - макс. страниц за запуск (default: 50)
- `--max-depth N` - макс. глубина ссылок (default: 2)
- `--initial-run` - начать с нуля, игнорируя состояние
- `--show-state` - показать текущее состояние и выйти

### Примеры

```bash
# Первый запуск - 10 страниц для теста
python scripts/populate_vector_db.py --max-pages 10 --initial-run

# Ежедневный incremental - 50 страниц
python scripts/populate_vector_db.py --max-pages 50

# Показать состояние
python scripts/populate_vector_db.py --show-state

# Большой batch - 200 страниц
python scripts/populate_vector_db.py --max-pages 200
```

## 📊 Мониторинг

### Проверить состояние scraper

```bash
# Показать JSON с состоянием
python scripts/populate_vector_db.py --show-state

# Или прочитать файл напрямую
cat backend/data/scraper_state.json
```

Состояние включает:
- `visited_urls` - список обработанных URL
- `last_run` - дата последнего запуска
- `total_documents` - всего документов собрано
- `total_pages_scraped` - всего страниц обработано
- `runs` - история последних 30 запусков

### Проверить логи на сервере

```bash
# Логи cron
tail -f /root/infohub/logs/cron.log

# Логи отдельных запусков
ls -lh /root/infohub/logs/scraper_*.log
tail -f /root/infohub/logs/scraper_$(ls -t /root/infohub/logs/scraper_*.log | head -1)

# Логи внутри контейнера
docker exec infohub-backend-1 tail -f /app/logs/scraper.log
```

### Проверить vector store

```bash
# Через docker exec
docker exec infohub-backend-1 python -c "from rag.vector_store import vector_store; print(f'Documents in ChromaDB: {vector_store.get_count()}')"

# Проверить через API
curl https://tax-advisor.ge/api/v1/public/query \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"query":"რა არის დღგ?", "language":"ka"}'
```

### Проверить cron job

```bash
# Показать текущие cron jobs
crontab -l

# Редактировать cron jobs
crontab -e
```

## 🛠️ Настройка rate limiting

Изменить rate limiting в `.env`:

```bash
# Задержка между запросами (секунды)
SCRAPER_DELAY=3.0  # увеличить если блокируют

# Уважать robots.txt
SCRAPER_RESPECT_ROBOTS_TXT=true

# User agent
SCRAPER_USER_AGENT=InfoHubAI-Bot/1.0
```

Или изменить в `run_scraper.sh`:

```bash
MAX_PAGES=50  # уменьшить для более медленного scraping
```

## 📈 Стратегия scraping

### Incremental approach

1. **День 1**: Запуск с `--initial-run`, обработка 50 страниц
2. **День 2-N**: Автоматический запуск через cron, 50 новых страниц каждый день
3. **State tracking**: Скрипт запоминает обработанные URL, не дублирует
4. **Rate limiting**: 2-5 сек между запросами (настраивается в `.env`)

### Рекомендации

- **Начать медленно**: 10-20 страниц для теста
- **Мониторить**: Проверять логи первые несколько дней
- **Увеличивать постепенно**: Если всё ОК, увеличить до 50-100 страниц/день
- **Проверять качество**: Убедиться что документы релевантны

## 🐛 Troubleshooting

### Scraper не запускается

```bash
# Проверить зависимости
docker exec infohub-backend-1 python -c "import aiohttp, bs4, sqlalchemy; print('OK')"

# Проверить доступ к infohub.rs.ge
curl -I https://infohub.rs.ge/ka

# Проверить robots.txt
curl https://infohub.rs.ge/robots.txt
```

### ChromaDB не подключается

```bash
# Проверить контейнер ChromaDB
docker ps | grep chroma

# Проверить настройки в .env
docker exec infohub-backend-1 env | grep CHROMA

# Проверить подключение
docker exec infohub-backend-1 python -c "from rag.vector_store import vector_store; print(vector_store.client)"
```

### Нет embeddings

```bash
# Проверить модель
docker exec infohub-backend-1 python -c "from rag.embeddings import embeddings_generator; print(embeddings_generator.model)"

# Проверить GPU/CPU
docker exec infohub-backend-1 nvidia-smi  # if GPU
docker exec infohub-backend-1 python -c "import torch; print(torch.cuda.is_available())"
```

### Cron не запускается

```bash
# Проверить cron service
systemctl status cron

# Проверить права
ls -l /root/infohub/run_scraper.sh

# Проверить логи cron
grep CRON /var/log/syslog
tail -f /root/infohub/logs/cron.log
```

## 🔄 Обновление

### Обновить код scraper

```bash
# На сервере
cd /root/infohub
git pull origin main

# Перезапустить backend
docker-compose up -d --force-recreate backend
```

### Сбросить состояние scraper

```bash
# На сервере
rm -f /root/infohub/backend/data/scraper_state.json

# Или через docker
docker exec infohub-backend-1 rm -f /app/data/scraper_state.json
```

## 📝 Структура файлов

```
backend/
├── scripts/
│   ├── populate_vector_db.py    # Главный скрипт scraping
│   ├── setup_cron.sh             # Настройка cron job
│   └── README_SCRAPING.md        # Эта инструкция
├── data/
│   └── scraper_state.json        # Состояние scraper (auto-generated)
├── scraper/
│   ├── base_scraper.py           # Базовый класс с rate limiting
│   └── infohub_scraper.py        # InfoHub-специфичный scraper
└── logs/
    └── scraper.log               # Логи scraping

На сервере:
/root/infohub/
├── run_scraper.sh                # Обёртка для cron
└── logs/
    ├── cron.log                  # Логи cron
    └── scraper_YYYYMMDD_HHMMSS.log  # Логи отдельных запусков
```

## 🎯 Next Steps

1. ✅ Обновить base_url в InfoHubScraper → `https://infohub.rs.ge`
2. ✅ Создать скрипт `populate_vector_db.py` с state tracking
3. ✅ Создать `setup_cron.sh` для автоматизации
4. 🔄 Протестировать на 5-10 страницах
5. 🔄 Развернуть на сервере
6. 🔄 Настроить cron job
7. 🔄 Мониторить первые несколько дней
8. 🔄 Проверить качество RAG ответов
