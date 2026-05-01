"""
Pydantic schema validation tests.

Each schema is exercised with at least one valid payload (must not raise) and
at least one invalid payload (must raise ValidationError).  No app startup or
database connection is required.
"""
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    HistoryResponse,
    RunDetail,
    RunSummary,
    Token,
    ToolLogResponse,
    TripQuery,
    TripResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.tools.classify_destination import ClassifyInput
from app.tools.live_conditions import LiveConditionsInput
from app.tools.rag_search import RagSearchInput


# ---------------------------------------------------------------------------
# TripQuery
# ---------------------------------------------------------------------------


def test_trip_query_valid():
    q = TripQuery(query="What are the best beaches in Thailand?")
    assert q.query == "What are the best beaches in Thailand?"


def test_trip_query_too_short():
    with pytest.raises(ValidationError):
        TripQuery(query="short")


def test_trip_query_too_long():
    with pytest.raises(ValidationError):
        TripQuery(query="x" * 2001)


def test_trip_query_empty():
    with pytest.raises(ValidationError):
        TripQuery(query="")


# ---------------------------------------------------------------------------
# RagSearchInput
# ---------------------------------------------------------------------------


def test_rag_search_input_valid():
    inp = RagSearchInput(query="tropical beaches", top_k=3)
    assert inp.top_k == 3


def test_rag_search_input_defaults():
    inp = RagSearchInput(query="mountain hiking")
    assert inp.top_k == 5


def test_rag_search_input_top_k_zero():
    with pytest.raises(ValidationError):
        RagSearchInput(query="some query", top_k=0)


def test_rag_search_input_top_k_too_large():
    with pytest.raises(ValidationError):
        RagSearchInput(query="some query", top_k=11)


# ---------------------------------------------------------------------------
# ClassifyInput
# ---------------------------------------------------------------------------


def test_classify_input_valid():
    inp = ClassifyInput(
        climate="tropical",
        cost_index=4.5,
        top_activities="hiking,swimming",
        region="Southeast Asia",
    )
    assert inp.safety_score == 5.0  # default


def test_classify_input_cost_index_out_of_range():
    with pytest.raises(ValidationError):
        ClassifyInput(
            climate="arid",
            cost_index=11.0,
            top_activities="surfing",
            region="Pacific",
        )


def test_classify_input_negative_score():
    with pytest.raises(ValidationError):
        ClassifyInput(
            climate="temperate",
            cost_index=5.0,
            top_activities="museums",
            region="Europe",
            safety_score=-1.0,
        )


def test_classify_input_missing_required_fields():
    with pytest.raises(ValidationError):
        ClassifyInput(cost_index=5.0)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# LiveConditionsInput
# ---------------------------------------------------------------------------


def test_live_conditions_input_valid():
    inp = LiveConditionsInput(city="Paris", country="France", travel_date="2026-06-01")
    assert inp.travel_date == "2026-06-01"


def test_live_conditions_input_no_date():
    inp = LiveConditionsInput(city="Tokyo", country="Japan")
    assert inp.travel_date is None


def test_live_conditions_input_missing_city():
    with pytest.raises(ValidationError):
        LiveConditionsInput(country="Japan")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# UserCreate
# ---------------------------------------------------------------------------


def test_user_create_valid():
    u = UserCreate(email="alice@example.com", password="securepass")
    assert u.email == "alice@example.com"


def test_user_create_invalid_email():
    with pytest.raises(ValidationError):
        UserCreate(email="not-an-email", password="securepass")


def test_user_create_password_too_short():
    with pytest.raises(ValidationError):
        UserCreate(email="bob@example.com", password="short")


# ---------------------------------------------------------------------------
# UserLogin
# ---------------------------------------------------------------------------


def test_user_login_valid():
    u = UserLogin(email="alice@example.com", password="anything")
    assert u.password == "anything"


def test_user_login_invalid_email():
    with pytest.raises(ValidationError):
        UserLogin(email="bad", password="anything")


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------


def test_token_valid():
    t = Token(access_token="abc.def.ghi")
    assert t.token_type == "bearer"


def test_token_missing_access_token():
    with pytest.raises(ValidationError):
        Token()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# UserResponse (from_attributes ORM mode)
# ---------------------------------------------------------------------------


def test_user_response_from_dict():
    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    resp = UserResponse(id=uid, email="carol@example.com", created_at=now)
    assert resp.id == uid


# ---------------------------------------------------------------------------
# TripResponse
# ---------------------------------------------------------------------------


def test_trip_response_valid():
    resp = TripResponse(
        run_id=uuid.uuid4(),
        answer="Visit Bali in April.",
        tools_used=["rag_search", "live_conditions"],
        cost_usd=0.0012,
    )
    assert len(resp.tools_used) == 2


# ---------------------------------------------------------------------------
# RunSummary / RunDetail / ToolLogResponse / HistoryResponse
# ---------------------------------------------------------------------------


def test_run_summary_valid():
    s = RunSummary(
        id=uuid.uuid4(),
        query="Best ski resorts?",
        response="Try Aspen.",
        tools_used=["rag_search"],
        estimated_cost_usd=0.001,
        status="completed",
        created_at=datetime.now(timezone.utc),
    )
    assert s.status == "completed"


def test_tool_log_response_valid():
    log = ToolLogResponse(
        id=uuid.uuid4(),
        tool_name="rag_search",
        input_data={"query": "beaches"},
        output_data={"results": []},
        error=None,
        duration_ms=42,
        created_at=datetime.now(timezone.utc),
    )
    assert log.duration_ms == 42


def test_run_detail_valid():
    detail = RunDetail(
        id=uuid.uuid4(),
        query="Ski trip?",
        response="Go to Aspen.",
        tools_used=[],
        total_input_tokens=100,
        total_output_tokens=50,
        estimated_cost_usd=0.002,
        status="completed",
        created_at=datetime.now(timezone.utc),
        tool_calls=[],
    )
    assert detail.total_input_tokens == 100


def test_history_response_valid():
    h = HistoryResponse(runs=[], total=0, page=1, page_size=20)
    assert h.total == 0
