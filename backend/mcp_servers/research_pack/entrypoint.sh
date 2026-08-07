#!/bin/bash
set -e
ARGS=(--port 8000 --host 0.0.0.0 --pass-environment)
ARGS+=(--named-server fetch "python3 -m mcp_server_fetch")
ARGS+=(--named-server time "python3 -m mcp_server_time")
ARGS+=(--named-server sequential_thinking "mcp-server-sequential-thinking")
# Only start brave_search if its key is actually configured — it hard-exits
# at startup without one, which (before this script existed) took the whole
# pack container down with it. Omitting it here just means that one
# capability isn't available yet; the rest of the pack still starts fine.
if [ -n "$BRAVE_API_KEY" ]; then
  ARGS+=(--named-server brave_search "mcp-server-brave-search")
fi
exec mcp-proxy "${ARGS[@]}"
