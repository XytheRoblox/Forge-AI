FROM node:20-slim

WORKDIR /app

RUN npm install -g firecrawl-mcp

EXPOSE 8000

CMD ["npx", "firecrawl-mcp", "--port", "8000", "--transport", "sse"]
