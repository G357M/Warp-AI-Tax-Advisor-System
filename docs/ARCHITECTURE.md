# Архитектура системы InfoHub.ge AI Tax Advisor

## Обзор

Система построена на микросервисной архитектуре с использованием современных технологий AI/ML для обеспечения интеллектуального поиска и консультирования по налоговому законодательству Грузии.

## Архитектурные принципы

1. **Модульность**: Каждый компонент независим и может быть заменен
2. **Масштабируемость**: Горизонтальное масштабирование всех слоев
3. **Отказоустойчивость**: Graceful degradation при сбоях
4. **Безопасность**: Security by design на всех уровнях
5. **Наблюдаемость**: Полное логирование и мониторинг

## Слои системы

### 1. Data Collection Layer (Слой сбора данных)

#### Компоненты:
- **Web Scraper Service**
- **Document Downloader**
- **Change Detector**
- **Scheduler**

#### Технологии:
- Scrapy Framework для web scraping
- BeautifulSoup4 для парсинга HTML
- Selenium для динамического контента
- Celery Beat для планирования задач

#### Процесс работы:
```
┌─────────────┐
│  Scheduler  │
└──────┬──────┘
       │
       v
┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│   Scrapy    │─────>│  Document    │─────>│   Raw Data   │
│   Spider    │      │  Downloader  │      │    Storage   │
└─────────────┘      └──────────────┘      └──────────────┘
       │
       v
┌─────────────┐
│   Change    │
│  Detector   │
└─────────────┘
```

#### Функциональность:
- Обход сайта infohub.ge с учетом структуры
- Извлечение документов различных типов
- Детекция изменений (инкрементальные обновления)
- Rate limiting и уважение к robots.txt
- Обработка ошибок и retry механизмы
- Сохранение метаданных о документах

#### Типы документов:
- Законы (საკანონმდებლო აქტები)
- Подзаконные акты
- Решения налоговой службы
- Судебные постановления
- Разъяснения и инструкции

### 2. Data Processing Layer (Слой обработки данных)

#### Компоненты:
- **Document Parser**
- **Metadata Extractor**
- **Text Chunker**
- **OCR Engine**
- **Language Detector**

#### Технологии:
- PyPDF2, pdfplumber для PDF
- python-docx для Word документов
- Tesseract OCR для сканов
- langdetect для определения языка
- spaCy для NLP задач

#### Процесс обработки:
```
┌───────────────┐
│  Raw Document │
└───────┬───────┘
        │
        v
┌───────────────┐      ┌──────────────┐
│    Format     │─────>│   Text       │
│   Detection   │      │ Extraction   │
└───────────────┘      └──────┬───────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        v                     v                     v
┌──────────────┐      ┌──────────────┐     ┌──────────────┐
│   Metadata   │      │     Text     │     │  Language    │
│  Extraction  │      │   Chunking   │     │  Detection   │
└──────┬───────┘      └──────┬───────┘     └──────┬───────┘
       │                     │                     │
       └─────────────────────┴─────────────────────┘
                             │
                             v
                    ┌────────────────┐
                    │   Structured   │
                    │     Data       │
                    └────────────────┘
```

#### Извлечение метаданных:
```python
{
    "document_id": "uuid",
    "title": "Название документа",
    "document_type": "law|regulation|court_decision|guideline",
    "document_number": "№123",
    "date_published": "2024-01-15",
    "date_effective": "2024-02-01",
    "language": "ka|ru|en",
    "category": "corporate_tax|vat|income_tax|other",
    "authority": "parliament|revenue_service|court|ministry",
    "status": "active|amended|repealed",
    "related_documents": ["doc_id_1", "doc_id_2"],
    "keywords": ["налог", "НДС", "декларация"],
    "source_url": "https://infohub.ge/...",
    "file_hash": "sha256_hash"
}
```

#### Text Chunking стратегия:
- **По семантическим блокам**: Статьи, параграфы, пункты
- **Overlapping chunks**: 10-20% overlap для контекста
- **Размер chunk**: 512-1024 tokens
- **Сохранение структуры**: Иерархия документа

### 3. Storage Layer (Слой хранения)

#### PostgreSQL Database Schema:

