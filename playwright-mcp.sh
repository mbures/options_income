#!/bin/bash
# Wrapper to run Playwright MCP connected to existing headless Chrome
export PLAYWRIGHT_CHROMIUM_SANDBOX=0
exec npx @playwright/mcp@latest --cdp-endpoint http://localhost:9222 "$@"
