# mcprice ⚡ v4.0 — Free Stock & Crypto MCP Server (No API Key)

> **20 tools. Real-time prices · Technical signals · Fear & Greed · SEC insider flow ·
> Earnings calendar · Funding rates · Live financial news · DeepEar investment signals ·
> Polymarket prediction markets · FinBERT sentiment — for Claude, Cursor, Cline.**
> yfinance · Binance · alternative.me · SEC EDGAR · NewsNow · DeepEar · Polymarket · Zero API keys · Free forever.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)
[![Deploy on Fly.io](https://img.shields.io/badge/Fly.io-deploy-purple?logo=fly.io)](https://fly.io)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MCP Server](https://img.shields.io/badge/MCP-server-orange)](https://mcpize.com/mcp/mcprice)
[![20 Tools](https://img.shields.io/badge/tools-20-brightgreen)](#tools)

---

## What is mcprice?

**mcprice** is a free, open-source MCP server that gives Claude, Cursor, and any AI agent
**live prices, technical signals, market intelligence, news, sentiment, and prediction markets** —
with no API key, no paid tier, and zero setup friction.

Ask Claude things like:

> *"Is NVDA on Revolut and what's the RSI signal?"*
> *"Show me today's top financial news from Wall Street CN + sentiment score"*
> *"What does DeepEar say about today's market?"*
> *"What are the top Polymarket bets on Bitcoin ETF approval?"*
> *"Are there any cluster insider buys on Revolut stocks today?"*
> *"Give me a full morning briefing: market overview + Fear & Greed + DeepEar signals + top news"*

---

## Why mcprice v4?

| Feature | mcprice v4 | Alpha Vantage MCP | Financial Datasets MCP |
|---------|-----------|------------------|----------------------|
| **API Key** | ❌ None | ✅ Required | ✅ Paid |
| **Stock prices** | ✅ yfinance | ✅ | ✅ |
| **Crypto (real-time)** | ✅ Binance | ❌ | ❌ |
| **Technical signals** | ✅ RSI/MACD/SMA/EMA | ❌ | ❌ |
| **Fear & Greed** | ✅ | ❌ | ❌ |
| **SEC Insider Flow** | ✅ | ❌ | ❌ |
| **Earnings calendar** | ✅ | ❌ | ❌ |
| **Funding rates** | ✅ Binance perp | ❌ | ❌ |
| **Price alerts** | ✅ | ❌ | ❌ |
| **Live financial news** | ✅ **NEW** NewsNow | ❌ | ❌ |
| **Investment signals** | ✅ **NEW** DeepEar | ❌ | ❌ |
| **Prediction markets** | ✅ **NEW** Polymarket | ❌ | ❌ |
| **Text sentiment** | ✅ **NEW** FinBERT-distilled | ❌ | ❌ |
| **Revolut filter** | ✅ | ❌ | ❌ |
| **Cost** | 🆓 Free | Freemium | Paid |

---

## Quick Start (2 minutes)

### Option A — MCP Mode (Claude Desktop / Cursor / Cline)

```bash
git clone https://github.com/gepappas98/revolut-pulse-mcp.v2.git
cd revolut-pulse-mcp.v2
uv run --with fastmcp,httpx,yfinance,pandas python app.py
```

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcprice": {
      "command": "uv",
      "args": ["run", "--with", "fastmcp,httpx,yfinance,pandas", "python", "app.py"],
      "cwd": "/path/to/revolut-pulse-mcp.v2"
    }
  }
}
```

### Option B — Remote (already deployed on MCPize)

```json
{
  "mcpServers": {
    "mcprice": {
      "url": "https://mcprice.mcpize.run/mcp"
    }
  }
}
```

### Option C — REST API

```bash
pip install -r requirements-api.txt
uvicorn api.main:app --port 8001

# Examples
curl http://localhost:8001/price/NVDA
curl http://localhost:8001/crypto/BTC
curl http://localhost:8001/news?source=wallstreetcn
curl http://localhost:8001/deepear-signals?limit=5
curl http://localhost:8001/prediction-markets?topic_filter=bitcoin
curl -X POST http://localhost:8001/sentiment \
  -H "Content-Type: application/json" \
  -d '{"texts":["NVDA beats earnings by 20%","Tesla misses deliveries"]}'
```

---

## Tools (20 total)

### 📈 Prices & Revolut

| # | Tool | Description | Source |
|---|------|-------------|--------|
| 1 | `get_price` | Live price + 24h change for one stock/ETF | yfinance |
| 2 | `get_prices_bulk` | Up to 20 tickers at once | yfinance |
| 3 | `get_crypto_price` | Real-time crypto price | Binance |
| 4 | `price_snapshot` | Mixed watchlist snapshot + market mood | yfinance + Binance |
| 5 | `revolut_price_check` | Price + instant Revolut availability check 💳 | yfinance |
| 6 | `crypto_top_movers` | Top 24h gainers & losers with Revolut filter | Binance |
| 7 | `portfolio_pnl` | Real-time P&L for your holdings | yfinance + Binance |
| 8 | `market_overview` | Indices + commodities + crypto dashboard | yfinance + Binance |
| 9 | `revolut_watchlist` | Bulk Revolut check for mixed watchlist | yfinance + Binance |
| 10 | `revolut_sector_scan` | Sector scan + best Revolut pick of the day | yfinance + Binance |

### 📊 Signals & Analysis

| # | Tool | Description | Source |
|---|------|-------------|--------|
| 11 | `fear_greed_index` | Fear & Greed score + trading bias | alternative.me |
| 12 | `earnings_calendar` | Next earnings date + EPS estimates | yfinance |
| 13 | `technical_signals` | RSI/SMA/EMA/MACD buy-sell signal engine | yfinance |
| 14 | `insider_flow_scan` | SEC Form 4 cluster buy detection | GitHub Actions |
| 15 | `crypto_funding_rates` | Binance perp funding rates (contrarian) | Binance Futures |
| 16 | `price_alert_check` | Multi-ticker price target monitor | yfinance + Binance |

### 🧠 News & Intelligence *(v4.0 — from Awesome-Finance-Skills)*

| # | Tool | Description | Source |
|---|------|-------------|--------|
| 17 | `financial_news` | Live headlines + mood from 7 sources | NewsNow API |
| 18 | `deepear_signals` | Professional investment signals + reasoning | DeepEar Lite |
| 19 | `prediction_markets` | Crowd-probability bets on real-world events | Polymarket |
| 20 | `news_sentiment_score` | FinBERT-distilled sentiment scoring (-1 to +1) | Built-in lexicon |

---

## REST API Endpoints (19 total)

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /price/{ticker}` | Single stock price |
| `GET /prices?tickers=A,B` | Bulk stock prices |
| `GET /crypto/movers` | Top Binance gainers/losers |
| `GET /crypto/{symbol}` | Single crypto price |
| `GET /revolut/stocks` | Full Revolut stock list |
| `GET /revolut/crypto` | Full Revolut crypto list |
| `GET /revolut/check/{ticker}` | Revolut check + price |
| `GET /snapshot` | Mixed watchlist snapshot |
| `GET /fear-greed` | Fear & Greed index |
| `GET /earnings?tickers=...` | Earnings calendar |
| `GET /signals/{ticker}` | Technical signals |
| `GET /insider-flow` | SEC Form 4 insider data |
| `GET /funding-rates` | Binance funding rates |
| `POST /alert-check` | Price alert monitor |
| `GET /news` | **NEW** Live financial news |
| `GET /deepear-signals` | **NEW** DeepEar signals |
| `GET /prediction-markets` | **NEW** Polymarket markets |
| `POST /sentiment` | **NEW** Sentiment scoring |

---

## Data Sources

| Source | Used for | Latency |
|--------|----------|---------|
| yfinance | Stock/ETF prices, technicals, earnings | 30s cache |
| Binance | Crypto prices, funding rates, top movers | 10s cache |
| alternative.me | Fear & Greed Index | 5min cache |
| SEC EDGAR (via GitHub Actions) | Insider flow Form 4 | 2h updates |
| NewsNow API | Financial headlines from 7 sources | Live |
| DeepEar Lite | Professional investment signals | 2min cache |
| Polymarket | Prediction market probabilities | Live |
| Built-in lexicon | FinBERT-distilled sentiment | Instant |

---

## Architecture

```
Claude / Cursor / AI Agent
        │
        ├── MCP Server (app.py)                port 8080
        │     ├── Tools 1–10  : Prices & Revolut
        │     ├── Tools 11–16 : Signals & Analysis
        │     └── Tools 17–20 : News & Intelligence (v4.0)
        │
        └── REST API (api/main.py)             port 8001
              ├── GET  /price/{ticker}
              ├── GET  /crypto/movers  ← before /crypto/{symbol}!
              ├── GET  /news
              ├── GET  /deepear-signals
              ├── GET  /prediction-markets
              └── POST /sentiment

Data Providers:
  yfinance      ──→ stocks / ETFs (30s TTL cache)
  Binance       ──→ crypto / funding rates (10s cache)
  NewsNow       ──→ 7 news sources
  DeepEar       ──→ investment signals (2min cache)
  Polymarket    ──→ prediction markets
  Built-in      ──→ sentiment lexicon (instant)
       ↑
  Retry layer (3 attempts, exponential backoff)
  Stampede-safe TTL cache
  Rate limiter (semaphore 5 concurrent)
```

---

## Config-Driven Lists

Edit `config/revolut_stocks.json` or `config/revolut_crypto.json` to update
Revolut availability — no code changes needed.

---

## Deploy

### MCPize (recommended — auto-deploy from GitHub)
Push to `main` → MCPize redeploys automatically.

### Railway
1. Fork on GitHub
2. Railway → New Project → Deploy from GitHub
3. Env vars are set via Dockerfile (`MCP_TRANSPORT=http`, `PORT=8080`)

### Fly.io
```bash
flyctl launch --name mcprice --region ams
flyctl deploy
```

### Docker Compose (full stack: MCP + API)
```bash
docker compose up
```

---

## Notes

- No API keys required for any of the 20 tools
- Stock prices may have 15-20 min delay (Yahoo Finance free tier)
- Crypto prices are real-time (Binance)
- Not financial advice

---

## Changelog

- **v4.0** — +4 tools from Awesome-Finance-Skills: financial_news, deepear_signals, prediction_markets, news_sentiment_score
- **v3.0** — +6 tools: fear_greed_index, earnings_calendar, technical_signals, insider_flow_scan, crypto_funding_rates, price_alert_check
- **v2.2** — TTL cache, retry layer, rate limiter, config-driven lists, FastAPI layer
- **v2.0** — Initial release: 10 tools, yfinance + Binance

