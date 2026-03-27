# mcprice v5.0 🚀

**Real-Time Financial Intelligence MCP for Claude / Cursor / VS Code**

25 MCP tools + 25 REST endpoints. No API keys. Deploy in one push.

---

## What's New in v5.0 — Skills → MCP Conversion

Five Claude Skills (SKILL.md format) converted to production MCP tools + REST endpoints:

| MCP Tool | REST Endpoint | Source Skill |
|----------|--------------|--------------|
| `stock_correlation` | `GET /correlation` | stock-correlation SKILL.md |
| `options_analysis` | `POST /options/analysis` | options-payoff SKILL.md |
| `geopolitical_energy_risk` | `GET /geopolitical/energy` | hormuz-strait SKILL.md |
| `stock_deep_data` | `GET /fundamentals/{ticker}` | yfinance-data SKILL.md |
| `options_chain` | `GET /options/chain/{ticker}` | yfinance-data SKILL.md |

---

## All 25 Tools

### Price Tools (1–10)
| # | MCP Tool | REST | Description |
|---|----------|------|-------------|
| 1 | `get_price` | `GET /price/{ticker}` | Single stock/ETF price |
| 2 | `get_prices_bulk` | `GET /prices?tickers=` | Up to 20 tickers at once |
| 3 | `get_crypto_price` | `GET /crypto/{symbol}` | Binance crypto price |
| 4 | `price_snapshot` | `GET /snapshot` | Mixed stock+crypto watchlist |
| 5 | `revolut_price_check` | `GET /revolut/check/{ticker}` | Price + Revolut availability |
| 6 | `crypto_top_movers` | `GET /crypto/movers` | Binance 24h gainers/losers |
| 7 | `portfolio_pnl` | — | Real-time P&L for holdings |
| 8 | `market_overview` | — | Indices + commodities + crypto |
| 9 | `revolut_watchlist` | — | Bulk Revolut check |
| 10 | `revolut_sector_scan` | — | Sector scan + best Revolut pick |

### Signal Tools (11–16)
| # | MCP Tool | REST | Description |
|---|----------|------|-------------|
| 11 | `fear_greed_index` | `GET /fear-greed` | Fear & Greed + trading bias |
| 12 | `earnings_calendar` | `GET /earnings?tickers=` | Next earnings + EPS estimates |
| 13 | `technical_signals` | `GET /signals/{ticker}` | RSI/SMA/EMA/MACD engine |
| 14 | `insider_flow_scan` | `GET /insider-flow` | SEC Form 4 cluster buys |
| 15 | `crypto_funding_rates` | `GET /funding-rates` | Binance perp funding rates |
| 16 | `price_alert_check` | `POST /alert-check` | Multi-ticker alert monitor |

### Intelligence Tools (17–20)
| # | MCP Tool | REST | Description |
|---|----------|------|-------------|
| 17 | `financial_news` | `GET /news` | Live headlines (NewsNow) |
| 18 | `deepear_signals` | `GET /deepear-signals` | Institutional investment signals |
| 19 | `prediction_markets` | `GET /prediction-markets` | Polymarket crowd probabilities |
| 20 | `news_sentiment_score` | `POST /sentiment` | FinBERT-distilled sentiment |

### Analytics Tools — v5.0 NEW (21–25)
| # | MCP Tool | REST | Description |
|---|----------|------|-------------|
| 21 | `stock_correlation` | `GET /correlation` | Co-move discovery, pairs, clustering, rolling |
| 22 | `options_analysis` | `POST /options/analysis` | BS payoff curves + Greeks (7 strategies) |
| 23 | `geopolitical_energy_risk` | `GET /geopolitical/energy` | Hormuz + oil trade signals |
| 24 | `stock_deep_data` | `GET /fundamentals/{ticker}` | Income/balance/cashflow/analysts/insiders |
| 25 | `options_chain` | `GET /options/chain/{ticker}` | Live IV surface + OI + max pain |

---

## Quick Start

### Claude Desktop / Cursor
```json
{
  "mcServers": {
    "mcprice": {
      "url": "https://mcprice.fly.dev/mcp"
    }
  }
}
```

### REST API
```bash
# Stock correlation — find what moves with NVDA
curl "https://mcprice.fly.dev/correlation?tickers=NVDA&mode=discover"

# Pair analysis — AMD vs NVDA
curl "https://mcprice.fly.dev/correlation?tickers=AMD,NVDA&mode=pair"

# Deep fundamentals — NVDA overview
curl "https://mcprice.fly.dev/fundamentals/NVDA?data_type=all"

# Options chain — AAPL
curl "https://mcprice.fly.dev/options/chain/AAPL"

# Geopolitical energy risk
curl "https://mcprice.fly.dev/geopolitical/energy"

# Options analysis (POST)
curl -X POST https://mcprice.fly.dev/options/analysis \
  -H "Content-Type: application/json" \
  -d '{"strategy":"vertical_spread","underlying":"NVDA","spot":880,"strikes":[860,920],"premium":18.5,"dte":21,"iv":0.42}'
```

---

## Data Sources

| Source | Tools |
|--------|-------|
| yfinance | Stocks, ETFs, options, fundamentals |
| Binance Public API | Crypto prices, funding rates, top movers |
| alternative.me | Fear & Greed index |
| SEC EDGAR (via GitHub Actions) | Insider flow scan |
| Hormuz Strait Monitor | Geopolitical energy risk |
| DeepEar Lite | Institutional investment signals |
| Polymarket Gamma API | Prediction markets |
| NewsNow / WallStreetCN | Financial headlines |

---

## Deploy

```bash
git add app.py api/main.py mcpize.yaml README.md PATCH_NOTES_V5.md
git commit -m "feat: v5.0 — 25 tools, Skills-to-MCP conversion"
git push origin main
# MCPize auto-deploys on push
```

Built by **GRG** | mcprice.fly.dev | No API keys required
