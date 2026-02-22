"""
Main FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.database import init_db
from api.routes import auth, query, public, scraper
from core.metrics import metrics_middleware, get_metrics
from core.logging_config import setup_logging, logging_middleware
from prometheus_client import CONTENT_TYPE_LATEST


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered tax advisor system for Georgia tax law",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add GZip middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add metrics middleware
app.middleware("http")(metrics_middleware)

# Add logging middleware
app.middleware("http")(logging_middleware)

# Include routers
app.include_router(public.router, prefix=settings.API_PREFIX)  # Public endpoints (no auth)
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(query.router, prefix=settings.API_PREFIX)
app.include_router(scraper.router, prefix=settings.API_PREFIX)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    # Setup logging
    setup_logging(
        log_level=settings.LOG_LEVEL,
        json_logs=settings.ENVIRONMENT == "production"
    )
    
    # Initialize database
    init_db()
    print(f"✓ {settings.APP_NAME} v{settings.APP_VERSION} started")
    print(f"✓ Environment: {settings.ENVIRONMENT}")
    print(f"✓ Debug mode: {settings.DEBUG}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    print(f"✓ {settings.APP_NAME} shutdown")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    metrics_data = get_metrics()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.DEBUG else "An error occurred",
        },
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "backend.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
