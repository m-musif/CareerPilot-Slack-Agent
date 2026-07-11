"""
CareerPilot agent: Groq LLM + MCP tool-calling + per-user memory.

Flow:
  1. Load the user's recent history from SQLite.
  2. Send system prompt + history + new message to Groq with MCP tool schemas.
  3. If the model requests tools, execute them via the MCP client and loop.
  4. Persist the exchange and return the final answer + metadata.
"""
from __future__ import annotations

import json
import os

from groq import Groq

import memory_store
from mcp_client import MCPClient

# 70B model is far more reliable at tool-calling than 8b-instant.
MODEL = os.getenv("CAREERPILOT_MODEL", "llama-3.3-70b-versatile")
MAX_TOOL_ROUNDS = 3

SYSTEM_PROMPT = """You are CareerPilot, an AI career teammate living inside Slack.

You help with career roadmaps, internships, resume/LinkedIn tips, interview \
prep, and research summaries for CS/AI students and early-career engineers.

You have access to tools (via an MCP server):
- search_jobs: build targeted job-search links and keywords for a role
- analyze_resume: score a resume against a target role's keywords
- learning_roadmap: return a step-by-step roadmap for a skill

Use a tool whenever it clearly helps (job hunting, resume review, learning a \
skill). Otherwise answer directly. Be concise, practical, and encouraging. \
Format for Slack using *bold* and bullet points. Remember what the user told \
you earlier in the conversation."""

_client: Groq | None = None
_mcp: MCPClient | None = None


def init(mcp_client: MCPClient) -> None:
    global _client, _mcp
    _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    _mcp = mcp_client


def _chat(messages: list[dict], tools: list[dict]):
    return _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools or None,
        tool_choice="auto" if tools else "none",
        temperature=0.6,
        max_tokens=700,
    )


def run(user_id: str, user_message: str) -> dict:
    """Run one turn for a user. Returns {answer, tools_used}."""
    if _client is None or _mcp is None:
        raise RuntimeError("agent.init() must be called first")

    tools = _mcp.tool_schemas()
    history = memory_store.get_history(user_id)
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    tools_used: list[str] = []
    tool_cache: dict[str, str] = {}

    for _ in range(MAX_TOOL_ROUNDS):
        response = _chat(messages, tools)
        choice = response.choices[0].message

        if not choice.tool_calls:
            answer = choice.content or "(no response)"
            memory_store.add_message(user_id, "user", user_message)
            memory_store.add_message(user_id, "assistant", answer)
            return {"answer": answer, "tools_used": tools_used}

        # Append the assistant turn that requested tools.
        messages.append(
            {
                "role": "assistant",
                "content": choice.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.tool_calls
                ],
            }
        )

        for tc in choice.tool_calls:
            name = tc.function.name
            raw_args = tc.function.arguments or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
            signature = f"{name}:{raw_args}"
            if signature in tool_cache:
                # Model repeated an identical call — reuse the result.
                result = tool_cache[signature]
            else:
                try:
                    result = _mcp.call_tool(name, args)
                    tools_used.append(name)
                except Exception as exc:  # noqa: BLE001
                    result = f"Tool '{name}' failed: {exc}"
                tool_cache[signature] = result
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )

    # Ran out of tool rounds — ask for a final answer without tools.
    final = _chat(messages, [])
    answer = final.choices[0].message.content or "(no response)"
    memory_store.add_message(user_id, "user", user_message)
    memory_store.add_message(user_id, "assistant", answer)
    return {"answer": answer, "tools_used": tools_used}
