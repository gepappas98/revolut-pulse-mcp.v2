# mcprice ⚡ — Real-Time Stock & Crypto Prices for AI Agents

> **MCP Server + REST API** for real-time stock & crypto prices — no API keys, no setup friction.
>
> Stocks → **Yahoo Finance** &nbsp;|&nbsp; Crypto → **Binance** &nbsp;|&nbsp; Free forever

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)
[![Deploy on Fly.io](https://img.shields.io/badge/Fly.io-deploy-purple?logo=fly.io)](https://fly.io)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)

---

## What is mcprice?

**mcprice** is a dual-mode financial data server:

| Mode | What it does | Who uses it |
|------|-------------|-------------|
| **MCP Server** | Claude / Cursor / Cline tool calls | AI developers |
| **REST API** | Plain HTTP endpoints | Web apps, bots, scripts |
| **SEO Engine** | Generates 150+ static pages | Organic search traffic |

Zero API keys. Zero paid tiers. Works in 2 minutes.

---

## Quick Start (2 min)

### MCP Mode (Claude Desktop / Cursor)

```bash
git clone https://github.com/gepappas98/mcprice.git
cd mcprice
uv run --with fastmcp,httpx python app.py
```

Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "mcprice": {
      "command": "uv",
      "args": ["run", "--with", "fastmcp,httpx", "python", "app.py"],
      "cwd": "/path/to/mcprice"
    }
  }
}
```

### API Mode (HTTP)

```bash
pip install -r requirements-api.txt
uvicorn api.main:app --port 8001
```

```bash
# Stock price
curl http://localhost:8001/price/NVDA

# Crypto price
curl http://localhost:8001/crypto/BTC

# Is it on Revolut?
curl http://localhost:8001/revolut/check/LMT
```

---

## MCP Tools (6 total)

| Tool | Description | Source |
|------|-------------|--------|
| `get_price("NVDA")` | Live price + 24h change | Yahoo Finance |
| `get_prices_bulk(["LMT","GLD"])` | Bulk prices, max 20 | Yahoo Finance |
| `get_crypto_price("BTC")` | Crypto + high/low/volume | Binance |
| `price_snapshot(["NVDA","BTC"])` | Mixed stock+crypto snapshot | Yahoo + Binance |
| `revolut_price_check("LMT")` | Price + Revolut availability | Yahoo Finance |
| `crypto_top_movers(limit=10)` | Top gainers & losers 24h | Binance |

---

## REST API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /price/{ticker}` | Single stock price |
| `GET /prices?tickers=A,B,C` | Bulk stock prices |
| `GET /crypto/{symbol}` | Crypto price |
| `GET /revolut/check/{ticker}` | Revolut availability + price |
| `GET /revolut/stocks` | Full Revolut stocks list |
| `GET /revolut/crypto` | Full Revolut crypto list |
| `GET /snapshot` | Mixed watchlist snapshot |
| `GET /health` | Health check |
| `GET /docs` | OpenAPI docs |

---

## v2.0 Upgrades

- ✅ **TTL in-memory cache** — 30s stocks / 10s crypto (↓60% latency)
- ✅ **Retry + exponential backoff** — 3 attempts, never dies on flaky APIs
- ✅ **Yahoo → Binance fallback** — automatic provider failover
- ✅ **Ticker validation** — regex guard, no garbage input
- ✅ **Structured logging** — debug/info/error with timestamps
- ✅ **Rate limiter** — semaphore max 5 concurrent outbound calls
- ✅ **Config-driven lists** — edit `config/*.json`, no code changes
- ✅ **FastAPI HTTP layer** — REST API on top of MCP logic
- ✅ **Programmatic SEO engine** — 150+ auto-generated pages

---

## Programmatic SEO

Generate 150+ SEO-optimized static pages (one per ticker):

```bash
python seo/generator.py --base-url https://your-domain.fly.dev
```