```sql
-- Документы
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    document_type VARCHAR(50) NOT NULL,
    document_number VARCHAR(100),
    date_published DATE,
    date_effective DATE,
    language VARCHAR(2) NOT NULL,
    category VARCHAR(50),
    authority VARCHAR(50),
    status VARCHAR(20) DEFAULT 'active',
    full_text TEXT,
    source_url TEXT,
    file_hash VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Индексы для быстрого поиска
CREATE INDEX idx_documents_type ON documents(document_type);
CREATE INDEX idx_documents_category ON documents(category);
CREATE INDEX idx_documents_date ON documents(date_published);
CREATE INDEX idx_documents_language ON documents(language);
CREATE INDEX idx_documents_status ON documents(status);

-- Full-text search
CREATE INDEX idx_documents_fulltext ON documents 
    USING gin(to_tsvector('russian', full_text));

-- Чанки документов
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    tokens_count INTEGER,
    start_position INTEGER,
    end_position INTEGER,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_chunks_document ON document_chunks(document_id);

-- Пользователи
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(20) DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP
);

-- Разговоры
CREATE TABLE conversations (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Сообщения
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL, -- 'user' or 'assistant'
    content TEXT NOT NULL,
    sources JSONB, -- Ссылки на документы
    created_at TIMESTAMP DEFAULT NOW()
);

-- Связи между документами
CREATE TABLE document_relations (
    id UUID PRIMARY KEY,
    source_doc_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    target_doc_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    relation_type VARCHAR(50), -- 'amends', 'references', 'repeals'
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Vector Database (ChromaDB):

```python
# Collection structure
collection_schema = {
    "name": "infohub_documents",
    "metadata": {
        "dimension": 768,  # embedding size
        "distance_metric": "cosine"
    }
}

# Document embedding
{
    "id": "chunk_uuid",
    "embedding": [0.123, -0.456, ...],  # 768-dim vector
    "metadata": {
        "document_id": "doc_uuid",
        "chunk_index": 0,
        "document_type": "law",
        "category": "vat",
        "language": "ka",
        "date_published": "2024-01-15"
    },
    "document": "Текст чанка..."
}
```

#### Redis Cache:

```python
# Структура кеша
cache_keys = {
    # Результаты запросов
    "query:{query_hash}": {
        "response": "...",
        "sources": [...],
        "ttl": 3600
    },
    
    # Частые документы
    "doc:{doc_id}": {
        "content": "...",
        "metadata": {...},
        "ttl": 7200
    },
    
    # Rate limiting
    "rate_limit:{user_id}": {
        "count": 10,
        "ttl": 60
    },
    
    # Session data
    "session:{session_id}": {
        "user_id": "...",
        "conversation_id": "...",
        "ttl": 1800
    }
}
```

### 4. AI/ML Layer (Слой искусственного интеллекта)

#### Embedding Model:

```python
# Multilingual embedding model
model_config = {
    "model_name": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    "dimension": 768,
    "supported_languages": ["ka", "ru", "en"],
    "max_sequence_length": 512
}

# Альтернативы для грузинского языка
alternative_models = [
    "intfloat/multilingual-e5-large",
    "BAAI/bge-m3",
    "Alibaba-NLP/gte-multilingual-base"
]
```

#### RAG Pipeline:

```python
# Полный RAG процесс
class RAGPipeline:
    def process_query(self, query: str, user_context: dict) -> Response:
        # 1. Query Understanding
        query_embedding = self.embed_query(query)
        query_intent = self.classify_intent(query)
        
        # 2. Retrieval
        relevant_chunks = self.vector_search(
            query_embedding,
            filters={
                "language": user_context.get("language", "ka"),
                "top_k": 10
            }
        )
        
        # 3. Reranking
        reranked_chunks = self.rerank(query, relevant_chunks)
        top_chunks = reranked_chunks[:5]
        
        # 4. Context Assembly
        context = self.assemble_context(top_chunks)
        
        # 5. Generation
        response = self.generate_response(
            query=query,
            context=context,
            conversation_history=user_context.get("history", [])
        )
        
        # 6. Citation
        cited_response = self.add_citations(response, top_chunks)
        
        return cited_response
```

#### LLM Integration:

```python
# Prompt template
system_prompt = """
Вы - AI-ассистент по налоговому законодательству Грузии. 
Ваша задача - предоставлять точную информацию на основе официальных документов.

Правила:
1. Отвечайте только на основе предоставленного контекста
2. Всегда указывайте источники информации
3. Если информации недостаточно - скажите об этом
4. Не придумывайте информацию
5. Используйте язык запроса пользователя для ответа

Контекст из базы данных:
{context}

История разговора:
{conversation_history}
"""

user_prompt = """
Вопрос пользователя: {query}

Предоставьте подробный ответ с указанием источников.
"""

