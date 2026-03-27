# mcprice — Patch Notes

---

## v4.0 — Awesome-Finance-Skills Integration

| | v3.0 | v4.0 |
|--|------|------|
| MCP Tools | 16 | **20** |
| REST Endpoints | 15 | **19** |
| Data Sources | 4 | **8** |
| Signal types | Price + Technical + Insider | + **News + Intelligence + Sentiment** |

### New Tools

#### Tool 17 / GET `/news` — `financial_news`
**Source:** Awesome-Finance-Skills / alphaear-news / NewsNow API

Live financial headlines from 7 sources: `wallstreetcn`, `cls`, `xueqiu`, `hackernews`, `36kr`, `weibo`, `zhihu`.
- Up to 20 headlines per call with rank, title, URL, pubtime
- Built-in mood scanner: counts bullish/bearish keywords per headline batch
- Returns `headline_mood`: 🟢 Bullish / 🔴 Bearish / ⚪ Neutral
- Zero deps: pure httpx, no API key

**Use case:** Morning briefing workflow — fetch news, then feed headlines to `news_sentiment_score`, then run `revolut_price_check` on affected tickers.

---

#### Tool 18 / GET `/deepear-signals` — `deepear_signals`
**Source:** Awesome-Finance-Skills / alphaear-deepear-lite / DeepEar Lite API

Institutional-grade investment signals from `deepear.vercel.app/latest.json`.
- Each signal: title, summary, sentiment_score (-1 to +1), confidence, intensity, full reasoning chain, source links
- Automatic Revolut action hint per signal based on sentiment + confidence thresholds
- TTL cache: 2 minutes (signals update every few hours)
- `market_summary`: avg sentiment, avg confidence, overall mood

**Use case:** Replace expensive Bloomberg terminal reads. "What does the smart money think today?" in one tool call.

---

#### Tool 19 / GET `/prediction-markets` — `prediction_markets`
**Source:** Awesome-Finance-Skills / alphaear-news / Polymarket Gamma API

Live crowd-probability markets from Polymarket — where sophisticated traders put money on outcomes.
- Shows probabilities per outcome (e.g. "Bitcoin ETF approved: 84.2%")
- Optional `topic_filter`: "bitcoin", "fed", "election", "ai", "rate"
- Sorted by volume (most liquid/serious bets first)
- Conviction signal: HIGH CONVICTION (>70%) / CONTESTED / WIDE OPEN
- Embedded Revolut trading tip based on macro signals

**Use case:** Macro context for position timing. If Fed rate-cut probability > 75% on Polymarket, tech ETFs on Revolut benefit.

---

#### Tool 20 / POST `/sentiment` — `news_sentiment_score`
**Source:** Awesome-Finance-Skills / alphaear-sentiment (distilled, zero deps)

Fast FinBERT-distilled sentiment scoring for financial text.
- Score: -1.0 (very bearish) to +1.0 (very bullish)
- Labels: positive / negative / neutral with emoji
- Bull/bear keyword hits listed per text (explainable AI)
- Batch up to 30 texts per call
- Returns aggregate: avg_score, positive/negative/neutral counts, overall_mood

**Why distilled vs original BERT:**
The original alphaear-sentiment required `torch` + `transformers` + a 500MB FinBERT model download — impossible in a lean cloud container.
We extracted the domain vocabulary and scoring logic into a pure-Python keyword lexicon.
Same output format, instant response, zero MB overhead.

---

### Bug Fixes (carried from previous session)

| File | Fix |
|------|-----|
| `Dockerfile` | Added `ENV MCP_TRANSPORT=http` — server was starting in stdio mode on MCPize |
| `app.py` | Added `from starlette.requests import Request` + `Response` — HealthMiddleware crashed on first probe |
| `api/main.py` | `/crypto/movers` moved before `/crypto/{symbol}` — route shadowing bug |
| `app.py` | Tools 11–16 moved before `__main__` — architectural correctness |
| `app.py` | Removed duplicate `import os` |
| `app.py` + `api/main.py` | `asyncio.get_event_loop()` → `get_running_loop()` (deprecated on Python 3.12) |
| `app.py` | Version unified to v3.0→v4.0 (was mixed v2.2/v3.0) |
| `mcpize.yaml` | Full rewrite: `version: 1`, `runtime: container`, `startCommand.type: http` — eliminates all 10 MCPize warnings |

---

### No Breaking Changes

All v3.0 tools and endpoints (1–16) remain identical. v4.0 is purely additive.

---

## Quick Deploy

```bash
# Pull latest
git pull origin main

# Local MCP test
uv run --with fastmcp,httpx,yfinance,pandas python app.py

# Local API test
pip install -r requirements-api.txt
uvicorn api.main:app --reload --port 8001

# Test new v4.0 endpoints
curl "http://localhost:8001/news?source=wallstreetcn&count=5"
curl "http://localhost:8001/deepear-signals?limit=3"
curl "http://localhost:8001/prediction-markets?topic_filter=bitcoin"
curl -X POST http://localhost:8001/sentiment \
  -H "Content-Type: application/json" \
  -d '{"texts":["NVDA beats earnings by 20%","Fed cuts rates","Tesla misses deliveries"]}'

# MCPize auto-deploys on git push to main
git push origin main
```

---

## v4.0 Workflow Examples

### Morning Intelligence Briefing
```
1. market_overview()           → indices + crypto overnight
2. fear_greed_index()          → sentiment context
3. deepear_signals(limit=5)    → institutional view
4. financial_news("wallstreetcn", 10) → live headlines
5. news_sentiment_score([...headlines...]) → aggregate mood
6. revolut_sector_scan("tech") → actionable Revolut picks
```

### Macro Event Timing
```
1. prediction_markets(topic_filter="fed") → rate-cut probability
2. market_overview()                      → current positioning
3. technical_signals("QQQ")               → Nasdaq technical setup
4. revolut_price_check("QQQ")             → available on Revolut?
```

### News → Trade Pipeline
```
1. financial_news("cls")                  → China finance headlines
2. news_sentiment_score([headlines])       → which are actionable
3. revolut_price_check("BABA")            → is it on Revolut?
4. technical_signals("BABA")              → buy signal?
5. price_alert_check([{"ticker":"BABA","target":90,"direction":"above"}])
```

---

## Monetization Map (v4.0)

```
Morning Briefing workflow (tools 8+11+18+17+20)
  → User gets comprehensive intelligence in one Claude session
  → Stays engaged → more sessions → more affiliate exposure

DeepEar signal: "BTC bullish, confidence 0.85"
  → revolut_price_check("BTC") → available on Revolut 💳
  → User opens Revolut → you earn referral

Polymarket: "Bitcoin ETF approval 84%"
  → User buys BTC on Revolut
  → Revolut affiliate commission

news_sentiment_score on earnings headlines
  → Bearish TSLA headline detected
  → price_alert_check monitors TSLA drop
  → User sets stop-loss via Revolut
```

