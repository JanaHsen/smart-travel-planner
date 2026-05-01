from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from langchain_core.messages import AIMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.dependencies import get_agent, get_current_user, get_session
from app.models.db import AgentRun, ToolCallLog
from app.models.schemas import HistoryResponse, RunDetail, RunSummary, TripQuery, TripResponse
from app.services.webhook import deliver_to_discord

router = APIRouter(prefix="/trips", tags=["trips"])
log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Pricing constants (per token)
# ---------------------------------------------------------------------------
_HAIKU_IN = 0.80 / 1_000_000
_HAIKU_OUT = 4.00 / 1_000_000
_SONNET_IN = 3.00 / 1_000_000
_SONNET_OUT = 15.00 / 1_000_000


def _compute_cost(token_counts: dict[str, Any]) -> tuple[int, int, float]:
    """Return (total_input_tokens, total_output_tokens, cost_usd)."""
    total_in = total_out = 0
    cost = 0.0
    for key, usage in token_counts.items():
        if not isinstance(usage, dict):
            continue
        inp = int(usage.get("input_tokens", 0))
        out = int(usage.get("output_tokens", 0))
        total_in += inp
        total_out += out
        if key.startswith("haiku"):
            cost += inp * _HAIKU_IN + out * _HAIKU_OUT
        else:
            cost += inp * _SONNET_IN + out * _SONNET_OUT
    return total_in, total_out, cost


def _extract_answer(state: dict) -> str:
    """Pull the text content from the last AIMessage in the state."""
    for msg in reversed(state.get("messages", [])):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str) and content:
            return content
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            joined = " ".join(parts).strip()
            if joined:
                return joined
    return ""


# ---------------------------------------------------------------------------
# POST /trips/plan
# ---------------------------------------------------------------------------

@router.post("/plan", response_model=TripResponse)
async def plan_trip(
    body: TripQuery,
    request: Request,
    user=Depends(get_current_user),
    agent=Depends(get_agent),
):
    """
    Run the agent and persist the result.
    
    Uses two separate sessions: one for the agent's read-only tool queries,
    one for the persistence write. This avoids the long-lived async session
    state corruption that occurs when a single session spans the agent's
    50+ second Sonnet synthesis call.
    """
    run_id = uuid.uuid4()
    log.info("trip.plan_start", run_id=str(run_id), user_id=str(user.id), query=body.query[:60])

    session_factory = request.app.state.session_factory

    state: dict | None = None
    run_status = "failed"
    answer = ""
    total_in = total_out = 0
    cost = 0.0
    tools_used: list[str] = []

    # Session 1 — agent's RAG queries (read-only).
    async with session_factory() as agent_session:
        try:
            state = await agent.arun(body.query, agent_session)
            answer = _extract_answer(state)
            total_in, total_out, cost = _compute_cost(state.get("token_counts", {}))
            seen: set[str] = set()
            tools_used = [t for t in state.get("tools_used", []) if not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]
            run_status = "completed"
            log.info("trip.agent_done", run_id=str(run_id), cost_usd=round(cost, 6), tools=tools_used)
        except Exception as exc:
            log.error("trip.agent_error", run_id=str(run_id), error=str(exc))

    # Session 2 — persistence write (clean session, no shared state).
    async with session_factory() as persist_session:
        try:
            run = AgentRun(
                id=run_id,
                user_id=user.id,
                query=body.query,
                response=answer or None,
                tools_used=tools_used,
                total_input_tokens=total_in,
                total_output_tokens=total_out,
                estimated_cost_usd=cost,
                status=run_status,
            )
            persist_session.add(run)

            for tl in (state or {}).get("tool_logs", []):
                out_data = tl.get("output_data")
                persist_session.add(ToolCallLog(
                    agent_run_id=run_id,
                    tool_name=tl["tool_name"],
                    input_data=tl.get("input_data") or {},
                    output_data=out_data if isinstance(out_data, dict) else None,
                    error=tl.get("error"),
                    duration_ms=tl.get("duration_ms", 0),
                ))

            await persist_session.commit()
            log.info("trip.plan_persisted", run_id=str(run_id))
        except Exception as exc:
            log.error("trip.persist_error", run_id=str(run_id), error=str(exc))
            await persist_session.rollback()

    # Fire Discord webhook without blocking the response
    settings = get_settings()
    if settings.discord_webhook_url and run_status == "completed" and answer:
        asyncio.create_task(
            deliver_to_discord(settings.discord_webhook_url, answer, user.email)
        )

    if run_status == "failed":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Agent execution failed")

    return TripResponse(run_id=run_id, answer=answer, tools_used=tools_used, cost_usd=cost)


# ---------------------------------------------------------------------------
# GET /trips/history
# ---------------------------------------------------------------------------

@router.get("/history", response_model=HistoryResponse)
async def trip_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    log.info("trip.history_request", user_id=str(user.id), page=page, page_size=page_size)
    offset = (page - 1) * page_size

    total: int = await session.scalar(
        select(func.count(AgentRun.id)).where(AgentRun.user_id == user.id)
    ) or 0

    rows = await session.scalars(
        select(AgentRun)
        .where(AgentRun.user_id == user.id)
        .order_by(AgentRun.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    result = HistoryResponse(
        runs=[RunSummary.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
    log.info("trip.history_served", user_id=str(user.id), total=total, returned=len(result.runs))
    return result


# ---------------------------------------------------------------------------
# GET /trips/{run_id}
# ---------------------------------------------------------------------------

@router.get("/{run_id}", response_model=RunDetail)
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    log.info("trip.get_run_request", user_id=str(user.id), run_id=str(run_id))
    run = await session.scalar(
        select(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.user_id == user.id)
        .options(selectinload(AgentRun.tool_calls))
    )
    if run is None:
        log.warning("trip.get_run_not_found", user_id=str(user.id), run_id=str(run_id))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    log.info("trip.get_run_served", user_id=str(user.id), run_id=str(run_id), status=run.status)
    return RunDetail.model_validate(run)
