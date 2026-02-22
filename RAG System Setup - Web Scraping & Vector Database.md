# Цель
Настроить полноценную RAG (Retrieval-Augmented Generation) систему для InfoHub AI Tax Advisor:
* Запустить web scraper для сбора документов с infohub.ge
* Обработать и загрузить документы в ChromaDB
* Настроить поиск и проверить работу RAG
# Текущее состояние
## Что есть
* ✅ ChromaDB запущен в Docker (volume: ai_models)
* ✅ Embedding model работает: paraphrase-multilingual-mpnet-base-v2 (768 dimensions)
* ✅ InfoHubScraper реализован: backend/scraper/infohub_scraper.py
* ✅ RAG pipeline в коде: backend/rag/vector_store.py
* ✅ Backend интеграция: backend/api/v1/endpoints/public.py использует retrieval
## Проблема
* ❌ ChromaDB содержит 0 документов
* ❌ AI отвечает только на основе GPT-4 knowledge, без RAG
* ❌ Scraper никогда не запускался
# Предлагаемое решение
## Этап 1: Анализ и подготовка
1. Проверить InfoHubScraper:
    * Изучить backend/scraper/infohub_scraper.py
    * Проверить зависимости (requests, beautifulsoup4, lxml)
    * Убедиться что target URL правильный (infohub.ge vs infohub.rs.ge)
2. Проверить структуру данных:
    * Какой формат документов ожидает ChromaDB
    * Настройки chunking (размер чанков, overlap)
    * Metadata fields для фильтрации
## Этап 2: Запуск Web Scraper
1. Создать management скрипт для запуска scraper:
    * backend/scripts/populate_vector_db.py
    * Логирование прогресса
    * Обработка ошибок
2. Запустить scraper на production сервере:
    * SSH к серверу (46.224.145.5)
    * Выполнить скрипт внутри backend container
    * Мониторить прогресс (может занять несколько часов)
3. Параметры scraping:
    * Max pages (ограничить если сайт большой)
    * Rate limiting (не перегружать целевой сайт)
    * Retry logic
    * Language detection (Georgian, Russian, English)
## Этап 3: Обработка документов
1. Document chunking:
    * Chunk size: ~500-1000 tokens
    * Overlap: 100-200 tokens
    * Сохранять metadata (URL, title, language, date)
2. Generate embeddings:
    * Batch processing для скорости
    * Проверить GPU доступность
    * Progress tracking
3. Загрузка в ChromaDB:
    * Batch inserts (100-1000 документов)
    * Проверить indexing
    * Verify count после загрузки
## Этап 4: Настройка поиска
1. Оптимизация retrieval:
    * Top K документов (default: 5-10)
    * Similarity threshold (min relevance score)
    * Metadata filtering (по языку, по дате)
2. Тестирование:
    * Тестовые запросы на Georgian, Russian, English
    * Проверить relevance scores
    * Убедиться что sources возвращаются
## Этап 5: Валидация системы
1. API тесты:
    * curl запросы к /api/v1/public/query
    * Проверить response.sources заполнены
    * Проверить retrieved_count > 0
2. Frontend тесты:
    * Зайти на [https://tax-advisor.ge](https://tax-advisor.ge)
    * Задать вопрос про ДГВ/VAT
    * Убедиться что отображаются источники
3. Quality checks:
    * Релевантность ответов
    * Корректность цитирования источников
    * Проверка на разных языках
## Этап 6: Мониторинг и поддержка
1. Создать cron job для периодического обновления:
    * Scrape новых документов (weekly/monthly)
    * Update embeddings если документы изменились
2. Логирование:
    * Сколько документов в базе
    * Топ запросов пользователей
    * Failed queries
# Технические детали
## Scraper
* File: backend/scraper/infohub_scraper.py
* Target: [https://infohub.ge](https://infohub.ge) (пользователь упомянул infohub.rs.ge - нужно уточнить)
* Features: language detection (ka/ru/en), metadata extraction
## Vector Store
* DB: ChromaDB
* Location: Docker volume 'ai_models'
* Embedding model: sentence-transformers/paraphrase-multilingual-mpnet-base-v2
* Dimensions: 768
## Backend Integration
* Endpoint: /api/v1/public/query
* Process: query → embedding → similarity search → retrieve docs → send to GPT-4 → response
* Current problem: 0 docs = skip retrieval
# Риски и ограничения
1. Время scraping:
    * Может занять несколько часов если сайт большой
    * Нужен rate limiting чтобы не заблокировали
2. Storage:
    * Embeddings занимают много места
    * Нужно проверить disk space на сервере
3. Качество данных:
    * Если на infohub.ge мало документов, ответы будут неполные
    * Нужна валидация структуры сайта перед scraping
4. Legal:
    * Убедиться что scraping разрешён (robots.txt, ToS)
    * Уважать rate limits
# Следующие шаги
1. Получить подтверждение от пользователя:
    * Правильный ли URL: infohub.ge или infohub.rs.ge?
    * Есть ли доступ к серверу (SSH)?
    * Сколько времени можно выделить на scraping?
2. Начать с Этапа 1: анализ кода scraper
3. Запустить тестовый scrape на нескольких страницах
4. Если ОК → полный scrape + загрузка в ChromaDB
