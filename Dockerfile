FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY slack_app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app + MCP server
COPY slack_app/ ./slack_app/
COPY mcp_server/ ./mcp_server/

# Socket Mode needs no inbound port; run as a long-lived worker.
CMD ["python", "-u", "slack_app/careerpilot.py"]
