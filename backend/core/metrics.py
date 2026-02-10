"""
Prometheus metrics for monitoring.
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from time import time
import psutil
import os

# Request metrics
request_count = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

# Query metrics
query_count = Counter(
    'queries_total',
    'Total queries processed',
    ['language', 'status']
)

query_duration = Histogram(
    'query_duration_seconds',
    'Query processing duration in seconds',
    ['language']
)

retrieval_count = Histogram(
    'document_retrieval_count',
    'Number of documents retrieved per query'
)

# System metrics
active_requests = Gauge(
    'active_requests',
    'Number of requests currently being processed'
)

database_connections = Gauge(
    'database_connections_active',
    'Number of active database connections'
)

# Scraper metrics
scraper_tasks_total = Counter(
    'scraper_tasks_total',
    'Total scraper tasks',
    ['status']
)

scraper_documents_processed = Counter(
    'scraper_documents_processed',
    'Total documents processed by scraper'
)

# Cache metrics
cache_hits = Counter(
    'cache_hits_total',
    'Total cache hits',
    ['cache_type']
)

cache_misses = Counter(
    'cache_misses_total',
    'Total cache misses',
    ['cache_type']
)

# System resource metrics
cpu_usage = Gauge(
    'system_cpu_usage_percent',
    'Current CPU usage percentage'
)

memory_usage = Gauge(
    'system_memory_usage_bytes',
    'Current memory usage in bytes'
)

disk_usage = Gauge(
    'system_disk_usage_percent',
    'Current disk usage percentage'
)


def update_system_metrics():
    """Update system resource metrics."""
    try:
        # CPU usage
        cpu_usage.set(psutil.cpu_percent(interval=1))
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_usage.set(memory.used)
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_usage.set(disk.percent)
    except Exception as e:
        print(f"Error updating system metrics: {e}")


async def metrics_middleware(request: Request, call_next):
    """Middleware to track request metrics."""
    start_time = time()
    
    # Increment active requests
    active_requests.inc()
    
    try:
        response = await call_next(request)
        
        # Calculate duration
        duration = time() - start_time
        
        # Extract endpoint (remove query params)
        endpoint = request.url.path
        
        # Record metrics
        request_count.labels(
            method=request.method,
            endpoint=endpoint,
            status=response.status_code
        ).inc()
        
        request_duration.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(duration)
        
        return response
        
    finally:
        # Decrement active requests
        active_requests.dec()


def get_metrics():
    """Generate Prometheus metrics."""
    # Update system metrics before generating
    update_system_metrics()
    return generate_latest()


def track_query(language: str, status: str, duration: float, retrieved_docs: int):
    """Track query metrics."""
    query_count.labels(language=language, status=status).inc()
    query_duration.labels(language=language).observe(duration)
    retrieval_count.observe(retrieved_docs)


def track_scraper_task(status: str, documents_count: int = 0):
    """Track scraper task metrics."""
    scraper_tasks_total.labels(status=status).inc()
    if documents_count > 0:
        scraper_documents_processed.inc(documents_count)


def track_cache(cache_type: str, hit: bool):
    """Track cache hit/miss."""
    if hit:
        cache_hits.labels(cache_type=cache_type).inc()
    else:
        cache_misses.labels(cache_type=cache_type).inc()
