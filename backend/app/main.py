from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_anthropic import ChatAnthropic
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.routes.auth import router as auth_router
from app.routes.trips import router as trips_router
from app.utils.logging import configure_logging

log = structlog.get_logger()

_BACKEND_DIR = Path(__file__).parent.parent
_ML_MODEL_PATH = _BACKEND_DIR / "models" / "destination_classifier.joblib"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()

    # Async DB engine — stored for clean dispose on shutdown
    app.state.engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
    app.state.session_factory = async_sessionmaker(
        app.state.engine, class_=AsyncSession, expire_on_commit=False,
)

    # Sentence-transformer embedder (CPU-bound load → thread)
    from rag.embeddings import EmbeddingModel
    app.state.embedder = await asyncio.to_thread(EmbeddingModel.get, settings.embedding_model)

    # Scikit-learn ML classifier
    if _ML_MODEL_PATH.exists():
        import joblib, json
        app.state.ml_model = await asyncio.to_thread(joblib.load, _ML_MODEL_PATH)
    
        meta_path = _BACKEND_DIR / "models" / "destination_classifier_meta.json"
        with open(meta_path) as f:
            app.state.ml_meta = json.load(f)
    
        log.info("ml_model_loaded",
             path=str(_ML_MODEL_PATH),
             classes=app.state.ml_meta["classes"],
             feature_count=app.state.ml_meta["feature_count"])
    else:
        app.state.ml_model = None
        app.state.ml_meta = None
        log.warning("ml_model_not_found", path=str(_ML_MODEL_PATH))

    # Anthropic LLM clients — cheap (Haiku) for tool calls, strong (Sonnet) for synthesis
    app.state.llm_cheap = ChatAnthropic(
        model=settings.cheap_model,
        api_key=settings.anthropic_api_key,
    )
    app.state.llm_strong = ChatAnthropic(
        model=settings.strong_model,
        api_key=settings.anthropic_api_key,
    )

    log.info("startup_complete", cheap_model=settings.cheap_model, strong_model=settings.strong_model)
    yield

    await app.state.engine.dispose()
    log.info("shutdown_complete")


app = FastAPI(title="Smart Travel Planner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(trips_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
