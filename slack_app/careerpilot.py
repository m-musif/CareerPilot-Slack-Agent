"""
CareerPilot Slack Agent
=======================
AI career teammate inside Slack. Uses Groq for reasoning, an MCP server
(CareerTools) for real tools, and per-user SQLite memory.

Run:  python careerpilot.py   (Socket Mode)
"""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv(Path(__file__).parent / ".env")

import agent  # noqa: E402
import memory_store  # noqa: E402
from mcp_client import MCPClient  # noqa: E402

app = App(token=os.environ["SLACK_BOT_TOKEN"])

HELP_TEXT = """*CareerPilot* — your AI career teammate

*Slash commands*
• `/career [question]` — internships, roadmaps, interview prep
• `/research [topic]` — summaries and technical explanations
• `/resume [text]` — resume & LinkedIn tips (keyword analysis)
• `/forget` — clear my memory of our conversation
• `/help` — this message

*DM mode*
Just message me directly — I remember our conversation and use tools \
(job search, resume analysis, learning roadmaps) when helpful.

*Examples*
`/career Find me backend internships in Islamabad`
`/resume Built a FastAPI app with Docker and Postgres`
`/research Explain RAG in simple terms`"""


def _blocks(answer: str, footer: str):
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": answer[:3000]}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]},
    ]


def _footer(tools_used: list[str]) -> str:
    if tools_used:
        unique = ", ".join(dict.fromkeys(tools_used))
        return f"_🔧 Used MCP tools: {unique}_"
    return "_CareerPilot_"


def _answer(user_id: str, text: str):
    result = agent.run(user_id, text)
    return result["answer"], _footer(result["tools_used"])


def _handle_command(ack, respond, command, prefix: str, usage: str):
    ack()
    text = (command.get("text") or "").strip()
    if not text:
        respond(f"Usage: `{usage}`")
        return
    user_id = command["user_id"]
    try:
        answer, footer = _answer(user_id, f"{prefix}{text}")
        respond(blocks=_blocks(answer, footer), text=answer[:3000])
    except Exception:
        respond("Sorry, something went wrong. Try again in a moment.")


@app.command("/career")
def handle_career(ack, respond, command):
    _handle_command(ack, respond, command, "", "/career Find backend internships in Islamabad")


@app.command("/research")
def handle_research(ack, respond, command):
    _handle_command(ack, respond, command, "Research and explain: ", "/research Explain RAG")


@app.command("/resume")
def handle_resume(ack, respond, command):
    _handle_command(ack, respond, command, "Review my resume: ", "/resume Built a FastAPI app")


@app.command("/forget")
def handle_forget(ack, respond, command):
    ack()
    count = memory_store.clear_history(command["user_id"])
    respond(f"Cleared {count} messages from my memory. Fresh start! 🧹")


@app.command("/help")
def handle_help(ack, respond):
    ack()
    respond(HELP_TEXT)


@app.event("app_mention")
def handle_mention(event, say):
    text = event.get("text", "").split(">", 1)[-1].strip()
    if not text:
        say(HELP_TEXT, thread_ts=event.get("ts"))
        return
    answer, footer = _answer(event["user"], text)
    say(blocks=_blocks(answer, footer), text=answer[:3000], thread_ts=event.get("ts"))


@app.event("message")
def handle_dm(event, say, logger):
    if event.get("bot_id") or event.get("subtype"):
        return
    if event.get("channel_type") != "im":
        return
    text = (event.get("text") or "").strip()
    if not text:
        return
    try:
        answer, footer = _answer(event["user"], text)
        say(blocks=_blocks(answer, footer), text=answer[:3000])
    except Exception as exc:  # noqa: BLE001
        logger.exception(exc)
        say("Sorry, something went wrong. Try `/help` or a shorter message.")


@app.event("app_home_opened")
def handle_home(event, client):
    client.views_publish(
        user_id=event["user"],
        view={
            "type": "home",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "CareerPilot"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": HELP_TEXT}},
            ],
        },
    )


def main():
    print("Starting CareerTools MCP server...")
    mcp = MCPClient().start()
    print(f"MCP ready — {len(mcp.list_tools())} tools: "
          f"{', '.join(t.name for t in mcp.list_tools())}")
    agent.init(mcp)

    # Supervisor loop: survive transient network / DNS drops instead of dying.
    backoff = 5
    while True:
        try:
            handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
            print("CareerPilot is running (Socket Mode). Press Ctrl+C to stop.")
            handler.start()  # blocks; returns/raises only on fatal disconnect
            print("Socket Mode handler stopped — reconnecting...")
        except KeyboardInterrupt:
            print("Shutting down.")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"Connection error: {exc}. Retrying in {backoff}s...")
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    main()
