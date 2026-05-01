import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8)]


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Trip planning
# ---------------------------------------------------------------------------

class TripQuery(BaseModel):
    query: str = Field(..., min_length=10, max_length=2000)


class TripResponse(BaseModel):
    run_id: uuid.UUID
    answer: str
    tools_used: list[str]
    cost_usd: float


# ---------------------------------------------------------------------------
# History / run detail
# ---------------------------------------------------------------------------

class ToolLogResponse(BaseModel):
    id: uuid.UUID
    tool_name: str
    input_data: dict
    output_data: dict | None
    error: str | None
    duration_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RunSummary(BaseModel):
    id: uuid.UUID
    query: str
    response: str | None
    tools_used: list[str]
    estimated_cost_usd: float
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RunDetail(BaseModel):
    id: uuid.UUID
    query: str
    response: str | None
    tools_used: list[str]
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    status: str
    created_at: datetime
    tool_calls: list[ToolLogResponse]

    model_config = {"from_attributes": True}


class HistoryResponse(BaseModel):
    runs: list[RunSummary]
    total: int
    page: int
    page_size: int
