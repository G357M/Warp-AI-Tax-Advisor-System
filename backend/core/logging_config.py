"""
Structured JSON logging configuration.
"""
import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict
from fastapi import Request
import traceback


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields
        if hasattr(record, "extra"):
            log_data["extra"] = record.extra
        
        # Add request context if available
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        
        if hasattr(record, "endpoint"):
            log_data["endpoint"] = record.endpoint
        
        if hasattr(record, "method"):
            log_data["method"] = record.method
        
        if hasattr(record, "duration"):
            log_data["duration_ms"] = record.duration
        
        return json.dumps(log_data)


def setup_logging(log_level: str = "INFO", json_logs: bool = True):
    """Setup logging configuration."""
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    
    # Set formatter
    if json_logs:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Silence noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    return logger


class RequestLogger:
    """Logger with request context."""
    
    def __init__(self, logger: logging.Logger, request_id: str = None, user_id: str = None):
        self.logger = logger
        self.request_id = request_id
        self.user_id = user_id
    
    def _add_context(self, extra: Dict = None) -> Dict:
        """Add request context to log."""
        context = {}
        if self.request_id:
            context["request_id"] = self.request_id
        if self.user_id:
            context["user_id"] = self.user_id
        if extra:
            context.update(extra)
        return context
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        extra = self._add_context(kwargs)
        record = self.logger.makeRecord(
            self.logger.name, logging.INFO, "", 0, message, (), None
        )
        for key, value in extra.items():
            setattr(record, key, value)
        self.logger.handle(record)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        extra = self._add_context(kwargs)
        record = self.logger.makeRecord(
            self.logger.name, logging.WARNING, "", 0, message, (), None
        )
        for key, value in extra.items():
            setattr(record, key, value)
        self.logger.handle(record)
    
    def error(self, message: str, **kwargs):
        """Log error message."""
        extra = self._add_context(kwargs)
        record = self.logger.makeRecord(
            self.logger.name, logging.ERROR, "", 0, message, (), None
        )
        for key, value in extra.items():
            setattr(record, key, value)
        self.logger.handle(record)
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        extra = self._add_context(kwargs)
        record = self.logger.makeRecord(
            self.logger.name, logging.DEBUG, "", 0, message, (), None
        )
        for key, value in extra.items():
            setattr(record, key, value)
        self.logger.handle(record)


async def logging_middleware(request: Request, call_next):
    """Middleware to add request logging."""
    import uuid
    from time import time
    
    # Generate request ID
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Get logger
    logger = logging.getLogger("api")
    
    # Log request start
    start_time = time()
    
    try:
        response = await call_next(request)
        
        # Calculate duration
        duration = (time() - start_time) * 1000  # Convert to ms
        
        # Log request completion
        record = logger.makeRecord(
            logger.name,
            logging.INFO,
            "",
            0,
            "Request completed",
            (),
            None
        )
        record.request_id = request_id
        record.endpoint = request.url.path
        record.method = request.method
        record.status_code = response.status_code
        record.duration = round(duration, 2)
        logger.handle(record)
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
        
    except Exception as e:
        # Log error
        record = logger.makeRecord(
            logger.name,
            logging.ERROR,
            "",
            0,
            f"Request failed: {str(e)}",
            (),
            sys.exc_info()
        )
        record.request_id = request_id
        record.endpoint = request.url.path
        record.method = request.method
        logger.handle(record)
        raise


def get_logger(name: str, request_id: str = None, user_id: str = None) -> RequestLogger:
    """Get a logger with request context."""
    logger = logging.getLogger(name)
    return RequestLogger(logger, request_id, user_id)
