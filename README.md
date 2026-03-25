# mcprice ⚡ — Free Stock & Crypto Price MCP Server (No API Key)

> **Real-time stock prices & crypto prices for Claude, Cursor, Cline, and any AI agent.**
> Yahoo Finance · Binance · Revolut availability check · Zero API keys · Free forever.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)
[![Deploy on Fly.io](https://img.shields.io/badge/Fly.io-deploy-purple?logo=fly.io)](https://fly.io)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MCP Server](https://img.shields.io/badge/MCP-server-orange)](https://mcpize.com/mcp/mcprice)

---

## What is mcprice?

**mcprice** is a free, open-source MCP server that gives Claude, Cursor, and other AI agents
**live stock prices, ETF prices, and real-time crypto prices** — with no API key, no paid tier,
and no setup friction.

Ask Claude things like:

> *"What is the current NVDA price and can I buy it on Revolut?"*
> *"Show me the top crypto gainers today."*
> *"Give me a snapshot of my watchlist: AAPL, TSLA, BTC, ETH."*

| Mode | What it does | Who uses it |
|------|-------------|-------------|
| **MCP Server** | Claude / Cursor / Cline tool calls | AI developers |
| **REST API** | Plain HTTP endpoints | Web apps, bots, scripts |
| **SEO Engine** | Generates 150+ static pages | Organic traffic |

---

## Why mcprice?

| | mcprice | Alpha Vantage MCP | Financial Datasets MCP |
|--|---------|------------------|----------------------|
| **API Key required** | ❌ None | ✅ Required | ✅ Required (paid) |
| **Stocks** | ✅ Yahoo Finance | ✅ | ✅ |
| **Crypto (real-time)** | ✅ Binance | ❌ | ❌ |
| **Revolut availability** | ✅ Built-in | ❌ | ❌ |
| **Top movers** | ✅ Binance 24h | ❌ | ❌ |
| **Self-hostable** | ✅ Docker / Fly.io | ✅ | ✅ |
| **Cost** | 🆓 Free | Freemium | Paid |

---

## Quick Start (2 minutes)

### Option A — MCP Mode (Claude Desktop / Cursor / Cline)

```bash
git clone https://github.com/gepappas98/revolut-pulse-mcp.v2.git
cd revolut-pulse-mcp.v2
uv run --with fastmcp,httpx,yfinance python app.py
```

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcprice": {
      "command": "uv",
      "args": ["run", "--with", "fastmcp,httpx,yfinance", "python", "app.py"],
      "cwd": "/path/to/revolut-pulse-mcp.v2"
    }
  }
}
```

### Option B — REST API Mode

```bash
pip install -r requirements-api.txt
uvicorn api.main:app --port 8001
```

```bash
# Live stock price
curl http://localhost:8001/price/NVDA

# Real-time crypto price
curl http://localhost:8001/crypto/BTC

# Is it tradeable on Revolut?
curl http://localhost:8001/revolut/check/LMT
```

### Option C — Remote MCP (no install)

Add to your MCP client config and connect instantly:

```json
{
  "mcpServers": {
    "mcprice": {
      "type": "streamable-http",
      "url": "https://mcprice.fly.dev/mcp"
    }
  }
}
```

---

## MCP Tools (6 total)

| Tool | Description | Data Source |
|------|-------------|-------------|
| `get_price("NVDA")` | Live price + 24h change + Revolut flag | Yahoo Finance |
| `get_prices_bulk(["LMT","GLD"])` | Bulk prices, max 20 tickers | Yahoo Finance |
| `get_crypto_price("BTC")` | Crypto + high/low/volume/24h change | Binance |
| `price_snapshot(["NVDA","BTC"])` | Mixed stock + crypto watchlist snapshot | Yahoo + Binance |
| `revolut_price_check("LMT")` | Price + Revolut availability verdict | Yahoo Finance |
| `crypto_top_movers(limit=10)` | Top gainers & losers 24h, Revolut-tagged | Binance |

---

## REST API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /price/{ticker}` | Single stock price |
| `GET /prices?tickers=A,B,C` | Bulk stock prices |
| `GET /crypto/{symbol}` | Crypto price (real-time) |
| `GET /revolut/check/{ticker}` | Revolut availability + price |
| `GET /revolut/stocks` | Full Revolut stocks list |
| `GET /revolut/crypto` | Full Revolut crypto list |
| `GET /snapshot` | Mixed watchlist snapshot |
| `GET /health` | Health check |
| `GET /docs` | OpenAPI (Swagger) docs |

---

## v2.1 — What's New

