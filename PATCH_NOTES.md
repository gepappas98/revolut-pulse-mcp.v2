# mcprice v2.1 — Patch Notes

## Files changed

| File | Status |
|------|--------|
| `app.py` | ✅ Fixed (7 bugs) |
| `requirements.txt` | ✅ Fixed (added yfinance) |
| `Dockerfile` | ✅ Fixed (2 bugs) |
| `fly.toml` | ✅ Fixed (1 bug) |
| `docker-compose.yml` | ✅ Fixed (2 bugs) |
| `mcp.json` | ✅ Fixed (1 bug) |

---

## Bug list (all 13)

### app.py

**#1 — Semaphore module-level crash** `🔴 Critical`
`asyncio.Semaphore(5)` at module level crashes Python 3.12 with
`RuntimeError: no running event loop`. Fixed with lazy init inside `_get_semaphore()`.

**#2 — Yahoo null-result IndexError** `🔴 Critical`
`data["chart"]["result"][0]` raised `IndexError` / `TypeError` when Yahoo returned
`"result": null` for unknown tickers or rate-limiting. Added explicit null guard.

**#3 — Yahoo Finance blocked on cloud IPs** `🔴 Critical`
Railway / Fly.io / Render IPs get 401/429/503 from Yahoo's raw API. Replaced raw
`httpx` calls with `yfinance` which handles cookie/crumb auth automatically.

**#4 — Config JSON files never loaded** `🟠 High`
`config/revolut_stocks.json` and `config/revolut_crypto.json` were completely
ignored — `app.py` used only hardcoded dicts. Added `_load_config()` with graceful
fallback.

**#6 — Cache stampede** `🟠 Medium`
Concurrent cache misses for the same ticker fired multiple simultaneous HTTP
requests. Fixed with `_in_flight` dict deduplication.

**#7 — Untyped `list` parameter** `🟡 Low`
`tickers: list` is ambiguous in MCP schema. Changed to `List[str]` everywhere.

**#8 — Binance 429 not handled separately** `🟡 Low`
HTTP 429 was treated identically to other errors (0.5s backoff). Now detects
`Retry-After` header and waits 60s.

---

### Dockerfile

**#9 — `config/` folder not copied** `🔴 Critical`
`COPY config/ ./config/` was missing. Even after fixing `_load_config()` in
`app.py`, the JSON files never existed inside the Docker image — always fell back
to hardcoded lists.

**#10 — PORT mismatch** `🟠 High`
`Dockerfile` defaulted `PORT=8000` but `fly.toml` injects `PORT=8080`. The app
listened on 8000 while Fly.io forwarded to 8080 → connection refused. Fixed
`ENV PORT=8080` and `EXPOSE 8080`.

---

### fly.toml

**#11 — Cold start kills MCP sessions** `🔴 Critical`
`min_machines_running = 0` let the VM sleep between requests. MCP clients
expect responses in <2s; Fly.io cold starts take 10–20s → timeout / disconnect.
Changed to `min_machines_running = 1`.

---

### docker-compose.yml

**#12 — Healthcheck hit wrong endpoint** `🟠 High`
`httpx.get('.../health')` on the MCP service returned 404 (MCP server has no
`/health` route, only `/mcp`). Docker marked container as unhealthy and kept
restarting it. Fixed to `HEAD /mcp`.

**#13 — Deprecated `version` key** `🟡 Low`
`version: "3.9"` is ignored by modern Docker Compose and produces warnings.
Removed.

---

### mcp.json

**#5 (README) — Wrong clone URL** `🟠 High`
README said `git clone https://github.com/gepappas98/mcprice.git` (wrong repo).
`mcp.json` also referenced wrong paths. Fixed to correct repo name and added both
local (uv) and remote (streamable-http) configs.

---

## Quick install (after cloning correct repo)

```bash
# 1. Clone
git clone https://github.com/gepappas98/revolut-pulse-mcp.v2.git
cd revolut-pulse-mcp.v2

# 2. Local MCP mode (stdio)
uv run --with fastmcp,httpx,yfinance python app.py

# 3. API mode
pip install -r requirements-api.txt
uvicorn api.main:app --port 8001

# 4. Docker (full stack)
docker compose up

# 5. Fly.io deploy
flyctl launch --name mcprice --region ams
flyctl deploy
```
