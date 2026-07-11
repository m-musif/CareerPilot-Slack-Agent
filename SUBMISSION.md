# CareerPilot — Devpost Submission Kit

Everything you need to paste into the Devpost form. Track: **New Slack Agent**.

---

## Project name

**CareerPilot — AI Career Teammate for Slack**

## Elevator pitch (one line, ~200 chars)

An AI teammate inside Slack that gives students grounded career help — job
search, resume keyword analysis, and learning roadmaps — using MCP tools and
persistent per-user memory.

---

## About the project (main description)

### The problem

Career guidance is scattered across job boards, resume checkers, and blog
posts — and none of it lives where communities actually work. Students and
early-career engineers waste hours context-switching, and generic AI chatbots
hallucinate advice with no memory of who you are or what you already asked.

### The solution

**CareerPilot** is an AI career teammate that lives inside Slack. Ask it in a
DM, an `@mention`, or with a slash command — it remembers your conversation and
calls real tools to give grounded answers:

- **`/career`** — internships, roadmaps, interview prep
- **`/research`** — technical explanations and summaries
- **`/resume`** — resume/LinkedIn keyword-gap analysis
- **`/forget`** — clears your memory for a fresh start
- **DM & @mention** — natural conversation with memory

Instead of guessing, CareerPilot routes to tools served over the **Model
Context Protocol (MCP)**: a job-search builder, a resume keyword analyzer, and a
structured roadmap generator. Every reply shows which tools it used, so advice
is transparent and grounded.

### How we built it

- **Bolt for Python** on **Socket Mode** handles Slack events (slash commands,
  DMs, mentions, App Home).
- A **CareerTools MCP server** (built with the `mcp` Python SDK / FastMCP)
  exposes three tools over stdio.
- The **agent** runs a **Groq `llama-3.3-70b`** function-calling loop: it loads
  the user's memory, decides which MCP tools to call, executes them, and
  synthesizes a final answer.
- **SQLite** stores per-user memory, isolated by Slack user ID.
- A **supervisor loop** auto-reconnects through transient network drops.

### What makes it stand out

- **Real MCP integration**, not just an LLM wrapper — tools are decoupled and
  reusable by any MCP client.
- **Per-user memory** makes it feel like a teammate, not a stateless bot.
- **Tool transparency** ("🔧 Used MCP tools: …") builds trust with users.

### Challenges

- Bridging **synchronous Bolt handlers** with the **async MCP SDK** — solved
  with a persistent background event loop and a sync wrapper.
- Making tool-calling reliable and avoiding duplicate tool calls (added a
  per-turn tool cache and bounded tool rounds).
- Network resilience for a live demo — added an auto-reconnect supervisor.

### What's next

- Slack MCP server integration to read/search workspace context.
- More tools: mock-interview generator, referral-message drafts.
- Cloud deployment for an always-on "Try it out" install link.

---

## Built with (tags)

`python` · `slack` · `bolt-for-python` · `socket-mode` · `mcp` ·
`model-context-protocol` · `groq` · `llama` · `sqlite` · `fastmcp`

---

## Submission checklist

- [ ] GitHub repo public with README
- [ ] ~3-min demo video (shows a real Slack workspace)
- [ ] Architecture diagram uploaded (see below)
- [ ] 3–5 screenshots (job search, resume analysis, roadmap, memory, /forget)
- [ ] Slack developer sandbox URL
- [ ] Give judges access: `slackhack@salesforce.com`, `testing@devpost.com`
- [ ] Slack **App ID** noted
- [ ] Submit before **Jul 13, 2026 @ 5:00 PM PDT** (Jul 14, 5:00 AM PKT)

---

## How to export the architecture diagram (PNG for Devpost)

1. Open [mermaid.live](https://mermaid.live)
2. Paste the `mermaid` block from `README.md` (the flowchart)
3. Click **Actions → PNG** to download a clean diagram image
4. Upload it to Devpost as the architecture diagram

---

## 3-minute demo video script

**(0:00–0:20) Hook + problem**
> "Career advice is scattered everywhere and forgets who you are. Meet
> CareerPilot — an AI career teammate that lives inside Slack, remembers you,
> and uses real tools to give grounded answers."

**(0:20–0:45) Show it in Slack**
- Open the CareerPilot DM. Say: "This runs in a real Slack workspace using Bolt
  for Python over Socket Mode."
- Type: `/help` → show the commands.

**(0:45–1:20) MCP tools in action**
- Type: `Find me backend internships in Islamabad`
  → point out the job links and **"🔧 Used MCP tools: search_jobs"**.
- Type: `/resume Built a FastAPI app with Docker and Postgres`
  → show the keyword match score and gaps → **analyze_resume**.
- Type: `Give me a learning roadmap for RAG`
  → show the structured roadmap → **learning_roadmap**.
> "These aren't hardcoded replies — they come from a CareerTools MCP server the
> agent calls over the Model Context Protocol."

**(1:20–2:00) Memory (the wow moment)**
- Type: `My name is Musif and I want an AI internship`
- Then: `What did I tell you about myself?`
  → CareerPilot recalls the name and goal.
> "Memory is per-user and persistent, stored in SQLite — so it feels like a
> teammate, not a stateless bot."
- Type: `/forget` → "and you're always in control of your data."

**(2:00–2:40) Architecture**
- Show the architecture diagram.
> "Slack events hit a Bolt app over Socket Mode. The agent loads memory, then
> runs a Groq tool-calling loop against an MCP server that owns the tools. It's
> modular — the same MCP tools work with any MCP client."

**(2:40–3:00) Close**
> "CareerPilot brings grounded, tool-backed, memory-aware career help right into
> Slack — where communities already work. Thanks for watching."

---

## Suggested screenshots (take 3–5)

1. `/help` output (shows all commands)
2. Job search reply with "🔧 Used MCP tools: search_jobs"
3. `/resume` keyword match score
4. RAG learning roadmap reply
5. Memory recall ("You told me your name is Musif…")
