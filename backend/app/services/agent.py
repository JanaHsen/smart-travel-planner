from __future__ import annotations

import json
import time
from typing import Annotated, Any

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.tools.classify_destination import ClassifyInput, classify_destination
from app.tools.live_conditions import LiveConditionsInput, live_conditions
from app.tools.rag_search import RagSearchInput, rag_search

log = structlog.get_logger()

ALLOWED_TOOLS: frozenset[str] = frozenset({"rag_search", "classify_destination", "live_conditions"})

_SYSTEM_PROMPT = """\
You are an expert travel planning assistant helping someone plan a real trip.

You have access to several internal sources of information — destination guides, current weather \
data, and a destination classifier. Use them to inform your recommendations, but DO NOT mention \
them to the user. The user is a traveller, not an engineer; they don't need to know about your \
"knowledge base", "RAG", "tools", "classifier", or "live conditions feed". Speak naturally, as a \
knowledgeable friend would.

Guidelines:
- Search internal destination guides first to gather context on destinations that might fit.
- When you have enough information about a candidate destination, classify its travel style.
- Check current weather and conditions to ground recommendations in present-day reality.
- If different sources of information tell different stories, integrate them honestly — but do \
not mention "the RAG said X but live data said Y." Just give the user the most accurate answer \
you can synthesize, and note any uncertainty in plain language ("weather data for March confirms \
this", or "I'd verify current flight prices on Google Flights before booking").
- Never write phrases like "RAG knowledge base", "ML classifier", "tool returned", "live feed", \
"data gap", or anything else that exposes internal plumbing.
- Synthesize all information into a coherent recommendation — never concatenate raw outputs or \
list source-by-source what each tool said.

The output should read as a polished travel plan from a thoughtful human expert.\
"""


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    tools_used: list[str]
    token_counts: dict[str, Any]
    tool_logs: list[dict]


