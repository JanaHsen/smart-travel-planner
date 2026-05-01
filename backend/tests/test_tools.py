"""
Unit tests for the three tool functions.

All external calls (DB, HTTP) are mocked so these tests run without a real
database or network connection.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from app.tools.classify_destination import ClassifyInput, ClassifyOutput, ToolError, classify_destination
from app.tools.live_conditions import LiveConditionsInput, LiveConditionsOutput, live_conditions
from app.tools.rag_search import RagSearchInput, RagSearchOutput, rag_search


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_weather_cache():
    """Prevent cache bleed between live_conditions tests."""
    from app.tools.live_conditions import _weather_cache

    _weather_cache.clear()
    yield
    _weather_cache.clear()


def _fake_session() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# rag_search
# ---------------------------------------------------------------------------


async def test_rag_search_returns_results(fake_embedder):
    raw_hits = [
        {"text": "Beautiful beaches in Bali", "source": "bali.md", "score": 0.92, "metadata": {}},
        {"text": "Cheap food in Chiang Mai", "source": "thailand.md", "score": 0.85, "metadata": {}},
    ]
    with patch("app.tools.rag_search.search_destinations", AsyncMock(return_value=raw_hits)):
        result = await rag_search(
            RagSearchInput(query="tropical beach vacation", top_k=2),
            session=_fake_session(),
            embedder=fake_embedder,
        )

    assert isinstance(result, RagSearchOutput)
    assert len(result.results) == 2
    assert result.results[0].score == 0.92
    assert result.results[0].source == "bali.md"


async def test_rag_search_handles_empty_results(fake_embedder):
    with patch("app.tools.rag_search.search_destinations", AsyncMock(return_value=[])):
        result = await rag_search(
            RagSearchInput(query="obscure destination nobody knows", top_k=5),
            session=_fake_session(),
            embedder=fake_embedder,
        )

    assert isinstance(result, RagSearchOutput)
    assert result.results == []


async def test_rag_search_returns_tool_error_on_exception(fake_embedder):
    from app.tools.rag_search import ToolError as RagToolError

    with patch(
        "app.tools.rag_search.search_destinations",
        AsyncMock(side_effect=RuntimeError("DB unavailable")),
    ):
        result = await rag_search(
            RagSearchInput(query="anything", top_k=3),
            session=_fake_session(),
            embedder=fake_embedder,
        )

    assert isinstance(result, RagToolError)
    assert result.retryable is True
    assert "DB unavailable" in result.error


# ---------------------------------------------------------------------------
# classify_destination
# ---------------------------------------------------------------------------


async def test_classify_returns_valid_label(fake_classifier):
    inp = ClassifyInput(
        climate="tropical",
        cost_index=3.0,
        top_activities="swimming,snorkeling",
        region="Southeast Asia",
    )
    result = await classify_destination(inp, model=fake_classifier)

    assert isinstance(result, ClassifyOutput)
    assert result.label == "beach"
    assert 0.0 <= result.confidence <= 1.0
    assert "beach" in result.all_probabilities


async def test_classify_returns_tool_error_when_model_is_none():
    inp = ClassifyInput(
        climate="arid",
        cost_index=7.0,
        top_activities="dune-bashing",
        region="Middle East",
    )
    result = await classify_destination(inp, model=None)

    assert isinstance(result, ToolError)
    assert result.retryable is False


async def test_classify_handles_invalid_features():
    """ClassifyInput enforces range constraints — invalid values raise ValidationError."""
    with pytest.raises(ValidationError):
        ClassifyInput(
            climate="polar",
            cost_index=99.0,  # > 10.0 — invalid
            top_activities="skiing",
            region="Arctic",
        )


async def test_classify_returns_tool_error_when_model_raises(fake_classifier):
    fake_classifier.predict = MagicMock(side_effect=ValueError("model corrupted"))

    inp = ClassifyInput(
        climate="temperate",
        cost_index=5.0,
        top_activities="hiking",
        region="Europe",
    )
    result = await classify_destination(inp, model=fake_classifier)

    assert isinstance(result, ToolError)
    assert "model corrupted" in result.error


# ---------------------------------------------------------------------------
# live_conditions
# ---------------------------------------------------------------------------


def _mock_httpx_client(geocode_json: dict, weather_json: dict) -> MagicMock:
    """Return a mock httpx.AsyncClient context manager that yields pre-baked responses."""
    geocode_resp = MagicMock()
    geocode_resp.raise_for_status = MagicMock()
    geocode_resp.json = MagicMock(return_value=geocode_json)

    weather_resp = MagicMock()
    weather_resp.raise_for_status = MagicMock()
    weather_resp.json = MagicMock(return_value=weather_json)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[geocode_resp, weather_resp])

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


async def test_live_conditions_returns_weather():
    geocode_json = {"results": [{"latitude": 48.85, "longitude": 2.35}]}
    weather_json = {
        "current": {
            "temperature_2m": 22.5,
            "relative_humidity_2m": 60,
            "wind_speed_10m": 15.0,
            "weather_code": 1,
        }
    }
    cm = _mock_httpx_client(geocode_json, weather_json)

    with patch("app.tools.live_conditions.httpx.AsyncClient", return_value=cm):
        result = await live_conditions(LiveConditionsInput(city="Paris", country="France"))

    assert isinstance(result, LiveConditionsOutput)
    assert result.weather is not None
    assert result.weather.temp_c == 22.5
    assert result.weather.conditions == "Mainly clear"
    assert result.weather.humidity == 60
    assert result.errors == []


async def test_live_conditions_handles_timeout():
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.tools.live_conditions.httpx.AsyncClient", return_value=cm):
        result = await live_conditions(LiveConditionsInput(city="London", country="UK"))

    assert result.weather is None
    assert len(result.errors) == 1
    assert "Weather fetch failed" in result.errors[0]


async def test_live_conditions_returns_tool_error_on_failure():
    """Geocoding that finds no results causes an error entry without an exception."""
    geocode_json = {"results": []}  # empty — city not found
    weather_json = {}
    cm = _mock_httpx_client(geocode_json, weather_json)

    with patch("app.tools.live_conditions.httpx.AsyncClient", return_value=cm):
        result = await live_conditions(LiveConditionsInput(city="NowhereCity", country="XX"))

    assert result.weather is None
    assert any("Could not geocode" in e for e in result.errors)
