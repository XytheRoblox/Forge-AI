FROM python:3.11-slim

WORKDIR /app

# Node, for the MCP servers published as npm packages. The agent container
# hosts its own capabilities as stdio subprocesses rather than talking to
# shared capability containers over the network, which is what lets each agent
# carry its OWN credentials (a shared container can only ever hold one token)
# and its own private scratch space.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Capability servers, baked in rather than fetched at run time so a deployed
# agent doesn't depend on npm/PyPI being reachable — and so the first tool call
# isn't a download. One image serves every agent; which servers actually start
# is decided per agent from its own capabilities.json.
RUN pip install --no-cache-dir mcp-server-fetch mcp-server-time
RUN npm install -g --no-fund --no-audit \
      @modelcontextprotocol/server-filesystem \
      @modelcontextprotocol/server-github \
      @modelcontextprotocol/server-sequential-thinking \
    && npm cache clean --force

# The Google server is ours rather than an npm package, so it's copied in.
COPY google_server.py /app/google_server.py

# Per-agent scratch space for the filesystem capability. Previously this was
# one named volume shared by every agent on the host.
RUN mkdir -p /scratch

COPY app.py .

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
