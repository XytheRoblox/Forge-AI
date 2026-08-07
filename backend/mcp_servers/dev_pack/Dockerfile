FROM node:20-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --break-system-packages "mcp==1.29.0" mcp-proxy
RUN npm install -g @modelcontextprotocol/server-filesystem @modelcontextprotocol/server-github
RUN mkdir -p /scratch
EXPOSE 8000
CMD ["mcp-proxy", "--port", "8000", "--host", "0.0.0.0", "--pass-environment", \
     "--named-server", "filesystem", "mcp-server-filesystem /scratch", \
     "--named-server", "github", "mcp-server-github"]
