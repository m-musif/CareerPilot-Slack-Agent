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
import time

import groq
from groq import Groq

import memory_store
from mcp_client import MCPClient

# 70b-versatile is far more reliable at structured tool calling. 8b-instant
# frequently emits malformed function calls that Groq rejects with a 400
# 'tool_use_failed' error, which broke research/roadmap queries. For a demo's
# message volume the 70b free-tier daily token limit is plenty.
MODEL = os.getenv("CAREERPILOT_MODEL", "llama-3.3-70b-versatile")
MAX_TOOL_ROUNDS = 3
# Cap how much of each past message we replay to the LLM to save tokens —
# job lists and roadmaps are long, and we don't need them verbatim as memory.
MAX_HISTORY_CHARS = 600

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
you earlier in the conversation.

CRITICAL — relaying tool output:
When a tool returns links, keywords, roadmap steps, or any structured content, \
you MUST include that content directly in your reply. Copy the actual links and \
keywords verbatim — do not shorten URLs and do not hide them. \
NEVER reply with a vague pointer such as "you can use these links and keywords" \
without actually showing them. The tool output is meant for the user to see, so \
present it in full, then add a short encouraging note or next step at the end."""

_client: Groq | None = None
_mcp: MCPClient | None = None


def init(mcp_client: MCPClient) -> None:
    global _client, _mcp
    _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    _mcp = mcp_client


# Transient Groq failures (server overload, timeouts, dropped connections) are
# common on the free tier. Retry these a few times so a single blip doesn't
# surface to the user as a generic error mid-demo. RateLimitError is handled
# separately in run() so it can show a clear "usage limit" message.
_TRANSIENT_ERRORS = (
    groq.APITimeoutError,
    groq.APIConnectionError,
    groq.InternalServerError,
)


def _create(messages: list[dict], tools: list[dict]):
    return _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools or None,
        tool_choice="auto" if tools else "none",
        temperature=0.6,
        max_tokens=700,
    )


def _chat(messages: list[dict], tools: list[dict]):
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            return _create(messages, tools)
        except _TRANSIENT_ERRORS as exc:
            last_exc = exc
            print(f"[agent] transient Groq error (attempt {attempt + 1}/3): {exc}")
            time.sleep(1.5 * (attempt + 1))
        except groq.BadRequestError as exc:
            # The model emitted a malformed tool call (Groq 'tool_use_failed').
            # Retry — it's stochastic and usually succeeds next time.
            if "tool_use_failed" not in str(exc):
                raise
            last_exc = exc
            print(f"[agent] malformed tool call, retrying (attempt {attempt + 1}/3)")
            time.sleep(0.5)
    # Retries exhausted on a malformed tool call: answer with no tools so the
    # model can't emit a bad call and the user still gets a real reply.
    if tools and isinstance(last_exc, groq.BadRequestError):
        print("[agent] falling back to a no-tool answer")
        return _create(messages, [])
    raise last_exc  # type: ignore[misc]


def _history_for_llm(user_id: str) -> list[dict]:
    """Recent turns, with long messages truncated to save tokens."""
    trimmed = []
    for msg in memory_store.get_history(user_id):
        content = msg.get("content", "")
        if len(content) > MAX_HISTORY_CHARS:
            content = content[:MAX_HISTORY_CHARS] + " …(truncated)"
        trimmed.append({"role": msg["role"], "content": content})
    return trimmed


def run(user_id: str, user_message: str) -> dict:
    """Run one turn for a user. Returns {answer, tools_used}."""
    if _client is None or _mcp is None:
        raise RuntimeError("agent.init() must be called first")

    tools = _mcp.tool_schemas()
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_history_for_llm(user_id))
    messages.append({"role": "user", "content": user_message})

    tools_used: list[str] = []
    tool_cache: dict[str, str] = {}
    # Raw, user-ready outputs from tools (links, job lists, roadmaps). We show
    # these directly so the model can't summarise them away into a vague reply.
    display_outputs: list[str] = []

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            response = _chat(messages, tools)
            choice = response.choices[0].message

            if not choice.tool_calls:
                answer = _compose_answer(choice.content, display_outputs)
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
                        if not result.lower().startswith("tool '"):
                            display_outputs.append(result)
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
        answer = _compose_answer(final.choices[0].message.content, display_outputs)
    except groq.RateLimitError:
        # Daily/temporary token cap hit. If a tool already produced output,
        # still show it; otherwise explain clearly instead of a generic error.
        if display_outputs:
            return {"answer": _compose_answer(None, display_outputs),
                    "tools_used": tools_used}
        return {
            "answer": (
                "⚠️ I've hit today's AI usage limit (Groq free tier).\n"
                "Please try again later, or ask an admin to add credits / "
                "switch the model. Your message was received — nothing broke."
            ),
            "tools_used": tools_used,
        }
    except Exception as exc:  # noqa: BLE001
        # Log the real error so it's visible in the terminal for debugging,
        # then degrade gracefully — show any tool output we already gathered.
        import traceback
        print(f"[agent] unexpected error: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        if display_outputs:
            return {"answer": _compose_answer(None, display_outputs),
                    "tools_used": tools_used}
        return {
            "answer": (
                "⚠️ I hit a temporary hiccup reaching the AI service. "
                "Please send that again in a moment — nothing broke."
            ),
            "tools_used": tools_used,
        }

    memory_store.add_message(user_id, "user", user_message)
    memory_store.add_message(user_id, "assistant", answer)
    return {"answer": answer, "tools_used": tools_used}


def _compose_answer(model_text: str | None, display_outputs: list[str]) -> str:
    """Guarantee tool output reaches the user.

    Tool results (job lists, links, roadmaps) are already Slack-formatted and
    meant to be shown. If a tool ran, we present its output directly and append
    the model's short note only when it adds something (and isn't itself a
    vague 'here are some links' placeholder that hides the real content).
    """
    note = (model_text or "").strip()
    if not display_outputs:
        return note or "(no response)"

    combined = "\n\n".join(display_outputs)
    # Keep the model's note only if it's a genuine short add-on, not a
    # placeholder and not something that would duplicate the tool content.
    if note and "http" not in note.lower() and len(note) <= 400:
        return f"{combined}\n\n{note}"
    return combined
