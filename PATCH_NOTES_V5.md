# mcprice v5.0 — Skills-to-MCP Conversion Patch Notes

## Overview: What Changed

| | v4.0 | v5.0 |
|--|------|------|
| MCP Tools | 20 | **25** |
| Data Sources | 8 | **11** |
| Analytics Depth | Price + Technical + News | + **Correlation + Options + Fundamentals + Geopolitical** |
| Skill Conversions | 0 | **5 skills → 5 MCP tools** |

---

## Architecture: Skills → MCP Tools

### What is a "Skill"?

A Claude Skill (SKILL.md format) is a **markdown playbook** that instructs Claude to:
1. Run Python code via `bash_tool`
2. Parse the output
3. Present results to the user

**Problem**: Skills only work inside Claude conversations with computer access.

### What is an MCP Tool?

An MCP tool is a **callable function** exposed over a standard protocol that:
1. Any AI agent can invoke (Claude, GPT, Gemini, custom agents)
2. Returns structured JSON — composable with other tools
3. Works from Claude Desktop, Cursor, VS Code, Claude Code
4. Runs on `mcprice.fly.dev` as a permanent cloud service

### Conversion Matrix

| Skill | → | MCP Tool | Key Transformation |
|-------|---|----------|--------------------|
| `stock-correlation/SKILL.md` | → | `stock_correlation` | Python inline → async executor, 4 sub-modes |
| `options-payoff/SKILL.md` | → | `options_analysis` | HTML widget removed → pure BS JSON engine |
| `hormuz-strait/SKILL.md` | → | `geopolitical_energy_risk` | curl bash → async httpx, Revolut signals added |
| `yfinance-data/SKILL.md` (deep data section) | → | `stock_deep_data` | Multi-endpoint router, 10 data_types |
| `yfinance-data/SKILL.md` (options section) | → | `options_chain` | Options chain + IV surface + max pain |

---

## Tool 21 — `stock_correlation`

**Source**: `finance-skills/skills/stock-correlation/SKILL.md`

### What was converted

The skill had 4 sub-skills (A/B/C/D). All 4 are now addressable via the `mode` parameter:

| Mode | Sub-skill | What it does |
|------|-----------|--------------|
| `discover` | A — Co-movement Discovery | Given 1 ticker, find top correlated peers + Revolut picks |
| `pair` | B — Return Correlation | Deep pairwise: Pearson, beta, R², rolling 60d, spread Z-score |
| `cluster` | C — Sector Clustering | Full correlation matrix for 3–15 tickers, identify diversifiers |
| `rolling` | D — Realized Correlation | Rolling windows (20d/60d/120d) + regime-conditional analysis |

### Key design decisions

1. **No `scipy` dependency** — skill used hierarchical clustering from scipy. Removed for lean container. Replaced with simple avg-correlation sort.
2. **Peer universe**: hardcoded sector maps replace the skill's `yf.Screener` API (which requires auth and has rate limits in cloud environments).
3. **All sync yfinance calls** wrapped in `run_in_executor` — preserves async MCP server integrity.
4. **Revolut flags** added to every output — a correlation result without Revolut context is useless for GRG's use case.

### Example usage

```python
# Discover what moves with NVDA
stock_correlation(tickers=["NVDA"], mode="discover", period="1y")

# Deep pair analysis for AMD/NVDA sympathy play
stock_correlation(tickers=["AMD", "NVDA"], mode="pair")

# Portfolio correlation matrix
stock_correlation(tickers=["NVDA","LMT","GLD","BTC","SPY"], mode="cluster")

# Crisis regime analysis — does correlation spike during drawdowns?
stock_correlation(tickers=["AMD", "NVDA"], mode="rolling", period="2y")
```

---

## Tool 22 — `options_analysis`

**Source**: `finance-skills/skills/options-payoff/SKILL.md`

### What was converted

