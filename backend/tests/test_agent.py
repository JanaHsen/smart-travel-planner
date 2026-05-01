"""
End-to-end agent test.

All external calls are mocked:
  - LLMs (Haiku & Sonnet) are replaced with fake models.
  - search_destinations is patched so rag_search never hits the DB.
  - The agent is invoked directly via TravelAgent.arun(); no HTTP layer involved.

The fake LLM emits one rag_search tool call on its first invocation, then a
plain synthesis message on subsequent invocations, exercising the full
haiku → tools → haiku → sonnet graph path.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from app.services.agent import TravelAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_call_llm() -> MagicMock:
    """
    LLM whose first ainvoke issues a rag_search tool call; subsequent calls
    return a plain synthesis message (no tool_calls).
    """
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "rag_search",
                "args": {"query": "beaches in Thailand", "top_k": 3},
                "id": "tc_test_001",
                "type": "tool_call",
            }
        ],
    )
    no_tool_msg = AIMessage(content="Based on the search, I recommend Koh Lanta.")

    llm = MagicMock()
    llm.bind_tools = MagicMock(return_value=llm)
    # call 1 (haiku): tool call  →  route to tools node
    # call 2 (haiku, after tools): no tool calls  →  route to sonnet
    # call 3 (sonnet): final synthesis
    llm.ainvoke = AsyncMock(side_effect=[tool_call_msg, no_tool_msg, no_tool_msg])
    return llm


_RAG_HITS = [
    {"text": "Koh Lanta has pristine beaches.", "source": "thailand.md", "score": 0.91, "metadata": {}},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_agent_end_to_end(fake_embedder, fake_classifier,fake_meta):
    """
    Invoke the agent with a sample query.  Assert:
      - The response text is non-empty.
      - tools_used contains the tool that was called.
      - No exceptions propagate out of arun().
    """
    llm = _make_tool_call_llm()
    agent = TravelAgent(
        llm_cheap=llm,
        llm_strong=llm,
        embedder=fake_embedder,
        ml_model=fake_classifier,
        ml_meta=fake_meta,
    )

    # Patch search_destinations so rag_search never touches the DB.
    with patch(
        "app.tools.rag_search.search_destinations",
        AsyncMock(return_value=_RAG_HITS),
    ):
        session = MagicMock()
        state = await agent.arun("What are the best beaches in Thailand?", session)

    # Response is non-empty
    last_message = state["messages"][-1]
    assert last_message.content, "Expected a non-empty response from the agent"

    # rag_search was recorded as used
    assert "rag_search" in state["tools_used"]

    # Tool logs contain the executed call
    assert any(log["tool_name"] == "rag_search" for log in state["tool_logs"])


async def test_agent_no_tool_calls(fake_embedder, fake_classifier, fake_meta):
    """
    When the LLM decides no tools are needed, tools_used is empty and the
    agent still produces a non-empty answer.
    """
    llm = MagicMock()
    response = AIMessage(content="Just visit Paris — no further research needed.")
    llm.bind_tools = MagicMock(return_value=llm)
    llm.ainvoke = AsyncMock(return_value=response)

    agent = TravelAgent(
        llm_cheap=llm,
        llm_strong=llm,
        embedder=fake_embedder,
        ml_model=fake_classifier,
        ml_meta=fake_meta,
    )

    state = await agent.arun("Where should I go in Europe?", MagicMock())

    assert state["messages"][-1].content
    assert state["tools_used"] == []
    assert state["tool_logs"] == []


async def test_agent_blocked_tool_is_rejected(fake_embedder, fake_classifier, fake_meta):
    """
    A tool call for a name not in ALLOWED_TOOLS must not execute and must
    return an error ToolMessage without raising.
    """
    disallowed_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "delete_all_data",  # not in ALLOWED_TOOLS
                "args": {},
                "id": "tc_bad_001",
                "type": "tool_call",
            }
        ],
    )
    safe_response = AIMessage(content="I cannot use that tool.")

    llm = MagicMock()
    llm.bind_tools = MagicMock(return_value=llm)
    llm.ainvoke = AsyncMock(side_effect=[disallowed_call, safe_response, safe_response])

    agent = TravelAgent(
        llm_cheap=llm,
        llm_strong=llm,
        embedder=fake_embedder,
        ml_model=fake_classifier,
        ml_meta=fake_meta,
    )

    # Should complete without raising even though the tool is blocked.
    state = await agent.arun("Do something dangerous", MagicMock())

    # The blocked tool must NOT appear in tools_used
    assert "delete_all_data" not in state["tools_used"]
    assert state["messages"][-1].content

async def test_agent_classify_destination_path(fake_embedder, fake_classifier, fake_meta):
    """
    The classify_destination tool fires end-to-end with the new 30-field schema.
    Validates that the meta sidecar is wired correctly and the tool produces
    a structured ClassifyOutput.
    """
    classify_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "classify_destination",
                "args": {
                    "destination_name": "Queenstown",
                    "num_hiking_trails": 60,
                    "extreme_sports_operator_count": 40,
                    "outdoor_to_indoor_attraction_ratio": 5.0,
                    "topographic_elevation_meters": 310,
                    # Other 26 fields will use defaults from ClassifyInput
                },
                "id": "tc_classify_001",
                "type": "tool_call",
            }
        ],
    )
    final_msg = AIMessage(content="Queenstown is an excellent adventure destination.")

    llm = MagicMock()
    llm.bind_tools = MagicMock(return_value=llm)
    llm.ainvoke = AsyncMock(side_effect=[classify_call, final_msg, final_msg])

    agent = TravelAgent(
        llm_cheap=llm,
        llm_strong=llm,
        embedder=fake_embedder,
        ml_model=fake_classifier,
        ml_meta=fake_meta,
    )

    state = await agent.arun("Tell me about Queenstown", MagicMock())

    # The tool fired and was recorded
    assert "classify_destination" in state["tools_used"]

    # The tool produced an output, not an error
    classify_log = next(
        log for log in state["tool_logs"] if log["tool_name"] == "classify_destination"
    )
    assert classify_log["error"] is None
    assert classify_log["output_data"]["label"] == "Adventure"
    assert classify_log["output_data"]["destination_name"] == "Queenstown"
    assert "fields_defaulted" in classify_log["output_data"]