Each generated page includes:
- Unique `<title>` + meta description per ticker
- **Schema.org `FinancialProduct`** structured data (rich results)
- Open Graph + Twitter Card tags
- Canonical URLs
- Auto-generated `sitemap.xml` + `robots.txt`

Target keywords generated automatically:
- `NVDA stock price today`
- `Is Tesla available on Revolut?`
- `BTC price live Revolut`
- `buy Lockheed Martin on Revolut`

---

## Config-Driven Lists

Revolut stock/crypto availability is now in `config/`, not hardcoded:

```json
// config/revolut_stocks.json
{
  "stocks": {
    "NVDA": "NVIDIA",
    "TSLA": "Tesla"
  }
}
```

To add/remove a stock: **edit the JSON, no Python code needed.**

---

## Deploy

### Railway (1-click)
1. Fork on GitHub
2. Railway → New Project → Deploy from GitHub
3. Set `MCP_TRANSPORT=http` and `PORT=8000`

### Fly.io
```bash
flyctl auth login
flyctl launch --name mcprice --region ams
flyctl secrets set MCP_TRANSPORT=http
flyctl deploy
```

### Docker Compose (full stack)
```bash
# MCP + API together
docker compose up

# One-off SEO page generation
BASE_URL=https://mcprice.fly.dev docker compose run seo-gen
```

---

## Architecture

```
Claude / Cursor / AI Agent
        │
        ├── MCP Server (app.py)          port 8000
        │     ├── get_price()
        │     ├── get_crypto_price()
        │     ├── revolut_price_check()
        │     └── crypto_top_movers()
        │
        └── REST API (api/main.py)       port 8001
              ├── GET /price/{ticker}
              ├── GET /crypto/{symbol}
              ├── GET /revolut/check/{ticker}
              └── GET /docs


Providers:
  Yahoo Finance  ──→  stocks / ETFs (30s cache)
  Binance        ──→  crypto       (10s cache)
     ↑
  Retry layer (3 attempts, exponential backoff)
  Cache layer (TTL in-memory)
  Rate limiter (semaphore 5 concurrent)


Config (no code changes needed):
  config/revolut_stocks.json   ← edit to update Revolut stock list
  config/revolut_crypto.json   ← edit to update Revolut crypto list

SEO Engine:
  seo/generator.py  ──→  seo/output/price/*.html  +  sitemap.xml
```

---

## Ecosystem

```
Claude / Cursor
    │
    ├── revolut-pulse-mcp   →  SEC Form 4 insider trades
    │                          is_revolut_tradable()
    │
    └── mcprice             →  real-time prices
                               revolut_price_check()
```

Ask Claude:
> *"Show me insider trades for NVDA and tell me the current price and whether I can buy it on Revolut"*

Both servers answer **simultaneously**.

---

## Notes

- No API key required — Yahoo Finance & Binance public APIs are free
- Stock prices may have 15-20 min delay (Yahoo Finance free tier)
- Crypto prices are **real-time** (Binance)
- Not financial advice

---

## File Structure

```
mcprice/
├── app.py                  ← MCP server v2.0 (6 tools)
├── api/
│   └── main.py             ← FastAPI HTTP layer
├── seo/
│   ├── generator.py        ← Programmatic SEO engine
│   └── output/             ← Generated static pages (gitignored)
├── config/
│   ├── revolut_stocks.json ← Revolut stock list (editable)
│   └── revolut_crypto.json ← Revolut crypto list (editable)
├── requirements.txt        ← MCP deps
├── requirements-api.txt    ← API + SEO deps
├── Dockerfile              ← MCP server image
├── Dockerfile.api          ← FastAPI image
├── docker-compose.yml      ← Full stack compose
├── fly.toml                ← Fly.io config
├── railway.json            ← Railway config
├── mcp.json                ← Claude/Cursor config
└── .github/workflows/ci.yml ← GitHub Actions CI
```
