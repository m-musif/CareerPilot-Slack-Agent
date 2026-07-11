"""
CareerTools MCP Server
======================
A Model Context Protocol server exposing career-focused tools that
CareerPilot's agents call over stdio. Runs as a standalone process and
speaks the MCP protocol, satisfying the Slack Agent Builder "MCP server
integration" requirement.

Tools:
  * search_jobs          - build targeted job-search queries + board links
  * analyze_resume       - keyword-gap analysis for a target role
  * learning_roadmap     - structured upskilling roadmap for a skill

Run standalone (for debugging):
    python career_tools_server.py
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("career-tools")

# --- Curated knowledge bases (offline-safe, no external API needed) ---------

ROLE_KEYWORDS: dict[str, list[str]] = {
    "backend": [
        "python", "java", "node", "api", "rest", "sql", "postgres",
        "docker", "microservices", "redis", "testing", "ci/cd", "aws",
    ],
    "frontend": [
        "react", "javascript", "typescript", "css", "html", "tailwind",
        "vite", "accessibility", "responsive", "state management", "testing",
    ],
    "ai": [
        "python", "pytorch", "tensorflow", "llm", "rag", "nlp",
        "transformers", "fine-tuning", "vector database", "prompt", "ml",
    ],
    "ml": [
        "python", "pytorch", "scikit-learn", "pandas", "numpy", "model",
        "training", "evaluation", "feature engineering", "deployment",
    ],
    "data": [
        "sql", "python", "pandas", "etl", "warehouse", "spark",
        "visualization", "statistics", "dashboard", "pipeline",
    ],
    "fullstack": [
        "react", "node", "api", "sql", "docker", "rest", "typescript",
        "python", "deployment", "git", "testing",
    ],
}

ROADMAPS: dict[str, list[str]] = {
    "python": [
        "Syntax, data types, control flow, functions",
        "Data structures: lists, dicts, sets, comprehensions",
        "OOP: classes, inheritance, dunder methods",
        "Files, exceptions, modules, virtual environments",
        "Popular libs: requests, pytest, FastAPI",
        "Build a project: REST API or CLI tool",
    ],
    "react": [
        "JSX, components, props, state",
        "Hooks: useState, useEffect, useContext",
        "Lists, conditional rendering, forms",
        "Routing with react-router",
        "Data fetching + state management",
        "Build a project: dashboard consuming an API",
    ],
    "rag": [
        "Embeddings + why vector search",
        "Chunking strategies for documents",
        "Vector DB: FAISS / Chroma basics",
        "Retriever + prompt assembly",
        "LLM answer generation with citations",
        "Build a project: doc Q&A chatbot",
    ],
    "llm": [
        "Tokenization + how transformers work (intuition)",
        "Prompt engineering fundamentals",
        "Function/tool calling",
        "RAG for grounding",
        "Fine-tuning vs prompting trade-offs",
        "Build a project: multi-agent assistant",
    ],
    "docker": [
        "Images vs containers",
        "Writing a Dockerfile",
        "docker build / run / exec",
        "Volumes + environment variables",
        "docker-compose for multi-service apps",
        "Deploy a containerized API",
    ],
}


def _normalize_role(role: str) -> str:
    r = role.lower()
    for key in ROLE_KEYWORDS:
        if key in r:
            return key
    if "full" in r and "stack" in r:
        return "fullstack"
    return "backend"


@mcp.tool()
def search_jobs(role: str, location: str = "Remote", seniority: str = "internship") -> str:
    """Build targeted job-search queries and direct board links for a role.

    Args:
        role: Target role, e.g. "backend developer", "AI engineer".
        location: City or "Remote". Defaults to Remote.
        seniority: internship | junior | mid | senior. Defaults to internship.
    """
    query = f"{seniority} {role} {location}".strip()
    q = quote_plus(query)
    links = {
        "LinkedIn": f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(role + ' ' + seniority)}&location={quote_plus(location)}",
        "Indeed": f"https://www.indeed.com/jobs?q={q}",
        "Wellfound (startups)": f"https://wellfound.com/role/r/{quote_plus(role.replace(' ', '-'))}",
        "Google Jobs": f"https://www.google.com/search?q={q}+jobs",
    }
    key = _normalize_role(role)
    must_have = ", ".join(ROLE_KEYWORDS[key][:6])

    lines = [f"*Job search plan for:* {seniority} {role} — {location}", ""]
    lines.append("*Direct search links:*")
    for name, url in links.items():
        lines.append(f"• <{url}|{name}>")
    lines.append("")
    lines.append(f"*Keywords to put in your search & resume:* {must_have}")
    lines.append("")
    lines.append("*Tips:* apply within 24h of posting, tailor the first resume "
                 "bullet to the role, and DM a recruiter after applying.")
    return "\n".join(lines)


@mcp.tool()
def analyze_resume(resume_text: str, target_role: str = "backend") -> str:
    """Analyze resume text for keyword coverage against a target role.

    Args:
        resume_text: The resume or bullet points to analyze.
        target_role: Target role to match against (e.g. "backend", "AI").
    """
    key = _normalize_role(target_role)
    expected = ROLE_KEYWORDS[key]
    text = resume_text.lower()
    tokens = set(re.findall(r"[a-z0-9\+/#\.]+", text))

    present, missing = [], []
    for kw in expected:
        if kw in text or kw in tokens:
            present.append(kw)
        else:
            missing.append(kw)

    score = round(100 * len(present) / len(expected)) if expected else 0
    lines = [
        f"*Resume match for {key} role: {score}%*",
        "",
        f"*Covered ({len(present)}):* " + (", ".join(present) or "none"),
        f"*Missing ({len(missing)}):* " + (", ".join(missing) or "none"),
    ]
    if missing:
        lines += [
            "",
            "*Suggested actions:*",
            f"• Add concrete projects showing: {', '.join(missing[:4])}",
            "• Quantify impact (numbers, %, users, latency)",
            "• Mirror the exact keywords from the job description",
        ]
    else:
        lines.append("\nStrong keyword coverage — focus on quantified impact next.")
    return "\n".join(lines)


@mcp.tool()
def learning_roadmap(skill: str, level: str = "beginner") -> str:
    """Return a structured, step-by-step learning roadmap for a skill.

    Args:
        skill: Skill to learn, e.g. "python", "react", "rag", "docker".
        level: beginner | intermediate. Defaults to beginner.
    """
    s = skill.lower().strip()
    steps = None
    for key, plan in ROADMAPS.items():
        if key in s:
            steps = plan
            break
    if steps is None:
        return (
            f"No curated roadmap for '{skill}' yet. General path:\n"
            "1. Learn the fundamentals from official docs\n"
            "2. Follow one high-quality tutorial end-to-end\n"
            "3. Build a small project from scratch\n"
            "4. Read others' code and refactor yours\n"
            "5. Ship it publicly (GitHub + short demo)"
        )
    start = 0 if level == "beginner" else max(0, len(steps) // 3)
    numbered = [f"{i+1}. {step}" for i, step in enumerate(steps[start:])]
    return f"*Learning roadmap for {skill} ({level}):*\n" + "\n".join(numbered)


if __name__ == "__main__":
    mcp.run()