- ✅ **yfinance** replaces raw Yahoo HTTP — works from Railway, Fly.io, Render (no IP blocking)
- ✅ **Lazy semaphore** — no more `RuntimeError: no running event loop` on Python 3.12
- ✅ **Stampede-safe cache** — in-flight deduplication, no thundering herd
- ✅ **Config-driven lists** — edit `config/*.json`, no Python changes needed
- ✅ **Binance 429 handling** — smart backoff with `Retry-After` respect
- ✅ **Proper `List[str]` types** — clean MCP schema for all AI clients
- ✅ **Null-result guard** — no more `IndexError` on unknown tickers

---

## Programmatic SEO Engine

Generate 150+ SEO pages (one per ticker), ready to deploy to GitHub Pages or any static host:

```bash
python seo/generator.py --base-url https://your-domain.fly.dev
```

Each page includes:
- Unique `<title>` + meta description per ticker
- Schema.org `FinancialProduct` structured data
- Open Graph + Twitter Card tags
- Auto-generated `sitemap.xml` + `robots.txt`

Target keywords auto-generated per ticker:
- `NVDA stock price today`
- `Is Tesla available on Revolut?`
- `BTC price live Revolut`

---

## Config-Driven Revolut Lists

Revolut availability is stored in `config/` — not hardcoded:

```json
// config/revolut_stocks.json
{
  "stocks": {
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
    "LMT": "Lockheed Martin"
  }
}
```

To add/remove a stock: **edit the JSON only — no Python code needed.**

---

## Deploy

### Fly.io (recommended — free hobby tier)

```bash
flyctl auth login
flyctl launch --name mcprice --region ams
flyctl secrets set MCP_TRANSPORT=http
flyctl deploy
```

### Railway (1-click)

1. Fork on GitHub
2. Railway → New Project → Deploy from GitHub
3. Set env vars: `MCP_TRANSPORT=http`, `PORT=8080`

### Docker Compose (full stack — MCP + API)

```bash
# Start both MCP server and REST API
docker compose up

# Run one-off SEO page generation
BASE_URL=https://mcprice.fly.dev docker compose run --profile seo seo-gen
```

---

## Architecture

```
Claude / Cursor / Cline / AI Agent
        │
        ├── MCP Server (app.py)           port 8080
        │     ├── get_price()             → yfinance (Yahoo Finance)
        │     ├── get_crypto_price()      → Binance
        │     ├── revolut_price_check()   → yfinance + config/
        │     ├── get_prices_bulk()       → yfinance parallel
        │     ├── price_snapshot()        → yfinance + Binance
        │     └── crypto_top_movers()     → Binance /api/v3/ticker/24hr
        │
        └── REST API (api/main.py)        port 8001
              ├── GET /price/{ticker}
              ├── GET /crypto/{symbol}
              ├── GET /revolut/check/{ticker}
              └── GET /docs

Reliability layer (all requests):
  yfinance         ──→  stocks / ETFs       (30s TTL cache)
  Binance          ──→  crypto              (10s TTL cache)
     ↑
  Stampede-safe cache  (in-flight deduplication)
  Retry layer          (3 attempts, exponential backoff)
  Rate limiter         (semaphore max 5 concurrent)
  429 guard            (Binance Retry-After respected)

Config (edit JSON, no code changes):
  config/revolut_stocks.json   ← Revolut stock list
  config/revolut_crypto.json   ← Revolut crypto list
```

---

## Use with the revolut-pulse ecosystem

```
Claude / Cursor
    │
    ├── revolut-pulse-mcp  →  SEC Form 4 insider trades
    │                         is_revolut_tradable()
    │
    └── mcprice            →  live stock & crypto prices
                               revolut_price_check()
```

Ask Claude:

> *"Show me insider trades for NVDA and tell me the current price and whether I can buy it on Revolut"*

---

## File Structure

```
revolut-pulse-mcp.v2/
├── app.py                  ← MCP server v2.1 (6 tools)
├── api/
│   └── main.py             ← FastAPI HTTP layer
├── seo/
│   ├── generator.py        ← Programmatic SEO engine
│   └── output/             ← Generated static pages (gitignored)
├── config/
│   ├── revolut_stocks.json ← Revolut stock list (editable)
│   └── revolut_crypto.json ← Revolut crypto list (editable)
├── requirements.txt        ← MCP deps (fastmcp, httpx, yfinance)
├── requirements-api.txt    ← API + SEO deps
├── Dockerfile              ← MCP server image
├── Dockerfile.api          ← FastAPI image
├── docker-compose.yml      ← Full stack compose
├── fly.toml                ← Fly.io config
├── railway.json            ← Railway config
└── mcp.json                ← Claude/Cursor MCP config
```

---

## Notes & Limitations

- No API key required — yfinance and Binance public APIs are free
- Stock prices may have 15–20 min delay (Yahoo Finance free tier)
- Crypto prices are **real-time** via Binance
- Not financial advice

---

## Contributing

PRs welcome. To add stocks to the Revolut list, edit `config/revolut_stocks.json` and open a PR.

## License

MIT — free to use, modify, and deploy.
