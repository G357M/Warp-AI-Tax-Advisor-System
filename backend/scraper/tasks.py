"""
Celery tasks for background jobs.
"""
from celery import Celery
from celery.schedules import crontab

from backend.core.config import settings

# Initialize Celery app
celery_app = Celery(
    "infohub_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Celery configuration
celery_app.conf.update(
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.CELERY_TASK_TIME_LIMIT - 300,  # 5 min before hard limit
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)


@celery_app.task(name="scrape_infohub")
def scrape_infohub():
    """
    Task to run InfoHub spider.
    
    This task crawls infohub.ge and saves documents to database.
    """
    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings
    
    # Import spider settings
    from backend.scraper import settings as scraper_settings
    
    print("Starting InfoHub scraping task...")
    
    # TODO: Implement actual scraping
    # For now, just log that task was called
    print("InfoHub scraping task called (skeleton implementation)")
    
    return {"status": "completed", "message": "Scraping task skeleton"}


@celery_app.task(name="process_documents")
def process_documents():
    """
    Task to process newly scraped documents.
    
    This includes:
    - Text extraction
    - Chunking
    - Embedding generation
    - Vector DB indexing
    """
    print("Processing documents task called (skeleton implementation)")
    return {"status": "completed", "message": "Processing task skeleton"}


@celery_app.task(name="reindex_documents")
def reindex_documents():
    """
    Task to reindex all documents in vector database.
    
    This is useful when:
    - Changing embedding models
    - Updating chunking strategy
    - Recovering from data loss
    """
    print("Reindexing documents task called (skeleton implementation)")
    return {"status": "completed", "message": "Reindexing task skeleton"}


# Celery Beat schedule
celery_app.conf.beat_schedule = {
    "daily-scraping": {
        "task": "scrape_infohub",
        "schedule": crontab(hour=2, minute=0),  # Run at 2:00 AM daily
    },
    "hourly-processing": {
        "task": "process_documents",
        "schedule": crontab(minute=0),  # Run every hour
    },
}

celery_app.conf.timezone = "UTC"