# Model configuration
llm_config = {
    "model": "gpt-4-turbo-preview",  # или claude-3-opus-20240229
    "temperature": 0.3,  # Низкая для фактической точности
    "max_tokens": 2000,
    "top_p": 0.95
}
```

#### Reranking Strategy:

```python
# Cross-encoder для более точного ранжирования
reranker_config = {
    "model": "cross-encoder/ms-marco-MiniLM-L-12-v2",
    "batch_size": 32,
    "use_gpu": True
}

def rerank(query: str, candidates: List[Document]) -> List[Document]:
    # Пересчитываем релевантность с учетом семантики
    pairs = [(query, doc.content) for doc in candidates]
    scores = reranker_model.predict(pairs)
    
    # Сортируем по новым scores
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, score in ranked]
```

### 5. API Layer (Слой API)

#### REST API Endpoints:

```python
# Authentication
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/refresh
GET    /api/v1/auth/me

# Query endpoints
POST   /api/v1/query              # Основной endpoint для вопросов
POST   /api/v1/query/stream       # Streaming ответ
GET    /api/v1/conversations      # Список разговоров
GET    /api/v1/conversations/{id} # Конкретный разговор
DELETE /api/v1/conversations/{id} # Удалить разговор

# Documents
GET    /api/v1/documents          # Список документов (с фильтрами)
GET    /api/v1/documents/{id}     # Конкретный документ
GET    /api/v1/documents/search   # Поиск документов
GET    /api/v1/documents/{id}/related  # Связанные документы

# Admin endpoints
POST   /api/v1/admin/scrape       # Запустить scraping
GET    /api/v1/admin/scrape/status # Статус scraping
GET    /api/v1/admin/stats        # Статистика системы
GET    /api/v1/admin/users        # Управление пользователями
POST   /api/v1/admin/documents/reindex  # Переиндексация

# Health & Monitoring
GET    /health                    # Health check
GET    /metrics                   # Prometheus metrics
```

#### WebSocket для Streaming:

```python
@app.websocket("/ws/query")
async def websocket_query(websocket: WebSocket):
    await websocket.accept()
    
    while True:
        # Получаем запрос
        data = await websocket.receive_json()
        query = data["query"]
        
        # Streaming response
        async for chunk in rag_pipeline.stream_response(query):
            await websocket.send_json({
                "type": "chunk",
                "content": chunk
            })
        
        # Отправляем источники в конце
        await websocket.send_json({
            "type": "sources",
            "data": sources
        })
```

#### Middleware Stack:

```python
middleware_stack = [
    # Security
    CORSMiddleware(allow_origins=["*"]),
    TrustedHostMiddleware(allowed_hosts=["*"]),
    
    # Authentication
    JWTMiddleware(),
    
    # Rate Limiting
    RateLimitMiddleware(requests_per_minute=60),
    
    # Logging
    RequestLoggingMiddleware(),
    
    # Error Handling
    ErrorHandlerMiddleware(),
    
    # Compression
    GZipMiddleware(minimum_size=1000)
]
```

### 6. Frontend Layer

#### Next.js App Structure:

```
frontend/
├── app/
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── (chat)/
│   │   ├── page.tsx                 # Main chat interface
│   │   ├── history/page.tsx         # Conversation history
│   │   └── [id]/page.tsx           # Specific conversation
│   ├── (admin)/
│   │   ├── dashboard/page.tsx
│   │   ├── documents/page.tsx
│   │   └── users/page.tsx
│   ├── layout.tsx
│   └── api/                        # API routes
│       └── auth/[...nextauth]/route.ts
├── components/
│   ├── ui/                         # shadcn/ui components
│   ├── chat/
│   │   ├── ChatInterface.tsx
│   │   ├── MessageList.tsx
│   │   ├── MessageInput.tsx
│   │   └── SourceCard.tsx
│   └── admin/
│       ├── Dashboard.tsx
│       ├── DocumentList.tsx
│       └── UserManagement.tsx
└── lib/
    ├── api.ts                      # API client
    ├── hooks/                      # Custom hooks
    └── utils.ts
```

#### State Management:

```typescript
// React Query для server state
const useQuery = () => {
  return useQuery({
    queryKey: ['query', queryText],
    queryFn: () => api.query(queryText),
    staleTime: 5 * 60 * 1000, // 5 min
  });
};

// Zustand для client state
interface ChatStore {
  conversations: Conversation[];
  currentConversation: string | null;
  addMessage: (message: Message) => void;
  setConversation: (id: string) => void;
}

const useChatStore = create<ChatStore>((set) => ({
  conversations: [],
  currentConversation: null,
  addMessage: (message) => set((state) => ({
    conversations: state.conversations.map(conv =>
      conv.id === state.currentConversation
        ? { ...conv, messages: [...conv.messages, message] }
        : conv
    )
  })),
  setConversation: (id) => set({ currentConversation: id })
}));
```

## Data Flow

### Complete Query Flow:

```
1. User Input
   ↓
