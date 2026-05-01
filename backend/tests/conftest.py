"""
Shared pytest fixtures.

Environment variables are set here — before any app import — so that
get_settings() resolves correctly when app/db/session.py is first imported.
"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/travel_planner_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-minimum-32-characters!!")

# Clear lru_cache so Settings re-reads our env vars.
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.dependencies import get_agent, get_llm, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.db import Base  # noqa: E402

# ---------------------------------------------------------------------------
# Database — created once per session, shared across all tests
# ---------------------------------------------------------------------------

_TEST_DB_URL = os.environ["DATABASE_URL"]
_test_engine = create_async_engine(_TEST_DB_URL, echo=False)
_TestSession = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def database_tables():
    """Create all tables before the test session; drop them after."""

    async def _up() -> None:
        async with _test_engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)

    async def _down() -> None:
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await _test_engine.dispose()

    asyncio.run(_up())
    yield
    asyncio.run(_down())


@pytest_asyncio.fixture
async def db_session():
    """Yield a fresh AsyncSession per test (data persists; tests use unique values)."""
    async with _TestSession() as session:
        yield session


# ---------------------------------------------------------------------------
# Fake LLM / embedder / classifier
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_llm():
    """Deterministic LLM that always returns a plain AIMessage (no tool calls)."""
    llm = MagicMock()
    response = AIMessage(content="Here is your travel recommendation.")
    llm.bind_tools = MagicMock(return_value=llm)
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


@pytest.fixture
def fake_embedder():
    """Embedder returning a fixed 384-dim zero vector — no model download."""
    embedder = MagicMock()
    embedder.embed_batch = AsyncMock(return_value=[[0.0] * 384])
    return embedder


@pytest.fixture
def fake_classifier():
    """sklearn-style classifier with predictable predictions matching the real 8-class model."""
    model = MagicMock()
    model.predict = MagicMock(return_value=["Adventure"])
    model.predict_proba = MagicMock(return_value=[[
        0.40,  # Adventure
        0.05,  # Budget
        0.20,  # Culture
        0.10,  # Eco-Tourism
        0.05,  # Family
        0.05,  # Luxury
        0.10,  # Nightlife
        0.05,  # Relaxation
    ]])
    model.classes_ = [
        "Adventure", "Budget", "Culture", "Eco-Tourism",
        "Family", "Luxury", "Nightlife", "Relaxation",
    ]
    return model

@pytest.fixture
def fake_meta():
    """Sidecar metadata matching the real classifier — 30 features, 8 classes."""
    return {
        "model_class": "LogisticRegression",
        "classes": [
            "Adventure", "Budget", "Culture", "Eco-Tourism",
            "Family", "Luxury", "Nightlife", "Relaxation",
        ],
        "feature_names": [
            "num_hiking_trails", "distance_to_nearest_national_park_km",
            "extreme_sports_operator_count", "topographic_elevation_meters",
            "outdoor_to_indoor_attraction_ratio", "spa_and_wellness_center_count",
            "distance_to_coastline_or_lake_km", "noise_and_light_pollution_index",
            "sunshine_hours_per_year", "density_of_resorts",
            "unesco_sites_within_50km", "museum_and_gallery_count",
            "historical_monuments_count", "age_of_oldest_standing_landmark",
            "traditional_markets_count", "numbeo_cost_of_living_index",
            "avg_hostel_nightly_rate_usd", "avg_inexpensive_meal_cost_usd",
            "public_transit_ticket_cost_usd", "free_attractions_count",
            "michelin_star_restaurant_count", "avg_5_star_hotel_rate_usd",
            "luxury_boutique_density", "yacht_club_and_golf_course_count",
            "taxi_cost_per_10km_usd", "numbeo_safety_index",
            "theme_park_and_zoo_count", "walkability_score",
            "family_friendly_hotel_ratio", "healthcare_quality_index",
        ],
        "feature_count": 30,
    }


# ---------------------------------------------------------------------------
# HTTP client — app started with all heavy dependencies patched / overridden
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session, fake_llm, fake_embedder, fake_classifier, fake_meta):
    """
    AsyncClient for endpoint tests.

    Dependency overrides inject the fake DB session, LLM, and agent so no
    real Postgres connection or Anthropic call is made.  EmbeddingModel.get is
    patched so the lifespan does not download a sentence-transformer model.
    """
    from unittest.mock import patch

    from app.services.agent import TravelAgent

    async def _get_session():
        yield db_session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_llm] = lambda _req: fake_llm
    app.dependency_overrides[get_agent] = lambda _req: TravelAgent(
        llm_cheap=fake_llm,
        llm_strong=fake_llm,
        embedder=fake_embedder,
        ml_model=fake_classifier,
        ml_meta=fake_meta,
    )

    with patch("rag.embeddings.EmbeddingModel.get", return_value=fake_embedder):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()