The skill generates an interactive HTML widget (Chart.js + sliders). This is **useless in MCP context** — MCP tools must return JSON. 

Complete rewrite of the computational core:
- Pure Python Black-Scholes implementation (no dependencies)
- `norm_cdf` via Abramowitz & Stegun approximation
- `bs_call` / `bs_put` / `bs_delta` / `theta_approx`
- Payoff curve: 21-point scan from 80%→120% of strike range
- Breakeven detection via linear interpolation

### Strategies supported

| Strategy | Legs | Formula source |
|----------|------|----------------|
| `butterfly` | Buy K1, Sell 2×K2, Buy K3 | Put butterfly payoff |
| `vertical_spread` | Buy K1 call, Sell K2 call | Debit spread payoff |
| `iron_condor` | 4 legs | Short put spread + short call spread |
| `straddle` | Long ATM call + put | Max(S-K,0) + Max(K-S,0) |
| `strangle` | OTM call + OTM put | Both legs OTM |
| `covered_call` | Long stock + short call | Stock delta - call |
| `naked_put` | Short put | -Max(K-S,0) |

### Revolut integration

Options don't exist on Revolut — so the tool adds a **directional translation**:
- High IV → expect a big move in the underlying → time stock entry on Revolut
- Breakevens → price levels to set alerts via `price_alert_check`
- Delta → direction bias for Revolut stock position sizing

### Example usage

```python
# Bull call spread on NVDA
options_analysis(
    strategy="vertical_spread",
    underlying="NVDA",
    spot=880.0,
    strikes=[860.0, 920.0],
    premium=18.50,
    dte=21,
    iv=0.42
)

# Iron condor on SPY
options_analysis(
    strategy="iron_condor",
    underlying="SPY",
    spot=580.0,
    strikes=[545.0, 560.0, 600.0, 615.0],
    premium=-4.20,   # credit received
    dte=30
)
```

---

## Tool 23 — `geopolitical_energy_risk`

**Source**: `finance-skills/skills/hormuz-strait/SKILL.md`

### What was converted

The skill used `curl` bash + text presentation. Converted to:
- `async httpx` call to `hormuzstraitmonitor.com/api/dashboard`
- Complete schema parsing (10 API sections)
- Risk classification logic (normal/elevated/high/critical)
- Revolut energy trade signal generator

### Added value beyond the skill

The original skill just displayed data. The MCP tool adds:

```python
"revolut_energy_signals": {
    "trade_bias": "🔴 BULLISH oil — consider XOM, CVX, OXY, XLE on Revolut",
    "hedge_tip": "Consider GLD as safe-haven via Revolut",
    "revolut_energy_tickers": ["XOM", "CVX", "COP", "OXY", "XLE"],
    "suggested_tools": [
        "revolut_sector_scan('energy')",
        "technical_signals('XLE')",
        "price_alert_check([...])"
    ]
}
```

This converts geopolitical intelligence into **actionable Revolut trades** — exactly the GRG workflow.

---

## Tool 24 — `stock_deep_data`

**Source**: `finance-skills/skills/yfinance-data/SKILL.md` + `references/api_reference.md`

### What was converted

The skill covers yfinance's full API surface. mcprice v4 only had `fast_info` (price data). This tool adds:

