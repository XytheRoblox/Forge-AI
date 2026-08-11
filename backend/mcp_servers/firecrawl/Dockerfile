FROM node:20-slim

WORKDIR /app

# Pinned deliberately. firecrawl-mcp 3.x dropped the SSE transport this
# platform speaks (mcp_manager wires every capability up over SSE, and the
# agent runtime connects with mcp.client.sse) — on 3.x the process starts a
# stateless "HTTP Stream" server at /mcp instead, never binds a reachable
# port, and exits 0 immediately when invoked with the CLI flags that used to
# select SSE. 2.1.0 is the newest release that still serves /sse.
RUN npm install -g firecrawl-mcp@2.1.0

# 2.1.0 takes its transport config from the environment, not from argv:
# SSE_LOCAL switches it off stdio, PORT is what it binds.
ENV SSE_LOCAL=true
ENV PORT=8000

EXPOSE 8000

CMD ["npx", "firecrawl-mcp"]
