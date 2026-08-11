FROM node:20-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --break-system-packages "mcp==1.29.0" mcp-server-fetch mcp-server-time mcp-proxy
RUN npm install -g @modelcontextprotocol/server-sequential-thinking
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8000
CMD ["/entrypoint.sh"]