class TravelAgent:
    """
    LangGraph-based travel planning agent with dual-model routing.

    Haiku (cheap_model) drives tool selection and argument extraction.
    Sonnet (strong_model) performs final synthesis once all tools have returned.
    """

    def __init__(
        self,
        llm_cheap: ChatAnthropic,
        llm_strong: ChatAnthropic,
        embedder: Any,
        ml_model: Any,
        ml_meta: dict | None = None,
    ) -> None:
        self._llm_cheap = llm_cheap
        self._llm_strong = llm_strong
        self._embedder = embedder
        self._ml_model = ml_model
        self._ml_meta = ml_meta

    def _make_tools(self, session: Any) -> list[StructuredTool]:
        embedder = self._embedder
        ml_model = self._ml_model
        ml_meta = self._ml_meta

        async def _rag_search(query: str, top_k: int = 5):
            result = await rag_search(
                RagSearchInput(query=query, top_k=top_k),
                session=session,
                embedder=embedder,
            )
            return result.model_dump()

        async def _classify_destination(**kwargs: Any):
            result = await classify_destination(
                ClassifyInput(**kwargs),
                model=ml_model,
                meta=ml_meta,
            )
            return result.model_dump()

        async def _live_conditions(city: str, country: str, travel_date: str | None = None):
            result = await live_conditions(
                LiveConditionsInput(city=city, country=country, travel_date=travel_date)
            )
            return result.model_dump()

        return [
            StructuredTool.from_function(
                coroutine=_rag_search,
                name="rag_search",
                description="Search destination guides for travel info, tips, and recommendations.",
                args_schema=RagSearchInput,
            ),
            StructuredTool.from_function(
                coroutine=_classify_destination,
                name="classify_destination",
                description=(
                    "Classify a destination by travel style using an ML model. "
                    "Provide climate, region, cost index, top activities, and optional score fields."
                ),
                args_schema=ClassifyInput,
            ),
            StructuredTool.from_function(
                coroutine=_live_conditions,
                name="live_conditions",
                description="Get real-time weather and conditions for a city.",
                args_schema=LiveConditionsInput,
            ),
        ]

    def _build_graph(self, session: Any):
        tools = self._make_tools(session)
        tool_map = {t.name: t for t in tools}
        haiku_bound = self._llm_cheap.bind_tools(tools)

        async def call_haiku(state: AgentState) -> dict:
            t0 = time.perf_counter()
            messages: list[BaseMessage] = [SystemMessage(content=_SYSTEM_PROMPT)] + list(state["messages"])
            response = await haiku_bound.ainvoke(messages)
            duration_ms = int((time.perf_counter() - t0) * 1000)

            counts = dict(state.get("token_counts", {}))
            usage = getattr(response, "usage_metadata", None)
            if usage:
                counts[f"haiku_{len(counts)}"] = dict(usage)

            log.info(
                "agent.haiku",
                duration_ms=duration_ms,
                tool_calls=len(getattr(response, "tool_calls", None) or []),
                input_tokens=(usage or {}).get("input_tokens"),
                output_tokens=(usage or {}).get("output_tokens"),
            )
            return {"messages": [response], "token_counts": counts}

        async def execute_tools(state: AgentState) -> dict:
            last = state["messages"][-1]
            results: list[ToolMessage] = []
            used: list[str] = list(state.get("tools_used", []))
            logs: list[dict] = list(state.get("tool_logs", []))

            for tc in getattr(last, "tool_calls", None) or []:
                name: str = tc["name"]
                t0 = time.perf_counter()

                if name not in ALLOWED_TOOLS:
                    log.warning("agent.tool_blocked", tool=name)
                    results.append(
                        ToolMessage(
                            content=f"Tool '{name}' is not allowed. Available: {sorted(ALLOWED_TOOLS)}",
                            tool_call_id=tc["id"],
                        )
                    )
                    continue

                entry: dict = {
                    "tool_name": name,
                    "input_data": tc["args"],
                    "output_data": None,
                    "error": None,
                    "duration_ms": 0,
                }
                try:
                    output = await tool_map[name].ainvoke(tc["args"])
                    entry["duration_ms"] = int((time.perf_counter() - t0) * 1000)
                    entry["output_data"] = output
                    log.info("agent.tool_ok", tool=name, duration_ms=entry["duration_ms"])
                    content = json.dumps(output, indent=2, default=str)
                except Exception as exc:
                    entry["duration_ms"] = int((time.perf_counter() - t0) * 1000)
                    entry["error"] = str(exc)
                    log.error("agent.tool_fail", tool=name, error=str(exc), duration_ms=entry["duration_ms"])
                    content = json.dumps({"error": str(exc)})

                used.append(name)
                logs.append(entry)
                results.append(ToolMessage(content=content, tool_call_id=tc["id"]))

            return {"messages": results, "tools_used": used, "tool_logs": logs}

        async def call_sonnet(state: AgentState) -> dict:
            t0 = time.perf_counter()
            synthesis_addendum = (
                "\n\nProduce the final travel recommendation now. Write directly to the user as a "
                "knowledgeable friend would. Do NOT mention internal sources, tools, RAG, classifiers, "
                "or any technical infrastructure. Where information sources disagree, integrate them "
                "honestly in plain language — say 'the latest weather data shows X' or 'I'd double-check "
                "current flight prices', not 'the RAG said X but the live feed said Y'. The output must "
                "read as a polished travel plan from a human expert, not a debug log."
            )
            messages: list[BaseMessage] = (
                [SystemMessage(content=_SYSTEM_PROMPT + synthesis_addendum)]
                + list(state["messages"])
                + [HumanMessage(content="Now produce the final synthesized travel recommendation for the user, integrating all tool results above.")]
            )
            response = await self._llm_strong.ainvoke(messages)
            duration_ms = int((time.perf_counter() - t0) * 1000)

            counts = dict(state.get("token_counts", {}))
            usage = getattr(response, "usage_metadata", None)
            if usage:
                counts["sonnet_synthesis"] = dict(usage)

            log.info(
                "agent.sonnet",
                duration_ms=duration_ms,
                input_tokens=(usage or {}).get("input_tokens"),
                output_tokens=(usage or {}).get("output_tokens"),
            )
            return {"messages": [response], "token_counts": counts}

        def _route(state: AgentState) -> str:
            last = state["messages"][-1]
            if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
                return "tools"
            return "synthesize"

        g = StateGraph(AgentState)
        g.add_node("haiku", call_haiku)
        g.add_node("tools", execute_tools)
        g.add_node("sonnet", call_sonnet)
        g.set_entry_point("haiku")
        g.add_conditional_edges("haiku", _route, {"tools": "tools", "synthesize": "sonnet"})
        g.add_edge("tools", "haiku")
        g.add_edge("sonnet", END)
        return g.compile()

    async def arun(self, query: str, session: Any) -> AgentState:
        compiled = self._build_graph(session)
        initial: AgentState = {
            "messages": [HumanMessage(content=query)],
            "tools_used": [],
            "token_counts": {},
            "tool_logs": [],
        }
        result: AgentState = await compiled.ainvoke(initial)
        log.info(
            "agent.run_complete",
            tools_used=result.get("tools_used", []),
            token_counts=result.get("token_counts", {}),
        )
        return result