| `data_type` | yfinance method | New capability |
|-------------|-----------------|----------------|
| `overview` | `ticker.info` | P/E, PEG, beta, margins, 52w range |
| `income` | `ticker.income_stmt` | Revenue, EPS, EBITDA, net income |
| `balance` | `ticker.balance_sheet` | Assets, liabilities, equity, cash |
| `cashflow` | `ticker.cashflow` | Operating/investing/FCF calculation |
| `analysts` | `ticker.analyst_price_targets` | Mean/high/low targets, buy/hold/sell count |
| `holders` | `ticker.institutional_holders` | Top institutional + mutual fund holders |
| `insiders` | `ticker.insider_transactions` | SEC Form 4 at ticker level (vs Tool 14's bulk scan) |
| `dividends` | `ticker.dividends` | 8-quarter history + yield + payout ratio |
| `news` | `ticker.news` | 8 latest news items |
| `all` | multiple | Overview + analysts + financial health score |

### Health score (unique addition)

```python
"health_score": {
    "valuation": "fair",           # PE-based
    "growth_adj": "undervalued",   # PEG-based
    "profitability": "high margin", # profit margin-based
    "revolut_verdict": "💳 NVDA IS on Revolut — fundamental analysis supports 📈 accumulation"
}
```

---

## Tool 25 — `options_chain`

**Source**: `finance-skills/skills/yfinance-data/SKILL.md` (options chain section)

### What was converted

Dedicated options chain tool. New features vs raw yfinance:

- **Near-money filter**: Only shows strikes within ±10% of spot (configurable)
- **Max pain calculation**: Strike with highest total OI (both calls + puts)
- **Put/call OI ratio**: Sentiment indicator
- **IV signal**: Automatic interpretation (cheap/elevated/expensive)
- **Bid-ask spread**: Liquidity measure per strike
- **Moneyness %**: How far each strike is from spot
- **Revolut translation**: IV level → directional timing hint for stock position

### Example usage

```python
# Live NVDA options — nearest expiry, near-money calls + puts
options_chain(ticker="NVDA", expiry_index=0, near_money_only=True)

# SPY puts only — 2nd expiry (weekly hedging analysis)
options_chain(ticker="SPY", expiry_index=1, option_type="puts")
```

---

## Dependency Changes

No new Python dependencies added. All 5 new tools use:
- `yfinance` (already in requirements.txt)
- `httpx` (already in requirements.txt)
- `asyncio` + `math` (stdlib)
- `pandas`, `numpy` (already pulled by yfinance)

`scipy` was intentionally excluded (adds ~30MB to container, not worth it for clustering alone).

---

## Deploy

```bash
# Same as v4 — no config changes needed
git add app.py PATCH_NOTES_V5.md
git commit -m "feat: v5.0 — Skills-to-MCP conversion (+5 tools: correlation, options, geopolitical, fundamentals, options chain)"
git push origin main
# MCPize auto-deploys on push
```

---

## v5.0 Workflow Examples

### Sympathy Play Discovery (Tools 21 + 13 + 5)
```
1. stock_correlation(["NVDA"], mode="discover")    → find AMD, AVGO, TSM correlated
2. technical_signals("AMD")                        → is AMD also oversold?
3. revolut_price_check("AMD")                      → confirm on Revolut
4. price_alert_check([{"ticker":"AMD","target":190,"direction":"above"}])
```

### Pre-Earnings Options Analysis (Tools 12 + 25 + 22 + 5)
```
1. earnings_calendar(["NVDA","AAPL","META"])        → who reports next?
2. options_chain("NVDA", expiry_index=0)            → what's the IV?
3. options_analysis("straddle","NVDA",spot,strikes=[880],premium=45,dte=7,iv=0.55)
4. revolut_price_check("NVDA")                      → trade the underlying
```

### Energy Geopolitical Trade (Tools 23 + 10 + 13)
```
1. geopolitical_energy_risk()                       → Hormuz status + oil bias
2. revolut_sector_scan("energy")                    → best Revolut energy pick today
3. technical_signals("XLE")                         → entry timing signal
4. stock_correlation(["XLE","OXY"], mode="pair")    → which one leads the other?
```

### Deep Fundamental Research (Tools 24 + 21 + 16)
```
1. stock_deep_data("LMT", data_type="all")          → full fundamental picture
2. stock_deep_data("LMT", data_type="insiders")     → insider conviction?
3. stock_correlation(["LMT","RTX","NOC"], mode="cluster") → sector positioning
4. price_alert_check([{"ticker":"LMT","target":520,"direction":"above"}])
```