2. Frontend (Next.js)
   ↓
3. API Gateway (FastAPI)
   ↓
4. Authentication & Rate Limiting
   ↓
5. Query Preprocessing
   ↓
6. Cache Check (Redis)
   ├─ Hit → Return cached response
   └─ Miss → Continue
   ↓
7. Embedding Generation
   ↓
8. Vector Search (ChromaDB)
   ↓
9. Document Retrieval (PostgreSQL)
   ↓
10. Reranking
    ↓
11. Context Assembly
    ↓
12. LLM Generation (OpenAI/Anthropic)
    ↓
13. Citation Addition
    ↓
14. Cache Update (Redis)
    ↓
15. Response to User
    ↓
16. Save to Conversation History
```

### Scraping Flow:

```
1. Scheduler triggers scraping job
   ↓
2. Scrapy spider crawls infohub.ge
   ↓
3. Document download
   ↓
4. Change detection
   ├─ New document → Process
   ├─ Updated → Process & update
   └─ No change → Skip
   ↓
5. Document parsing
   ↓
6. Metadata extraction
   ↓
7. Text chunking
   ↓
8. Embedding generation
   ↓
9. Save to PostgreSQL
   ↓
10. Save embeddings to Vector DB
    ↓
11. Update cache
    ↓
12. Notify admin (if configured)
```

## Масштабирование и производительность

### Horizontal Scaling:

```yaml
# Docker Compose с масштабированием
services:
  backend:
    image: infohub-backend
    deploy:
      replicas: 3
    depends_on:
      - postgres
      - redis
      - chromadb

  worker:
    image: infohub-backend
    command: celery worker
    deploy:
      replicas: 5

  nginx:
    image: nginx
    ports:
      - "80:80"
    depends_on:
      - backend
```

### Caching Strategy:

1. **L1 Cache**: In-memory cache в application (LRU, 100MB)
2. **L2 Cache**: Redis (distributed cache, 1GB)
3. **L3 Cache**: CDN для static assets

### Database Optimization:

- Connection pooling (min=10, max=50)
- Query optimization и proper indexing
- Партиционирование таблиц по дате
- Read replicas для масштабирования чтения

### Vector Search Optimization:

- HNSW index для быстрого поиска
- Batch queries где возможно
- Approximate search для скорости
- Index sharding для больших баз

## Безопасность

### Authentication & Authorization:

```python
# JWT-based authentication
jwt_config = {
    "algorithm": "RS256",
    "access_token_expire_minutes": 30,
    "refresh_token_expire_days": 7
}

# RBAC
roles = {
    "admin": ["all"],
    "user": ["query", "read_documents", "manage_own_conversations"],
    "guest": ["query_limited"]
}
```

### Data Protection:

- Шифрование данных в transit (TLS/SSL)
- Шифрование чувствительных данных at rest
- Secure password hashing (bcrypt)
- API key rotation
- GDPR compliance

### Rate Limiting:

```python
rate_limits = {
    "guest": "10/minute",
    "user": "60/minute",
    "admin": "1000/minute"
}
```

## Мониторинг и Логирование

### Metrics (Prometheus):

- Request rate, latency, errors
- Query response time
- Vector search performance
- LLM API calls и costs
- Cache hit rate
- Database connection pool

### Logging (ELK Stack):

- Structured JSON logging
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Correlation IDs для трассировки
- User activity logs
- Error stack traces

### Alerting:

- High error rate
- Slow query performance
- Database connection issues
- API quota limits
- Scraping failures

## Disaster Recovery

### Backup Strategy:

- PostgreSQL: Daily full + hourly incremental
- Vector DB: Weekly full backup
- Redis: AOF persistence
- Document files: S3 с versioning

### Recovery Plan:

- RTO (Recovery Time Objective): 1 hour
- RPO (Recovery Point Objective): 1 hour
- Automated backup testing
- Documented recovery procedures

## Future Enhancements

1. **Multi-tenancy**: Поддержка нескольких организаций
2. **Advanced Analytics**: Dashboard с insights
3. **Fine-tuning**: Custom model для грузинского налогового домена
4. **Mobile Apps**: iOS и Android приложения
5. **Voice Interface**: Голосовой ввод/вывод
6. **Integration APIs**: Интеграция с бухгалтерскими системами
7. **Automated Updates**: Real-time обновления из infohub.ge
8. **Multilingual Expansion**: Поддержка большего числа языков
