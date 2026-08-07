FROM mcr.microsoft.com/playwright:latest

WORKDIR /app

RUN npm install -g @playwright/mcp@latest

# @playwright/mcp bundles its own (often newer) playwright-core, whose
# expected browser build can differ from what the base image preinstalled —
# install the matching build for the copy it actually uses at runtime.
RUN node /usr/lib/node_modules/@playwright/mcp/node_modules/playwright-core/cli.js install chromium

EXPOSE 8931

CMD ["playwright-mcp", "--host", "0.0.0.0", "--port", "8931", "--browser", "chromium", "--headless", "--isolated", "--allowed-hosts", "*"]
