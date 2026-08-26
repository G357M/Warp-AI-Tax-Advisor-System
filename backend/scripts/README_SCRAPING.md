# tax-advisor.ge / InfoHub - Web Scraping Setup

Инструкции по настройке scraping/export для наполнения production corpus и pgvector-индекса.

## 📋 Обзор

Система scraping предназначена для:
- Сбора налоговых документов с infohub.rs.ge
- Обработки и создания embeddings
- Загрузки в PostgreSQL/pgvector для RAG
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

# Проверить количество документов/чанков в vector store facade
python -c "from rag.vector_store import vector_store; print(f'Indexed chunks/documents: {vector_store.get_count()}')"
```

### 2. Развёртывание на сервере (Hetzner)

#### SSH к серверу

```bash
ssh root@46.224.145.5
cd /root/infohub
```

#### Обновить скрипты на сервере

Используйте только проверенный Git/deploy-путь; `setup_cron.sh` больше не
создаёт и не перезаписывает ingestion runner.

```bash
# На сервере
cd /root/infohub
git pull origin main
```

#### Настроить cron job

```bash
# На сервере
cd /root/infohub
bash scripts/configure_ingestion_schedule.sh --dry-run
bash scripts/configure_ingestion_schedule.sh --apply
```

Скрипт сохраняет unrelated cron entries и mode-600 backup предыдущего
crontab. Полный nightly остаётся в 03:00 UTC. Лёгкие `--ingest-only` refresh
запускаются в 09:17, 15:17 и 21:17 UTC; они не выполняют LLM maintenance и
RAG canary. Все режимы используют общий `flock`, поэтому не пересекаются.

#### Тестовый запуск на сервере

```bash
# Запустить вручную
/root/infohub/run_scraper.sh

# Только ingestion + freshness audit, без ночных LLM/quality стадий
/root/infohub/run_scraper.sh --ingest-only

# Не запускайте storage-команду напрямую во время cron: singleton lock живёт
# на host wrapper.
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
docker exec infohub-backend-1 python -c "from rag.vector_store import vector_store; print(f'Indexed rows via vector facade: {vector_store.get_count()}')"

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

### pgvector / vector facade не подключается

```bash
# Отдельного ChromaDB контейнера в production нет
# Проверьте postgres/pgvector и backend env
docker ps | egrep "infohub-postgres|infohub-backend"

# Проверить настройки backend
docker exec infohub-backend-1 env | egrep "DATABASE_URL|VECTOR_DB_TYPE"

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

## Scrapling operational status (2026-05-07)

Targeted live audits on the real `tax-advisor.ge` corpus did **not** justify promoting Scrapling to a preferred extractor. This includes:
- long `law` / `regulation`
- short/card-like `news`
- metadata-heavy anomaly patterns
- hard short-document outliers

Operational decision:
- keep Scrapling as **audit / debug / fallback / repair** tooling
- keep the native InfoHub extraction path as the **primary** production path
- do **not** roll Scrapling out as the default extractor unless a new, concrete production failure pattern appears

See also:
- `docs/SCRAPLING_AUDIT_SUMMARY_2026-05-07.md`
- `docs/CURRENT_STATE.md`

## Scrapling pilot path

В проект добавлен **pilot/fallback extractor** на базе Scrapling:
- `backend/scraper/scrapling_scraper.py`
- `backend/scripts/scrapling_probe.py`

### Зачем он нужен
Не как замена основному ingestion pipeline, а как вспомогательный слой для:
- repair extraction проблемных документов;
- audit/debug, когда нужно сравнить source page и наш normalized corpus;
- fallback extraction, если текущий parser даёт шумный или неполный текст.

### Что он делает сейчас
- использует текущий `aiohttp` fetch path;
- прогоняет HTML через `scrapling.parser.Selector`;
- пытается взять лучший контейнер (`main`, `article`, `.content`, `body` и т.д.);
- возвращает очищенный текст, заголовок и extraction mode.

### Быстрый тест

```bash
cd /root/infohub/backend
python scripts/scrapling_probe.py "https://infohub.rs.ge/ka/workspace/document/800cbef0-32bf-4f06-94fe-8afd2bf144a0"
```
