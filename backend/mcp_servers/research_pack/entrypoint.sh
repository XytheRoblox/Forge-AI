#!/bin/bash
set -e
ARGS=(--port 8000 --host 0.0.0.0 --pass-environment)
ARGS+=(--named-server fetch "python3 -m mcp_server_fetch")
ARGS+=(--named-server time "python3 -m mcp_server_time")
ARGS+=(--named-server sequential_thinking "mcp-server-sequential-thinking")
# Every server in this pack is keyless. If a keyed one is ever added back,
# guard it the way brave_search used to be — a named server that hard-exits
# for want of its key takes the whole pack container down with it.
exec mcp-proxy "${ARGS[@]}"
