"""FastAPI application entry point.

This module initializes the FastAPI application with middleware,
routers, and core endpoints.
"""

import logging
from datetime import datetime

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.server import __version__
from src.server.api.v1.router import router as v1_router
from src.server.config import settings
from src.server.models.common import HealthResponse
from src.server.services.scheduler_service import get_scheduler_service

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Backend API for wheel strategy options tracking and management",
    version=__version__,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Configure CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Include API routers
app.include_router(v1_router)


@app.on_event("startup")
async def startup_event():
    """Application startup event handler.

    Performs initialization tasks when the application starts.
    """
    logger.info(f"Starting {settings.app_name} v{__version__}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Database path: {settings.database_path}")

    # Initialize and start scheduler
    try:
        scheduler = get_scheduler_service()
        scheduler.initialize()
        scheduler.start()
        logger.info("Background scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start background scheduler: {e}", exc_info=True)


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event handler.

    Performs cleanup tasks when the application shuts down.
    """
    logger.info(f"Shutting down {settings.app_name}")

    # Shutdown scheduler
    try:
        scheduler = get_scheduler_service()
        scheduler.shutdown(wait=True)
        logger.info("Background scheduler shutdown successfully")
    except Exception as e:
        logger.error(f"Error during scheduler shutdown: {e}", exc_info=True)


@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["health"],
    summary="Health check endpoint",
    description="Returns service health status including scheduler",
)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Simple endpoint to verify the service is running and check
    background scheduler status.

    Returns:
        Health status response with timestamp and scheduler status

    Example:
        >>> GET /health
        >>> {
        >>>     "status": "healthy",
        >>>     "timestamp": "2026-02-01T10:00:00",
        >>>     "scheduler_running": true
        >>> }
    """
    # Check scheduler status
    scheduler_running = False
    try:
        scheduler = get_scheduler_service()
        scheduler_running = scheduler.is_running
    except Exception as e:
        logger.warning(f"Failed to get scheduler status: {e}")

    return HealthResponse(
        status="healthy", timestamp=datetime.utcnow(), scheduler_running=scheduler_running
    )


@app.get(
    "/",
    status_code=status.HTTP_200_OK,
    tags=["root"],
    summary="Root endpoint",
    description="Returns welcome message with API information",
)
async def root():
    """Root endpoint.

    Provides basic API information and links to documentation.

    Returns:
        Welcome message with API details
    """
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
        "api": "/api/v1/info",
    }


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors.

    Args:
        request: The request that caused the error
        exc: The exception that was raised

    Returns:
        JSON error response
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
            "detail": str(exc) if settings.debug else None,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.server.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
