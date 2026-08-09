from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import structlog

from src.infrastructure.database import engine
from src.domain.models import Base
from src.presentation.routers import matches, predictions, analytics, results, internal

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()

# Create tables (fallback if Alembic has not run; migrations preferred)
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title="BrainBets API",
    description="Sports Betting Intelligence Platform - BFF Backend",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(matches.get_router(), prefix="/api/v1")
app.include_router(predictions.get_router(), prefix="/api/v1")
app.include_router(results.get_router(), prefix="/api/v1")
app.include_router(analytics.get_router(), prefix="/api/v1")
app.include_router(internal.get_router(), prefix="/api/v1/internal")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.0.0"}
