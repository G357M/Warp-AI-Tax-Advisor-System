"""
Scraper API routes.
"""
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, Dict

from backend.scraper.infohub_scraper import InfoHubScraper


router = APIRouter(prefix="/scraper", tags=["Scraper"])


# In-memory task storage (in production, use Redis or database)
scraping_tasks = {}


class ScrapeRequest(BaseModel):
    """Scrape request schema."""
    url: HttpUrl = Field(..., description="Starting URL to scrape")
    max_depth: int = Field(default=2, ge=1, le=5, description="Maximum link depth")
    max_pages: int = Field(default=50, ge=1, le=500, description="Maximum pages to scrape")


class ScrapeResponse(BaseModel):
    """Scrape response schema."""
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """Task status response schema."""
    task_id: str
    status: str
    documents_scraped: Optional[int] = None
    pages_visited: Optional[int] = None
    result: Optional[Dict] = None
    error: Optional[str] = None


async def run_scraper_task(task_id: str, url: str, max_depth: int, max_pages: int):
    """Run scraper task in background."""
    scraping_tasks[task_id] = {
        'status': 'running',
        'documents_scraped': 0,
        'pages_visited': 0,
    }
    
    try:
        scraper = InfoHubScraper()
        result = await scraper.scrape(
            start_url=str(url),
            max_depth=max_depth,
            max_pages=max_pages,
        )
        
        scraping_tasks[task_id] = {
            'status': 'completed',
            'result': result,
            'documents_scraped': result['documents_scraped'],
            'pages_visited': result['pages_visited'],
        }
    
    except Exception as e:
        scraping_tasks[task_id] = {
            'status': 'failed',
            'error': str(e),
        }


@router.post("/start", response_model=ScrapeResponse)
async def start_scraping(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Start a scraping task.
    
    The task will run in the background and can be monitored via `/scraper/status/{task_id}`.
    
    - **url**: Starting URL (must be from infohub.ge)
    - **max_depth**: Maximum depth to follow links (1-5)
    - **max_pages**: Maximum number of pages to scrape (1-500)
    """
    # Validate URL is from infohub.ge
    if 'infohub.ge' not in str(request.url):
        raise HTTPException(
            status_code=400,
            detail="URL must be from infohub.ge domain"
        )
    
    # Generate task ID
    import uuid
    task_id = str(uuid.uuid4())
    
    # Start background task
    background_tasks.add_task(
        run_scraper_task,
        task_id,
        str(request.url),
        request.max_depth,
        request.max_pages
    )
    
    return ScrapeResponse(
        task_id=task_id,
        status="started",
        message=f"Scraping task started. Use task_id to check status."
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Get the status of a scraping task.
    
    - **task_id**: Task ID returned from `/scraper/start`
    
    Returns current status and results if completed.
    """
    if task_id not in scraping_tasks:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found"
        )
    
    task_data = scraping_tasks[task_id]
    
    return TaskStatusResponse(
        task_id=task_id,
        status=task_data['status'],
        documents_scraped=task_data.get('documents_scraped'),
        pages_visited=task_data.get('pages_visited'),
        result=task_data.get('result'),
        error=task_data.get('error'),
    )


@router.get("/tasks")
async def list_tasks():
    """
    List all scraping tasks.
    
    Returns a list of all tasks with their current status.
    """
    return {
        'total_tasks': len(scraping_tasks),
        'tasks': [
            {
                'task_id': task_id,
                'status': data['status'],
                'documents_scraped': data.get('documents_scraped', 0),
            }
            for task_id, data in scraping_tasks.items()
        ]
    }


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """
    Delete a task from the task list.
    
    - **task_id**: Task ID to delete
    """
    if task_id not in scraping_tasks:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found"
        )
    
    del scraping_tasks[task_id]
    
    return {
        'message': f'Task {task_id} deleted successfully'
    }
