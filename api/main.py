#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║              mcprice — FastAPI HTTP Layer  v5.0                  ║
║                                                                  ║
║  Exposes all 25 MCP tools over plain HTTP.                       ║
║  Stocks via yfinance · Crypto via Binance                        ║
║  No API key required for any endpoint.                           ║
║                                                                  ║
║  v5.0 new endpoints from Skills conversion (+5):                 ║
║    GET  /correlation        — 4-mode correlation engine          ║
║    POST /options/analysis   — Black-Scholes payoff + Greeks      ║
║    GET  /geopolitical/energy— Hormuz Monitor + oil signals       ║
║    GET  /fundamentals/{t}   — Income/balance/analysts/insiders   ║
║    GET  /options/chain/{t}  — Live IV surface + OI + max pain    ║
║                                                                  ║
║  Run:                                                            ║
║    uvicorn api.main:app --reload --port 8001                     ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import List, Optional

import httpx
import yfinance as yf

# === FIX TzCache Error για Cloud Run / Railway / Serverless ===
# Το yfinance δεν μπορεί να γράψει στο /root/.cache → χρησιμοποιούμε /tmp
import os
os.makedirs("/tmp/py-yfinance", exist_ok=True)
yf.set_tz_cache_location("/tmp/py-yfinance")
print("✅ yfinance TzCache fixed to /tmp/py-yfinance")
# ========================================================

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ─── load config ─────────────────────────────────────────────────────────────
_CONFIG_DIR = Path(__file__).parent.parent / "config"

with open(_CONFIG_DIR / "revolut_stocks.json") as f:
    REVOLUT_STOCKS: dict = json.load(f)["stocks"]

with open(_CONFIG_DIR / "revolut_crypto.json") as f:
    REVOLUT_CRYPTO: set = set(json.load(f)["crypto"])

_UNIVERSAL_CRYPTO = {
    "BTC","ETH","BNB","SOL","XRP","DOGE","ADA","AVAX","DOT","MATIC",
    "LINK","UNI","ATOM","LTC","BCH","XLM","ALGO","FIL","AAVE","COMP",
    "MKR","SNX","YFI","SUSHI","BAT","ENJ","MANA","SAND","AXS","CHZ",
    "GALA","IMX","APE","NEAR","FTM","HBAR","ICP","ETC","TRX","EOS",
    "OP","ARB","SUI","SEI","TIA","PYTH","JUP","WLD","INJ","PEPE",
    "FLOKI","BONK","SHIB","TON",
}
ALL_CRYPTO = REVOLUT_CRYPTO | _UNIVERSAL_CRYPTO

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; mcprice/3.0; +https://github.com/gepappas98/mcprice)"}

# ─── TTL cache ────────────────────────────────────────────────────────────────
_cache: dict = {}

def _ttl_get(key: str):
    if key in _cache:
        data, expiry = _cache[key]
        if time.monotonic() < expiry:
            return data
    return None

def _ttl_set(key: str, value, ttl: int):
    _cache[key] = (value, time.monotonic() + ttl)

# ─── providers ────────────────────────────────────────────────────────────────
async def _yahoo(ticker: str) -> dict:
    cached = _ttl_get(f"y:{ticker}")
    if cached:
        return cached
    def _sync():
        t    = yf.Ticker(ticker)
        info = t.fast_info
        price   = float(info.last_price or 0)
        prev    = float(info.previous_close or price)
        chg     = price - prev
        chg_p   = (chg / prev * 100) if prev else 0.0
        return {
            "ticker":     ticker,
            "name":       getattr(info, "display_name", None) or ticker,
            "price":      round(price, 4),
            "change":     round(chg, 4),
            "change_pct": round(chg_p, 2),
            "currency":   getattr(info, "currency", "USD"),
            "source":     "yfinance",
            "revolut":    ticker in REVOLUT_STOCKS,
        }
    result = await asyncio.get_running_loop().run_in_executor(None, _sync)
    _ttl_set(f"y:{ticker}", result, 30)
    return result

async def _binance(symbol: str) -> dict:
    cached = _ttl_get(f"b:{symbol}")
    if cached:
        return cached
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym += "USDT"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get("https://api.binance.com/api/v3/ticker/24hr", params={"symbol": sym})
        r.raise_for_status()
        d = r.json()
    base = sym.replace("USDT", "")
    result = {
        "ticker":         base,
        "price":          round(float(d["lastPrice"]), 6),
        "change_pct":     round(float(d["priceChangePercent"]), 2),
        "high_24h":       round(float(d["highPrice"]), 6),
        "low_24h":        round(float(d["lowPrice"]), 6),
        "volume_usd_24h": round(float(d["quoteVolume"]), 0),
        "source":         "Binance",
        "revolut":        base in REVOLUT_CRYPTO,
    }
    _ttl_set(f"b:{symbol}", result, 10)
    return result

def _arrow(chg: float) -> str:
    if chg > 2:  return "🚀"
    if chg > 0:  return "📈"
    if chg < -2: return "🔻"
    if chg < 0:  return "📉"
    return "➡️"

# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="mcprice API v5",
    description=(
        "Real-time financial intelligence. 25 endpoints. No API key required. "
        "Stocks via yfinance · Crypto via Binance · Options via yfinance · "
        "Fear & Greed · Technical Signals · Insider Flow · Earnings · Funding Rates · "
        "Stock Correlation · Options Analysis · Fundamentals · Geopolitical Energy Risk."
    ),
    version="5.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── SYSTEM ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    """Health check."""
    return {"status": "ok", "version": "4.0.0", "tools": 20}

# ─── STOCKS ───────────────────────────────────────────────────────────────────

@app.get("/price/{ticker}", tags=["Stocks"])
async def get_price(ticker: str):
    """Current price for one stock or ETF."""
    ticker = ticker.upper().strip()
    try:
        return await _yahoo(ticker)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/prices", tags=["Stocks"])
async def get_prices_bulk(
    tickers: str = Query(..., description="Comma-separated e.g. NVDA,AAPL,MSFT")
):
    """Prices for up to 20 tickers at once."""
    symbols = [t.strip().upper() for t in tickers.split(",")][:20]
    results = await asyncio.gather(*[_yahoo(s) for s in symbols], return_exceptions=True)
    out = [r for r in results if isinstance(r, dict)]
    return {
        "count":   len(out),
        "results": out,
        "gainers": sorted(out, key=lambda x: x.get("change_pct", 0), reverse=True)[:3],
        "losers":  sorted(out, key=lambda x: x.get("change_pct", 0))[:3],
    }

# ─── CRYPTO ───────────────────────────────────────────────────────────────────
# NOTE: /crypto/movers MUST be before /crypto/{symbol} to avoid route shadowing

@app.get("/crypto/movers", tags=["Crypto"])
async def crypto_movers(
    limit: int = Query(10, ge=1, le=50),
    min_volume: float = Query(10_000_000, description="Min 24h volume in USD")
):
    """Top crypto gainers & losers from Binance 24h."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get("https://api.binance.com/api/v3/ticker/24hr")
        r.raise_for_status()
        all_t = r.json()

    filtered = []
    for t in all_t:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        vol = float(t.get("quoteVolume", 0))
        if vol < min_volume:
            continue
        base = sym[:-4]
        chg  = float(t.get("priceChangePercent", 0))
        filtered.append({
            "ticker":         base,
            "price":          round(float(t["lastPrice"]), 6),
            "change_pct":     round(chg, 2),
            "volume_usd_24h": round(vol, 0),
            "revolut":        base in REVOLUT_CRYPTO,
            "emoji":          _arrow(chg),
        })

    return {
        "gainers":               sorted(filtered, key=lambda x: x["change_pct"], reverse=True)[:limit],
        "losers":                sorted(filtered, key=lambda x: x["change_pct"])[:limit],
        "revolut_movers":        [x for x in sorted(filtered, key=lambda x: abs(x["change_pct"]), reverse=True) if x["revolut"]][:limit],
        "total_pairs_scanned":   len(filtered),
    }


@app.get("/crypto/{symbol}", tags=["Crypto"])
async def get_crypto(symbol: str):
    """Crypto price from Binance (real-time, 10s cache)."""
    symbol = symbol.upper().replace("USDT", "").strip()
    try:
        return await _binance(symbol)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
# ─── REVOLUT ──────────────────────────────────────────────────────────────────

@app.get("/revolut/stocks", tags=["Revolut"])
async def revolut_stocks_list():
    """Full list of stocks tradeable on Revolut."""
    return {"count": len(REVOLUT_STOCKS), "stocks": REVOLUT_STOCKS}


@app.get("/revolut/crypto", tags=["Revolut"])
async def revolut_crypto_list():
    """Full list of crypto tradeable on Revolut."""
    return {"count": len(REVOLUT_CRYPTO), "crypto": sorted(REVOLUT_CRYPTO)}


@app.get("/revolut/check/{ticker}", tags=["Revolut"])
async def revolut_check(ticker: str):
    """Is this stock or crypto available on Revolut? + live price."""
    ticker = ticker.upper().strip()
    on_rev    = ticker in REVOLUT_STOCKS or ticker in REVOLUT_CRYPTO
    is_crypto = ticker in ALL_CRYPTO
    try:
        data  = await (_binance(ticker) if is_crypto else _yahoo(ticker))
        price = data.get("price")
        chg   = data.get("change_pct", 0)
    except Exception:
        price, chg = None, None

    return {
        "ticker":            ticker,
        "revolut_available": on_rev,
        "asset_type":        "crypto" if is_crypto else "stock",
        "price":             price,
        "change_pct":        chg,
        "verdict": (
            f"✅ {ticker} is available on Revolut — ${price} ({chg:+.2f}%)" if on_rev
            else f"❌ {ticker} is NOT available on Revolut"
        ),
    }


@app.get("/snapshot", tags=["Watchlist"])
async def snapshot(
    tickers: Optional[str] = Query(None, description="Comma-separated. Defaults to top watchlist.")
):
    """Rich snapshot for a mixed stock+crypto watchlist."""
    if tickers:
        syms = [t.strip().upper() for t in tickers.split(",")][:25]
    else:
        syms = ["NVDA","AAPL","MSFT","TSLA","LMT","GLD","SPY","BTC","ETH","SOL","XRP","DOGE"]

    stocks  = [s for s in syms if s not in ALL_CRYPTO]
    cryptos = [s for s in syms if s in ALL_CRYPTO]

    s_res, c_res = await asyncio.gather(
        asyncio.gather(*[_yahoo(s)   for s in stocks],  return_exceptions=True),
        asyncio.gather(*[_binance(c) for c in cryptos], return_exceptions=True),
    )
    all_valid = [r for r in list(s_res) + list(c_res) if isinstance(r, dict)]
    avg = sum(r.get("change_pct", 0) for r in all_valid) / len(all_valid) if all_valid else 0

    return {
        "stocks": [r for r in s_res if isinstance(r, dict)],
        "crypto": [r for r in c_res if isinstance(r, dict)],
        "summary": {
            "total":          len(all_valid),
            "avg_change_pct": round(avg, 2),
            "market_mood":    "🟢 Risk-On" if avg > 0 else "🔴 Risk-Off",
            "top_gainer":     max(all_valid, key=lambda x: x.get("change_pct", 0), default={}).get("ticker"),
            "top_loser":      min(all_valid, key=lambda x: x.get("change_pct", 0), default={}).get("ticker"),
        },
    }

# ─── NEW: FEAR & GREED ────────────────────────────────────────────────────────

@app.get("/fear-greed", tags=["Signals"])
async def fear_greed():
    """
    Current Fear & Greed Index from alternative.me.
    Includes trading bias signal + 5-day history. No API key.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://api.alternative.me/fng/", params={"limit": 5})
            r.raise_for_status()
            data = r.json().get("data", [])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    def _classify(s): 
        if s <= 25: return "😱 Extreme Fear"
        if s <= 40: return "😨 Fear"
        if s <= 55: return "😐 Neutral"
        if s <= 75: return "😄 Greed"
        return "🤑 Extreme Greed"

    def _bias(s):
        if s <= 25: return "🟢 Strong BUY — historically best entry point"
        if s <= 40: return "🟡 Cautious BUY — fear creating opportunity"
        if s <= 55: return "⚪ HOLD — no clear edge"
        if s <= 75: return "🟡 Consider TRIM — risk increasing"
        return "🔴 SELL / avoid new longs — extreme greed = near-term top risk"

    score   = int(data[0]["value"])
    labels  = ["Today", "Yesterday", "Last Week", "2 Weeks Ago", "Last Month"]
    history = [
        {"period": labels[i], "score": int(d["value"]), "label": d["value_classification"], "sentiment": _classify(int(d["value"]))}
        for i, d in enumerate(data[:5])
    ]
    return {
        "current_score": score,
        "sentiment":     _classify(score),
        "trading_bias":  _bias(score),
        "history":       history,
        "revolut_tip":   "💳 Fear below 25 = buy NVDA/AAPL/MSFT on Revolut at discount. Greed above 75 = reduce.",
        "source":        "alternative.me/fng",
    }

# ─── NEW: EARNINGS CALENDAR ───────────────────────────────────────────────────

@app.get("/earnings", tags=["Signals"])
async def earnings_calendar(
    tickers: str = Query(..., description="Comma-separated e.g. NVDA,AAPL,META")
):
    """
    Next earnings date + EPS estimates for a list of stocks.
    Flags which are tradeable on Revolut for pre-earnings plays.
    """
    symbols = [t.strip().upper() for t in tickers.split(",")][:15]

    def _fetch(ticker: str) -> dict:
        try:
            t   = yf.Ticker(ticker)
            cal = t.calendar
            ed  = None
            if cal is not None and hasattr(cal, "get"):
                raw_ed = cal.get("Earnings Date") or cal.get("earningsDate")
                if raw_ed is not None:
                    try:
                        items = list(raw_ed)
                        ed    = str(items[0])[:10] if items else None
                    except TypeError:
                        ed = str(raw_ed)[:10]
            eps = None
            if cal is not None and hasattr(cal, "get"):
                raw_eps = cal.get("EPS Estimate") or cal.get("epsEstimate")
                if raw_eps is not None:
                    try: eps = round(float(raw_eps), 4)
                    except: pass
            on_r = ticker in REVOLUT_STOCKS
            return {
                "ticker":          ticker,
                "earnings_date":   ed or "Not scheduled",
                "eps_estimate":    eps,
                "revolut":         on_r,
                "action":          f"💳 Tradeable on Revolut!" if on_r else "❌ Not on Revolut",
            }
        except Exception as exc:
            return {"ticker": ticker, "error": str(exc)}

    loop    = asyncio.get_running_loop()
    results = await asyncio.gather(*[loop.run_in_executor(None, _fetch, s) for s in symbols])
    today   = time.strftime("%Y-%m-%d")
    upcoming = sorted(
        [r for r in results if "error" not in r and r.get("earnings_date", "") >= today],
        key=lambda x: x["earnings_date"]
    )
    return {
        "results":               list(results),
        "upcoming":              upcoming,
        "revolut_opportunities": [r for r in upcoming if r.get("revolut")],
        "summary":               f"📅 {len(upcoming)} upcoming. 💳 {sum(1 for r in upcoming if r.get('revolut'))} on Revolut.",
    }

# ─── NEW: TECHNICAL SIGNALS ───────────────────────────────────────────────────

@app.get("/signals/{ticker}", tags=["Signals"])
async def technical_signals(
    ticker: str,
    period: str = Query("3mo", description="1mo | 3mo | 6mo | 1y")
):
    """
    RSI-14, SMA20, SMA50, EMA9, MACD — full technical buy/sell signal.
    No API key. Includes Revolut tradeable flag.
    """
    ticker = ticker.upper().strip()

    def _calc():
        tk   = yf.Ticker(ticker)
        hist = tk.history(period=period)
        if hist.empty or len(hist) < 20:
            return {"ticker": ticker, "error": "Insufficient data"}
        close  = hist["Close"]
        sma20  = round(close.rolling(20).mean().iloc[-1], 2)
        sma50  = round(close.rolling(min(50, len(close))).mean().iloc[-1], 2)
        ema9   = round(close.ewm(span=9, adjust=False).mean().iloc[-1], 2)
        delta  = close.diff()
        gain   = delta.clip(lower=0).rolling(14).mean()
        loss   = (-delta.clip(upper=0)).rolling(14).mean()
        rs     = gain / loss.replace(0, float("nan"))
        rsi    = round(100 - (100 / (1 + rs.iloc[-1])), 1)
        ema12  = close.ewm(span=12, adjust=False).mean()
        ema26  = close.ewm(span=26, adjust=False).mean()
        macd   = ema12 - ema26
        sig    = macd.ewm(span=9, adjust=False).mean()
        macd_v = round(macd.iloc[-1], 4)
        sig_v  = round(sig.iloc[-1], 4)
        cur    = round(float(close.iloc[-1]), 2)
        on_r   = ticker in REVOLUT_STOCKS

        signals = []
        if rsi < 30:   signals.append("🟢 RSI oversold (<30) — BUY")
        elif rsi > 70: signals.append("🔴 RSI overbought (>70) — SELL")
        else:          signals.append(f"⚪ RSI neutral ({rsi})")
        if cur > sma20: signals.append("🟢 Price above SMA20")
        else:           signals.append("🔴 Price below SMA20")
        if sma20 > sma50: signals.append("🟢 SMA20 > SMA50 golden zone")
        else:             signals.append("🔴 SMA20 < SMA50 death zone")
        if cur > ema9: signals.append("🟢 Price above EMA9 — momentum up")
        else:          signals.append("🔴 Price below EMA9 — momentum down")
        if macd_v > sig_v: signals.append("🟢 MACD bullish crossover")
        else:              signals.append("🔴 MACD bearish crossover")

        bull = sum(1 for s in signals if s.startswith("🟢"))
        overall = (
            "🟢 STRONG BUY"  if bull >= 4 else
            "🟡 MILD BUY"    if bull == 3 else
            "⚪ NEUTRAL"     if bull == 2 else
            "🟡 MILD SELL"   if bull == 1 else
            "🔴 STRONG SELL"
        )
        return {
            "ticker":          ticker,
            "price":           cur,
            "period":          period,
            "rsi_14":          rsi,
            "sma_20":          sma20,
            "sma_50":          sma50,
            "ema_9":           ema9,
            "macd":            macd_v,
            "macd_signal":     sig_v,
            "signals":         signals,
            "overall":         overall,
            "revolut":         on_r,
            "revolut_action":  f"💳 {ticker} on Revolut — {overall} active!" if on_r else f"❌ {ticker} not on Revolut",
        }

    try:
        loop   = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _calc)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

# ─── NEW: INSIDER FLOW ────────────────────────────────────────────────────────

@app.get("/insider-flow", tags=["Signals"])
async def insider_flow(
    tickers: Optional[str] = Query(None, description="Comma-separated filter e.g. NVDA,AAPL")
):
    """
    SEC Form 4 insider buying/selling — cluster detection + Revolut flags.
    Updated every 2h via GitHub Actions. Perfect for timing entries.
    """
    DATA_URL = "https://raw.githubusercontent.com/gepappas98/revolut-pulse/main/public/insider-data.json"
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(DATA_URL)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Insider data unavailable: {exc}")

    filings = data.get("filings", [])
    if tickers:
        upper   = [t.strip().upper() for t in tickers.split(",")]
        filings = [f for f in filings if f.get("ticker") in upper]

    buys  = [f for f in filings if f.get("isBuy")]
    sells = [f for f in filings if not f.get("isBuy")]

    from collections import Counter
    counts   = Counter(f["ticker"] for f in buys)
    clusters = [
        {"ticker": t, "buy_count": c, "revolut": t in REVOLUT_STOCKS}
        for t, c in counts.most_common(10) if c >= 2
    ]
    top_buys = sorted(buys, key=lambda x: x.get("value", 0), reverse=True)[:10]
    for f in top_buys:
        f["revolut_available"] = f.get("ticker") in REVOLUT_STOCKS
        f["value_fmt"] = (
            f"${f['value']/1e6:.2f}M" if f.get("value", 0) >= 1_000_000
            else f"${f.get('value', 0)/1000:.0f}K"
        )

    return {
        "fetched_at":     data.get("fetchedAt", "unknown"),
        "total_buys":     len(buys),
        "total_sells":    len(sells),
        "buy_sell_ratio": round(len(buys) / max(len(sells), 1), 2),
        "cluster_buys":   clusters,
        "top_buys":       top_buys,
        "revolut_plays":  [f for f in top_buys if f.get("revolut_available")],
        "market_signal": (
            "🟢 BULLISH — insiders buying heavily"  if len(buys) > len(sells) * 1.5 else
            "🔴 BEARISH — insiders selling"         if len(sells) > len(buys) * 1.5 else
            "⚪ NEUTRAL"
        ),
        "screener_url": "https://revolut-pulse.lovable.app/insiderflow-pro-v2.html",
    }

# ─── NEW: FUNDING RATES ───────────────────────────────────────────────────────

@app.get("/funding-rates", tags=["Signals"])
async def funding_rates(
    symbols: Optional[str] = Query(None, description="Comma-separated e.g. BTC,ETH,SOL. Empty = top 15.")
):
    """
    Binance perpetual futures funding rates — contrarian signal.
    Extreme positive rate = crowded longs (caution). Negative = short squeeze setup.
    """
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get("https://fapi.binance.com/fapi/v1/premiumIndex")
            r.raise_for_status()
            raw = r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    processed, seen = [], set()
    for item in raw:
        sym = item.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        base = sym[:-4]
        if base in seen:
            continue
        seen.add(base)
        rate = float(item.get("lastFundingRate", 0)) * 100
        processed.append({
            "symbol":       base,
            "rate_pct":     round(rate, 4),
            "annualized":   round(rate * 3 * 365, 1),
            "bias":         "🔴 Bearish (longs paying)" if rate > 0 else "🟢 Bullish (shorts paying)",
            "signal": (
                "⚠️ EXTREME LONG SQUEEZE risk" if rate > 0.1 else
                "🔴 Crowded longs — caution"   if rate > 0.05 else
                "⚪ Neutral"                    if abs(rate) < 0.01 else
                "🟢 Crowded shorts — contrarian BUY"
            ),
            "revolut_crypto": base in REVOLUT_CRYPTO,
        })

    if symbols:
        upper     = [s.strip().upper() for s in symbols.split(",")]
        processed = [p for p in processed if p["symbol"] in upper]
    else:
        processed = sorted(processed, key=lambda x: abs(x["rate_pct"]), reverse=True)[:15]

    return {
        "funding_rates": processed,
        "revolut_picks": [p for p in processed if p["revolut_crypto"]],
        "extreme_alerts":[p for p in processed if abs(p["rate_pct"]) > 0.05],
        "summary": (
            f"📊 {len(processed)} pairs. "
            f"🔴 {sum(1 for p in processed if p['rate_pct'] > 0.05)} extreme long bias. "
            f"🟢 {sum(1 for p in processed if p['rate_pct'] < -0.01)} short squeeze setups."
        ),
        "source": "Binance Perpetual Futures",
    }

# ─── NEW: PRICE ALERT CHECK ───────────────────────────────────────────────────

class AlertItem(BaseModel):
    ticker:    str
    target:    float
    direction: str = "above"  # "above" | "below"

@app.post("/alert-check", tags=["Signals"])
async def alert_check(alerts: List[AlertItem] = Body(...)):
    """
    Check if price targets have been hit for a list of alerts.
    Pass ticker + target + direction (above/below) — get instant verdict.

    Example body:
    [
      {"ticker": "NVDA",  "target": 1000, "direction": "above"},
      {"ticker": "BTC",   "target": 90000,"direction": "above"},
      {"ticker": "AAPL",  "target": 180,  "direction": "below"}
    ]
    """
    results, triggered, safe = [], [], []

    for alert in alerts[:20]:
        ticker = alert.ticker.upper().strip()
        target = alert.target
        direc  = alert.direction.lower()

        try:
            q = (await _binance(ticker) if ticker in ALL_CRYPTO else await _yahoo(ticker))
        except Exception as exc:
            results.append({"ticker": ticker, "error": str(exc)})
            continue

        price  = float(q.get("price", 0))
        hit    = (price >= target if direc == "above" else price <= target)
        gap_p  = ((price - target) / target * 100) if target else 0
        on_r   = ticker in REVOLUT_STOCKS or ticker in REVOLUT_CRYPTO

        entry = {
            "ticker":    ticker,
            "current":   price,
            "target":    target,
            "direction": direc,
            "triggered": hit,
            "gap_pct":   round(gap_p, 2),
            "revolut":   on_r,
            "verdict": (
                f"🚨 TRIGGERED — {ticker} ${price} {'≥' if direc == 'above' else '≤'} ${target}"
                + (" 💳 Trade on Revolut!" if on_r else "")
                if hit else
                f"⏳ Pending — {ticker} ${price} | {gap_p:+.1f}% from ${target}"
            ),
        }
        results.append(entry)
        (triggered if hit else safe).append(entry)

    return {
        "triggered": triggered,
        "safe":      safe,
        "results":   results,
        "summary":   f"🚨 {len(triggered)} TRIGGERED. ⏳ {len(safe)} pending.",
    }

# ─── FROM AWESOME-FINANCE-SKILLS ─────────────────────────────────────────────

# ─── NEWS (alphaear-news) ─────────────────────────────────────────────────────

NEWS_SOURCES = {
    "cls": "财联社 (CLS Finance)", "wallstreetcn": "Wall Street CN",
    "xueqiu": "Xueqiu", "hackernews": "Hacker News",
    "36kr": "36Kr Tech", "weibo": "Weibo Trending", "zhihu": "Zhihu Hot",
}
_BULLISH_KW = {"surge","soar","rally","beat","upgrade","bullish","growth","profit",
               "gain","rise","boost","exceed","record high","strong","buy","recovery"}
_BEARISH_KW = {"crash","plunge","slump","miss","downgrade","bearish","loss","layoff",
               "fraud","fall","drop","decline","warning","risk","sell","record low"}

@app.get("/news", tags=["Finance Skills"])
async def financial_news(
    source: str = Query("wallstreetcn", description="News source: cls|wallstreetcn|xueqiu|hackernews|36kr|weibo|zhihu"),
    count: int  = Query(10, ge=1, le=20)
):
    """Fetch real-time hot financial news from NewsNow API. No API key required."""
    source = source.lower().strip()
    if source not in NEWS_SOURCES:
        raise HTTPException(400, detail=f"Unknown source. Available: {list(NEWS_SOURCES.keys())}")
    url = f"https://newsnow.busiyi.world/api/s?id={source}"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url)
            r.raise_for_status()
            items = r.json().get("items", [])[:count]
    except Exception as exc:
        raise HTTPException(502, detail=str(exc))

    headlines = [{"rank": i+1, "title": it.get("title",""), "url": it.get("url",""),
                  "pubtime": it.get("publish_time","")} for i, it in enumerate(items)]
    bull = sum(1 for h in headlines if any(k in h["title"].lower() for k in _BULLISH_KW))
    bear = sum(1 for h in headlines if any(k in h["title"].lower() for k in _BEARISH_KW))
    return {
        "source": source, "source_name": NEWS_SOURCES[source],
        "count": len(headlines), "headlines": headlines,
        "mood": "🟢 Bullish" if bull > bear else ("🔴 Bearish" if bear > bull else "⚪ Neutral"),
        "bull_signals": bull, "bear_signals": bear,
    }


# ─── DEEPEAR SIGNALS (alphaear-deepear-lite) ──────────────────────────────────

@app.get("/deepear-signals", tags=["Finance Skills"])
async def deepear_signals(limit: int = Query(5, ge=1, le=10)):
    """Fetch live professional investment signals from DeepEar Lite. No API key."""
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get("https://deepear.vercel.app/latest.json",
                           headers={"User-Agent": "mcprice/3.0",
                                    "Referer": "https://deepear.vercel.app/lite"})
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        raise HTTPException(502, detail=str(exc))

    signals = []
    for s in data.get("signals", [])[:limit]:
        sentiment  = float(s.get("sentiment_score", 0))
        confidence = float(s.get("confidence", 0))
        signals.append({
            "title":          s.get("title", ""),
            "summary":        s.get("summary", ""),
            "sentiment_score": round(sentiment, 3),
            "confidence":      round(confidence, 3),
            "intensity":       round(float(s.get("intensity", 0)), 3),
            "reasoning":       s.get("reasoning", ""),
            "sources":         s.get("sources", []),
            "emoji":           "🟢" if sentiment > 0.2 else ("🔴" if sentiment < -0.2 else "⚪"),
        })

    avg_s = round(sum(s["sentiment_score"] for s in signals) / len(signals), 3) if signals else 0
    return {
        "generated_at": data.get("generated_at"),
        "signals_count": len(signals),
        "signals": signals,
        "avg_sentiment": avg_s,
        "overall_mood": "🟢 Bullish" if avg_s > 0.2 else ("🔴 Bearish" if avg_s < -0.2 else "⚪ Mixed"),
        "source": "deepear.vercel.app",
    }


# ─── PREDICTION MARKETS (alphaear-news / Polymarket) ─────────────────────────

@app.get("/prediction-markets", tags=["Finance Skills"])
async def prediction_markets(
    limit:        int            = Query(10, ge=1, le=30),
    topic_filter: Optional[str] = Query(None, description="Keyword filter e.g. bitcoin, fed, election")
):
    """Fetch live Polymarket crowd-probability markets. No API key required."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://gamma-api.polymarket.com/markets",
                           params={"active": "true", "closed": "false", "limit": str(limit * 2)})
            r.raise_for_status()
            raw = r.json()
    except Exception as exc:
        raise HTTPException(502, detail=str(exc))

    if topic_filter:
        kw = topic_filter.lower()
        raw = [m for m in raw if kw in (m.get("question","") + m.get("slug","")).lower()]

    markets = []
    for m in raw[:limit]:
        outcomes = m.get("outcomes", [])
        prices   = m.get("outcomePrices", [])
        probs    = []
        try:
            for o, p in zip(outcomes, prices):
                probs.append({"outcome": str(o), "probability": f"{float(p)*100:.1f}%"})
        except Exception:
            pass
        markets.append({
            "question":      m.get("question",""),
            "probabilities": probs,
            "volume_usd":    round(float(m.get("volume", 0)), 0),
            "slug_url":      f"https://polymarket.com/event/{m.get('slug','')}",
        })
    markets.sort(key=lambda x: x["volume_usd"], reverse=True)
    return {"total": len(markets), "topic_filter": topic_filter, "markets": markets,
            "source": "Polymarket Gamma API"}


# ─── SENTIMENT (alphaear-sentiment adapted, zero deps) ────────────────────────

_SBULL = {"surge","soar","rally","beat","outperform","upgrade","bullish","record high",
          "strong","growth","profit","gain","rise","boost","exceed","optimistic","buy",
          "recovery","breakthrough","expansion","eps beat","buyback","dividend increase"}
_SBEAR = {"crash","plunge","slump","miss","underperform","downgrade","bearish","record low",
          "weak","loss","cut","sell","layoff","fraud","decline","warning","risk","drop",
          "eps miss","guidance cut","bankruptcy","investigation","write-off","fine"}
_SSBULL = {"record earnings","blowout quarter","massive beat","all-time high","explosive growth"}
_SSBEAR = {"bankruptcy","collapse","fraud","crisis","catastrophic","sec investigation",
           "accounting scandal","going concern","delisted"}

class SentimentRequest(BaseModel):
    texts: List[str]

@app.post("/sentiment", tags=["Finance Skills"])
async def news_sentiment(body: SentimentRequest):
    """
    Fast financial sentiment scoring (FinBERT-distilled keyword lexicon).
    POST a list of texts, get back score -1.0 (bearish) to +1.0 (bullish).
    Zero external deps — instant response.
    """
    results = []
    for i, text in enumerate(body.texts[:30]):
        t = text.lower()
        bull  = [k for k in _SBULL  if k in t]
        bear  = [k for k in _SBEAR  if k in t]
        sbull = [k for k in _SSBULL if k in t]
        sbear = [k for k in _SSBEAR if k in t]
        score = max(-1.0, min(1.0, round(
            len(bull)*0.15 + len(sbull)*0.40 - len(bear)*0.15 - len(sbear)*0.40, 3
        )))
        label = "positive" if score > 0.2 else ("negative" if score < -0.2 else "neutral")
        results.append({
            "index": i, "text": text[:200], "score": score, "label": label,
            "bull_signals": bull + sbull, "bear_signals": bear + sbear,
            "emoji": "🟢" if score > 0.1 else ("🔴" if score < -0.1 else "⚪"),
        })

    avg   = round(sum(r["score"] for r in results) / len(results), 3) if results else 0
    return {
        "results": results, "count": len(results), "avg_score": avg,
        "positive": sum(1 for r in results if r["label"]=="positive"),
        "negative": sum(1 for r in results if r["label"]=="negative"),
        "neutral":  sum(1 for r in results if r["label"]=="neutral"),
        "overall":  "🟢 Bullish" if avg > 0.15 else ("🔴 Bearish" if avg < -0.15 else "⚪ Neutral"),
        "method": "keyword-lexicon (FinBERT-distilled)",
    }

# ═══════════════════════════════════════════════════════════════════════════════
# v5.0 — NEW REST ENDPOINTS (Tools 21–25 from Skills conversion)
# ═══════════════════════════════════════════════════════════════════════════════

# ─── /correlation — stock_correlation (Tool 21) ──────────────────────────────

@app.get("/correlation", tags=["Analytics v5"])
async def correlation(
    tickers: str  = Query(..., description="Comma-separated e.g. NVDA,AMD or just NVDA for discover mode"),
    mode:    str  = Query("discover", description="discover | pair | cluster | rolling"),
    period:  str  = Query("1y",       description="1y | 2y | 6mo | 3mo"),
):
    """
    Stock correlation engine — 4 modes:
    - discover: find top correlated peers for 1 ticker + Revolut sympathy plays
    - pair:     deep pairwise analysis (Pearson, beta, R², spread Z-score, pair trade signal)
    - cluster:  full correlation matrix for 3–15 tickers (diversifiers, clusters)
    - rolling:  rolling 20/60/120d windows + regime-conditional (crisis amplification)

    No API key. Powered by yfinance.
    """
    import numpy as np, pandas as pd, math

    mode_lc = mode.lower().strip()
    if mode_lc not in ("discover", "pair", "cluster", "rolling"):
        raise HTTPException(400, detail=f"Unknown mode. Use: discover | pair | cluster | rolling")

    tkrs = [t.strip().upper() for t in tickers.split(",") if t.strip()][:15]
    if not tkrs:
        raise HTTPException(400, detail="Provide at least one ticker")

    loop = asyncio.get_running_loop()

    def _arrow_corr(c: float) -> str:
        if c >= 0.80: return "Very strong co-move 🔴"
        if c >= 0.60: return "Strong co-move 🟠"
        if c >= 0.40: return "Moderate 🟡"
        if c >= 0.20: return "Weak ⚪"
        if c >= -0.20: return "Near-zero ➡️"
        return "Inverse / hedge candidate 🟢"

    # ── DISCOVER ─────────────────────────────────────────────────────────────
    if mode_lc == "discover":
        target = tkrs[0]
        SECTOR_MAP = {
            "Technology":        ["NVDA","AMD","AVGO","INTC","QCOM","TSM","ASML","MU","MSFT","AAPL","GOOGL","META","LRCX","AMAT"],
            "Financial Services":["JPM","BAC","GS","MS","V","MA","BLK","SCHW","AXP","WFC"],
            "Healthcare":        ["JNJ","PFE","LLY","ABBV","MRK","AMGN","GILD","UNH","MRNA"],
            "Energy":            ["XOM","CVX","COP","OXY","SLB","HAL","XLE"],
            "Industrials":       ["LMT","RTX","BA","GD","NOC","LHX","HON","CAT"],
            "Consumer Cyclical": ["AMZN","TSLA","NKE","MCD","SBUX","HD","WMT"],
        }

        def _calc():
            import yfinance as yf
            info = {}
            try: info = yf.Ticker(target).info
            except: pass
            sector = info.get("sector","Technology")
            peers  = SECTOR_MAP.get(sector, SECTOR_MAP["Technology"])
            peers  = [t for t in dict.fromkeys(peers) if t != target][:18]
            all_t  = [target] + peers

            data = yf.download(all_t, period=period, auto_adjust=True, progress=False)
            closes = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data
            closes = closes.dropna(axis=1, thresh=max(20, len(data)//3))
            returns = np.log(closes / closes.shift(1)).dropna()
            if target not in returns.columns:
                return {"error": f"No data for {target}"}
            corr_s = returns.corr()[target].drop(target, errors="ignore")
            ranked = corr_s.abs().sort_values(ascending=False)
            out = []
            for tkr in ranked.index[:10]:
                c = float(corr_s[tkr])
                out.append({
                    "ticker": tkr, "correlation": round(c,4),
                    "abs_corr": round(abs(c),4), "strength": _arrow_corr(c),
                    "revolut": tkr in REVOLUT_STOCKS,
                })
            return {"target": target, "period": period, "top_correlated": out,
                    "revolut_picks": [x for x in out if x["revolut"]][:5],
                    "sympathy_plays": [x["ticker"] for x in out if x["correlation"]>0.6][:3],
                    "hedge_candidates": [x["ticker"] for x in out if x["correlation"]<-0.3],
                    "note": "Correlation ≠ causation. Past correlations may not persist."}

        try:
            return await loop.run_in_executor(None, _calc)
        except Exception as e:
            raise HTTPException(502, detail=str(e))

    # ── PAIR ──────────────────────────────────────────────────────────────────
    if mode_lc == "pair":
        if len(tkrs) < 2:
            raise HTTPException(400, detail="Provide 2 tickers for pair mode")
        ta, tb = tkrs[0], tkrs[1]

        def _calc_pair():
            import yfinance as yf
            data = yf.download([ta,tb], period=period, auto_adjust=True, progress=False)
            closes = data["Close"][[ta,tb]].dropna() if isinstance(data.columns, pd.MultiIndex) else data.dropna()
            rets = np.log(closes/closes.shift(1)).dropna()
            if ta not in rets.columns or tb not in rets.columns:
                return {"error": "Insufficient data"}
            corr = float(rets[ta].corr(rets[tb]))
            cov  = rets.cov()
            beta = float(cov.loc[tb,ta]/cov.loc[ta,ta]) if cov.loc[ta,ta]!=0 else 0
            roll = rets[ta].rolling(60).corr(rets[tb])
            spread  = np.log(closes[ta]/closes[tb])
            z_score = float((spread-spread.mean())/spread.std()) if spread.std()!=0 else 0
            return {
                "ticker_a": ta, "ticker_b": tb, "period": period,
                "correlation": round(corr,4), "r_squared": round(corr**2,4),
                "beta_b_vs_a": round(beta,4),
                "rolling_60d": {"current": round(float(roll.iloc[-1]),4), "mean": round(float(roll.mean()),4),
                                "std": round(float(roll.std()),4), "min": round(float(roll.min()),4),
                                "max": round(float(roll.max()),4)},
                "spread_z_score": round(z_score,3),
                "pair_trade": abs(z_score)>2,
                "action": (f"Long {ta} / Short {tb}" if z_score<-2 else
                           f"Long {tb} / Short {ta}" if z_score>2 else "Spread in range — no trade"),
                "interpretation": _arrow_corr(corr),
                "revolut_a": ta in REVOLUT_STOCKS, "revolut_b": tb in REVOLUT_STOCKS,
                "observations": len(rets),
            }
        try:
            return await loop.run_in_executor(None, _calc_pair)
        except Exception as e:
            raise HTTPException(502, detail=str(e))

    # ── CLUSTER ───────────────────────────────────────────────────────────────
    if mode_lc == "cluster":
        if len(tkrs) < 3:
            raise HTTPException(400, detail="Provide 3+ tickers for cluster mode")

        def _calc_cluster():
            import yfinance as yf
            data = yf.download(tkrs, period=period, auto_adjust=True, progress=False)
            closes = data["Close"].dropna(axis=1, thresh=max(20,len(data)//3)) if isinstance(data.columns,pd.MultiIndex) else data.dropna()
            rets = np.log(closes/closes.shift(1)).dropna()
            corr_m = rets.corr()
            pairs = []
            cols = list(corr_m.columns)
            for i in range(len(cols)):
                for j in range(i+1,len(cols)):
                    pairs.append({"a":cols[i],"b":cols[j],"corr":round(float(corr_m.iloc[i,j]),4)})
            pairs.sort(key=lambda x: abs(x["corr"]), reverse=True)
            avg_corr = {t: round(float(corr_m[t].drop(t).abs().mean()),4) for t in cols}
            return {
                "tickers": tkrs, "period": period,
                "top_pairs":  pairs[:5],
                "weak_pairs": pairs[-5:],
                "avg_corr_per_ticker": avg_corr,
                "diversifiers":    sorted(avg_corr.items(),key=lambda x:x[1])[:3],
                "most_connected":  sorted(avg_corr.items(),key=lambda x:x[1],reverse=True)[:3],
                "revolut_available": {t: t in REVOLUT_STOCKS for t in tkrs},
            }
        try:
            return await loop.run_in_executor(None, _calc_cluster)
        except Exception as e:
            raise HTTPException(502, detail=str(e))

    # ── ROLLING ───────────────────────────────────────────────────────────────
    if mode_lc == "rolling":
        if len(tkrs) < 2:
            raise HTTPException(400, detail="Provide 2 tickers for rolling mode")
        ta, tb = tkrs[0], tkrs[1]

        def _calc_rolling():
            import yfinance as yf
            data = yf.download([ta,tb], period=period, auto_adjust=True, progress=False)
            closes = data["Close"][[ta,tb]].dropna() if isinstance(data.columns,pd.MultiIndex) else data.dropna()
            rets = np.log(closes/closes.shift(1)).dropna()
            if ta not in rets.columns or tb not in rets.columns:
                return {"error":"Insufficient data"}
            windows = {}
            for w in [20,60,120]:
                roll = rets[ta].rolling(w).corr(rets[tb]).dropna()
                windows[f"{w}d"] = {"current":round(float(roll.iloc[-1]),4),"mean":round(float(roll.mean()),4),
                                    "std":round(float(roll.std()),4),"min":round(float(roll.min()),4),
                                    "max":round(float(roll.max()),4)}
            regimes = {}
            ret_a = rets[ta]
            for name,mask in [("all_days",pd.Series(True,index=rets.index)),
                               ("up_days",ret_a>0),("down_days",ret_a<0),
                               ("high_vol",ret_a.abs()>ret_a.abs().quantile(0.75)),
                               ("large_drawdown",ret_a<-0.02)]:
                subset = rets[mask]
                if len(subset)>=20:
                    regimes[name]={"corr":round(float(subset[ta].corr(subset[tb])),4),"days":int(mask.sum())}
            crisis_amp = (regimes.get("large_drawdown",{}).get("corr",0) >
                          regimes.get("all_days",{}).get("corr",0)+0.1)
            return {
                "ticker_a":ta,"ticker_b":tb,"period":period,
                "rolling_windows":windows,"regime_correlation":regimes,
                "crisis_amplification": crisis_amp,
                "key_insight": ("⚠️ Correlation spikes in sell-offs — diversification may fail in crisis"
                                if crisis_amp else "✅ Stable correlation across regimes"),
                "revolut_a":ta in REVOLUT_STOCKS,"revolut_b":tb in REVOLUT_STOCKS,
            }
        try:
            return await loop.run_in_executor(None, _calc_rolling)
        except Exception as e:
            raise HTTPException(502, detail=str(e))


# ─── /options/analysis — options_analysis (Tool 22) ──────────────────────────

class OptionsRequest(BaseModel):
    strategy:        str
    underlying:      str
    spot:            float
    strikes:         List[float]
    premium:         float
    dte:             int   = 30
    iv:              float = 0.20
    quantity:        int   = 1
    multiplier:      int   = 100
    risk_free_rate:  float = 0.043

@app.post("/options/analysis", tags=["Analytics v5"])
async def options_analysis_endpoint(body: OptionsRequest):
    """
    Black-Scholes options payoff analysis — returns JSON payoff curve, Greeks, breakevens.
    Supports: butterfly | vertical_spread | iron_condor | straddle | strangle | covered_call | naked_put

    POST body example (bull call spread):
    {
      "strategy": "vertical_spread",
      "underlying": "NVDA",
      "spot": 880.0,
      "strikes": [860.0, 920.0],
      "premium": 18.50,
      "dte": 21,
      "iv": 0.42
    }
    """
    import math

    def norm_cdf(x):
        if x<-8: return 0.0
        if x>8:  return 1.0
        t = 1/(1+0.2316419*abs(x))
        p = 1-(1/math.sqrt(2*math.pi))*math.exp(-0.5*x*x)*t*(0.319381530+t*(-0.356563782+t*(1.781477937+t*(-1.821255978+t*1.330274429))))
        return p if x>=0 else 1-p

    def bs_call(S,K,T,r,sig):
        if T<=0: return max(S-K,0)
        d1=(math.log(S/K)+(r+0.5*sig**2)*T)/(sig*math.sqrt(T)); d2=d1-sig*math.sqrt(T)
        return S*norm_cdf(d1)-K*math.exp(-r*T)*norm_cdf(d2)

    def bs_put(S,K,T,r,sig):
        return bs_call(S,K,T,r,sig)-S+K*math.exp(-r*T)

    def bs_delta(S,K,T,r,sig):
        if T<=0: return 1.0
        d1=(math.log(S/K)+(r+0.5*sig**2)*T)/(sig*math.sqrt(T))
        return norm_cdf(d1)

    T      = body.dte/365.0
    strat  = body.strategy.lower().strip()
    strikes= body.strikes
    spot   = body.spot
    iv     = body.iv
    r      = body.risk_free_rate
    scale  = body.quantity * body.multiplier

    min_s  = min(strikes)*0.80
    max_s  = max(strikes)*1.20
    pr     = [round(min_s+(max_s-min_s)*i/20,2) for i in range(21)]

    def exp_pnl(S):
        if strat=="butterfly":
            k1,k2,k3=strikes[0],strikes[1],strikes[2]
            return k3-S if S>=k2 else (S-k1 if S>=k1 else 0) if S<k3 else 0
        if strat=="vertical_spread":
            return max(S-strikes[0],0)-max(S-strikes[1],0)
        if strat=="iron_condor":
            k1,k2,k3,k4=(strikes+[strikes[-1]+1])[:4]
            return -(max(k2-S,0)-max(k1-S,0)+max(S-k3,0)-max(S-k4,0))
        if strat=="straddle":
            return max(S-strikes[0],0)+max(strikes[0]-S,0)
        if strat=="strangle":
            return max(strikes[0]-S,0)+max(S-strikes[1],0)
        if strat=="covered_call":
            return S-spot-max(S-strikes[0],0)
        if strat=="naked_put":
            return -max(strikes[0]-S,0)
        return 0

    def theory_pnl(S):
        if strat=="butterfly":
            k1,k2,k3=strikes[0],strikes[1],strikes[2]
            return bs_put(S,k1,T,r,iv)-2*bs_put(S,k2,T,r,iv)+bs_put(S,k3,T,r,iv)
        if strat=="vertical_spread":
            return bs_call(S,strikes[0],T,r,iv)-bs_call(S,strikes[1],T,r,iv)
        if strat=="straddle":
            return bs_call(S,strikes[0],T,r,iv)+bs_put(S,strikes[0],T,r,iv)
        if strat=="strangle":
            return bs_put(S,strikes[0],T,r,iv)+bs_call(S,strikes[1],T,r,iv)
        if strat=="naked_put":
            return -bs_put(S,strikes[0],T,r,iv)
        if strat=="covered_call":
            return S-spot-bs_call(S,strikes[0],T,r,iv)
        return exp_pnl(S)

    ce=[round((exp_pnl(p)-body.premium)*scale,2) for p in pr]
    ct=[round((theory_pnl(p)-body.premium)*scale,2) for p in pr]

    max_p=max(ce); max_l=min(ce)
    bes=[]
    for i in range(len(ce)-1):
        if ce[i]*ce[i+1]<=0 and ce[i+1]-ce[i]!=0:
            bes.append(round(pr[i]-ce[i]*(pr[i+1]-pr[i])/(ce[i+1]-ce[i]),2))

    k_c=strikes[len(strikes)//2]
    on_rev=body.underlying.upper() in REVOLUT_STOCKS

    return {
        "strategy": strat, "underlying": body.underlying.upper(),
        "spot": spot, "strikes": strikes, "dte": body.dte,
        "iv_pct": round(iv*100,1), "premium": body.premium, "scale": scale,
        "max_profit_usd": max_p, "max_loss_usd": max_l,
        "breakevens": bes,
        "current_theory_pnl": round((theory_pnl(spot)-body.premium)*scale,2),
        "risk_reward_ratio": round(abs(max_p/max_l),2) if max_l!=0 else None,
        "delta_approx": round(bs_delta(spot,k_c,T,r,iv),4),
        "payoff_curve": {"prices": pr, "expiry_pnl": ce, "theory_pnl": ct},
        "revolut_available": on_rev,
        "revolut_note": (
            f"💳 {body.underlying.upper()} on Revolut — no options available but use this for directional bias on the stock."
            if on_rev else f"❌ {body.underlying.upper()} not on Revolut"
        ),
        "summary": (f"{strat.replace('_',' ').title()}: max profit ${max_p:+.0f} / "
                    f"max loss ${max_l:+.0f} / BE: {', '.join(f'${b}' for b in bes) or 'N/A'}"),
    }


# ─── /geopolitical/energy — geopolitical_energy_risk (Tool 23) ───────────────

@app.get("/geopolitical/energy", tags=["Analytics v5"])
async def geopolitical_energy():
    """
    Real-time Strait of Hormuz status — shipping transits, oil prices,
    stranded vessels, war-risk insurance, diplomatic situation.
    Returns Revolut energy trade signals: XOM, CVX, OXY, XLE.
    No API key. Source: hormuzstraitmonitor.com
    """
    HORMUZ_API = "https://hormuzstraitmonitor.com/api/dashboard"
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(HORMUZ_API, headers=HEADERS)
            r.raise_for_status()
            payload = r.json()
    except Exception as exc:
        raise HTTPException(502, detail=f"Hormuz Monitor unavailable: {exc}")

    if not payload.get("success"):
        raise HTTPException(502, detail="Hormuz Monitor returned success=false")

    d         = payload.get("data", {})
    strait    = d.get("straitStatus", {})
    ships     = d.get("shipCount", {})
    oil       = d.get("oilPrice", {})
    stranded  = d.get("strandedVessels", {})
    insurance = d.get("insurance", {})
    throughput= d.get("throughput", {})
    diplomacy = d.get("diplomacy", {})
    gti       = d.get("globalTradeImpact", {})

    ins_level  = insurance.get("level","normal")
    pct_normal = ships.get("percentOfNormal",100)
    brent_chg  = oil.get("changePercent24h",0)
    risk_emoji = {"normal":"🟢","elevated":"🟡","high":"🔴","critical":"🚨"}.get(ins_level,"⚪")

    ENERGY_TICKERS = [t for t in ["XOM","CVX","COP","OXY","XLE","USO","GLD"] if t in REVOLUT_STOCKS]

    trade_bias = (
        "🔴 BULLISH oil — consider XOM, CVX, OXY, XLE on Revolut (long energy)" if ins_level in ("high","critical") or pct_normal<80 else
        "🟡 MILD bullish — monitor XLE/OXY for Revolut entry" if ins_level=="elevated" else
        "🟢 Normal — no Hormuz premium. Focus on fundamentals."
    )

    return {
        "source": "hormuzstraitmonitor.com",
        "last_updated": d.get("lastUpdated", payload.get("timestamp")),
        "strait_status": {"status": strait.get("status"), "since": strait.get("since"), "description": strait.get("description")},
        "ship_traffic": {"current_transits": ships.get("currentTransits"), "last_24h": ships.get("last24h"),
                         "percent_of_normal": pct_normal,
                         "signal": "🚨 MAJOR DISRUPTION" if pct_normal<60 else ("🔴 DISRUPTION" if pct_normal<80 else ("🟡 Mild" if pct_normal<95 else "🟢 Normal"))},
        "oil_price": {"brent_usd": oil.get("brentPrice"), "change_pct_24h": brent_chg,
                      "trend": "📈 Rising" if brent_chg>0 else "📉 Falling"},
        "stranded_vessels": {"total": stranded.get("total",0), "tankers": stranded.get("tankers",0),
                             "change_today": stranded.get("changeToday",0)},
        "insurance_risk": {"level": ins_level, "emoji": risk_emoji,
                           "war_risk_pct": insurance.get("warRiskPercent"),
                           "multiplier": insurance.get("multiplier")},
        "cargo_throughput": {"percent_normal": throughput.get("percentOfNormal"),
                             "today_dwt": throughput.get("todayDWT")},
        "diplomacy": {"status": diplomacy.get("status"), "headline": diplomacy.get("headline")},
        "global_trade_impact": {"pct_world_oil_at_risk": gti.get("percentOfWorldOilAtRisk"),
                                "daily_cost_bn_usd": gti.get("estimatedDailyCostBillions"),
                                "alternative_routes": gti.get("alternativeRoutes",[])},
        "revolut_energy_signals": {
            "trade_bias": trade_bias,
            "revolut_energy_tickers": ENERGY_TICKERS,
            "suggested_next": ["revolut_sector_scan('energy')", "technical_signals('XLE')", "technical_signals('OXY')"],
        },
        "risk_summary": (f"{risk_emoji} {strait.get('status','?')} | Traffic: {pct_normal}% | "
                         f"Insurance: {ins_level.upper()} | Brent: ${oil.get('brentPrice','?')} ({brent_chg:+.2f}%)"),
    }


# ─── /fundamentals/{ticker} — stock_deep_data (Tool 24) ──────────────────────

@app.get("/fundamentals/{ticker}", tags=["Analytics v5"])
async def fundamentals(
    ticker:    str,
    data_type: str  = Query("overview", description="overview|income|balance|cashflow|analysts|holders|insiders|dividends|news|all"),
    quarterly: bool = Query(False, description="Use quarterly data (for income/balance/cashflow)"),
):
    """
    Deep fundamental data via yfinance — income statement, balance sheet, cash flow,
    analyst targets, institutional holders, insider transactions, dividends, news.
    No API key. Flags Revolut availability.

    data_type options:
    - overview:  P/E, PEG, beta, sector, market cap, margins, 52w range
    - income:    Revenue, EPS, net income, EBITDA
    - balance:   Assets, liabilities, equity, cash
    - cashflow:  Operating, investing, financing, FCF
    - analysts:  Price targets + buy/hold/sell counts + upgrades/downgrades
    - holders:   Institutional + mutual fund holdings
    - insiders:  SEC Form 4 transactions for this ticker
    - dividends: Dividend history + yield + payout ratio
    - news:      Latest 8 news items
    - all:       Overview + analysts + health score
    """
    ticker = ticker.upper().strip()
    dt     = data_type.lower().strip()
    valid  = ["overview","income","balance","cashflow","analysts","holders","insiders","dividends","news","all"]
    if dt not in valid:
        raise HTTPException(400, detail=f"Unknown data_type. Options: {valid}")

    on_rev = ticker in REVOLUT_STOCKS

    def _fetch():
        import yfinance as yf, pandas as pd

        tk   = yf.Ticker(ticker)
        info = tk.info or {}
        fi   = tk.fast_info

        def _fmt(v):
            if v is None: return "N/A"
            try:
                v=float(v)
                if v>=1e12: return f"${v/1e12:.2f}T"
                if v>=1e9:  return f"${v/1e9:.2f}B"
                if v>=1e6:  return f"${v/1e6:.2f}M"
                return f"${v:.2f}"
            except: return str(v)

        def _df(df):
            if df is None or (hasattr(df,"empty") and df.empty): return []
            try:
                if isinstance(df.columns, pd.MultiIndex): df=df.droplevel(0,axis=1)
                return df.reset_index().head(4).to_dict(orient="records")
            except: return []

        out = {"ticker": ticker, "revolut_available": on_rev}

        if dt in ("overview","all"):
            out["overview"] = {
                "name": info.get("shortName",ticker), "sector": info.get("sector"),
                "industry": info.get("industry"), "market_cap": _fmt(info.get("marketCap")),
                "price": round(float(fi.last_price or 0),2),
                "52w_high": round(float(info.get("fiftyTwoWeekHigh",0) or 0),2),
                "52w_low":  round(float(info.get("fiftyTwoWeekLow",0) or 0),2),
                "trailing_pe": round(float(info.get("trailingPE",0) or 0),2),
                "forward_pe":  round(float(info.get("forwardPE",0) or 0),2),
                "peg_ratio":   round(float(info.get("pegRatio",0) or 0),2),
                "beta":        round(float(info.get("beta",0) or 0),2),
                "dividend_yield": f"{round((info.get('dividendYield') or 0)*100,2)}%",
                "profit_margin":  f"{round((info.get('profitMargins') or 0)*100,2)}%",
                "revenue_ttm": _fmt(info.get("totalRevenue")),
                "ebitda":      _fmt(info.get("ebitda")),
                "description": (info.get("longBusinessSummary") or "")[:350],
            }
        if dt=="income":
            stmt=tk.quarterly_income_stmt if quarterly else tk.income_stmt
            out["income_statement"]=_df(stmt.T) if stmt is not None and not stmt.empty else []
            out["period"]="quarterly" if quarterly else "annual"
        if dt=="balance":
            bs=tk.quarterly_balance_sheet if quarterly else tk.balance_sheet
            out["balance_sheet"]=_df(bs.T) if bs is not None and not bs.empty else []
            out["period"]="quarterly" if quarterly else "annual"
        if dt=="cashflow":
            cf=tk.quarterly_cashflow if quarterly else tk.cashflow
            out["cashflow"]=_df(cf.T) if cf is not None and not cf.empty else []
            try:
                op=float(cf.loc["Operating Cash Flow"].iloc[0]); cap=float(cf.loc["Capital Expenditure"].iloc[0])
                out["fcf_latest"]=_fmt(op+cap)
            except: out["fcf_latest"]="N/A"
        if dt in ("analysts","all"):
            try:
                t2=tk.analyst_price_targets
                out["analyst_targets"]={"current":round(float(t2.get("current",0) or 0),2),
                    "mean":round(float(t2.get("mean",0) or 0),2),
                    "high":round(float(t2.get("high",0) or 0),2),
                    "low":round(float(t2.get("low",0) or 0),2),
                    "num_analysts":t2.get("numberOfAnalysts")}
                recs=tk.recommendations
                if recs is not None and not recs.empty:
                    l=recs.iloc[0]
                    out["recommendation"]={"strong_buy":int(l.get("strongBuy",0)),
                        "buy":int(l.get("buy",0)),"hold":int(l.get("hold",0)),
                        "sell":int(l.get("sell",0)),"strong_sell":int(l.get("strongSell",0))}
            except Exception as e: out["analysts_error"]=str(e)
        if dt=="holders":
            try:
                inst=tk.institutional_holders
                out["institutional_holders"]=_df(inst) if inst is not None else []
            except Exception as e: out["holders_error"]=str(e)
        if dt=="insiders":
            try:
                ins=tk.insider_transactions
                out["insider_transactions"]=_df(ins)[:10] if ins is not None else []
                if ins is not None and not ins.empty:
                    buys=ins[ins["Shares"]>0]
                    out["insider_signal"]=("🟢 Net buying" if len(buys)>len(ins)//2 else "🔴 Net selling")
            except Exception as e: out["insiders_error"]=str(e)
        if dt=="dividends":
            try:
                divs=tk.dividends
                out["dividend_history"]=[{"date":str(i)[:10],"amount":round(float(v),4)} for i,v in (divs.tail(8).items() if divs is not None and not divs.empty else [])]
                out["dividend_yield"]=f"{round((info.get('dividendYield') or 0)*100,2)}%"
                out["payout_ratio"]=f"{round((info.get('payoutRatio') or 0)*100,2)}%"
            except Exception as e: out["dividends_error"]=str(e)
        if dt=="news":
            try:
                out["news"]=[{"title":n.get("title"),"publisher":n.get("publisher"),"link":n.get("link")} for n in (tk.news or [])[:8]]
            except Exception as e: out["news_error"]=str(e)
        if dt=="all":
            pe=float(info.get("trailingPE",0) or 0); peg=float(info.get("pegRatio",0) or 0); pm=float(info.get("profitMargins",0) or 0)
            out["health_score"]={"valuation":"cheap" if pe<15 else ("fair" if pe<30 else "expensive"),
                "growth_adj":"undervalued" if 0<peg<1 else ("fair" if peg<2 else "expensive/no-growth"),
                "profitability":"high-margin" if pm>0.2 else ("moderate" if pm>0.05 else "thin/loss"),
                "revolut_verdict":(f"💳 {ticker} on Revolut — " +
                    ("📈 accumulate" if pe<25 and pm>0.1 else "⏳ monitor")) if on_rev else f"❌ {ticker} not on Revolut"}
        return out

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _fetch)
    except Exception as e:
        raise HTTPException(502, detail=str(e))


# ─── /options/chain/{ticker} — options_chain (Tool 25) ───────────────────────

@app.get("/options/chain/{ticker}", tags=["Analytics v5"])
async def options_chain_endpoint(
    ticker:          str,
    expiry_index:    int  = Query(0,     description="0=nearest, 1=next, etc."),
    option_type:     str  = Query("both",description="calls | puts | both"),
    near_money_only: bool = Query(True,  description="Only show strikes within ±10% of spot"),
):
    """
    Live options chain via yfinance — calls, puts, IV surface, open interest.
    Includes max pain calculation, put/call OI ratio, IV signal for Revolut timing.
    No API key required.
    """
    ticker = ticker.upper().strip()
    on_rev = ticker in REVOLUT_STOCKS

    def _fetch():
        import yfinance as yf, pandas as pd

        tk      = yf.Ticker(ticker)
        spot    = round(float(tk.fast_info.last_price or 0),2)
        expiries= tk.options
        if not expiries:
            return {"error": f"No options data for {ticker}"}

        idx   = min(expiry_index, len(expiries)-1)
        exp   = expiries[idx]
        chain = tk.option_chain(exp)

        def _process(df, otype):
            if df is None or df.empty: return []
            df=df.copy()
            if near_money_only and spot>0:
                df=df[(df["strike"]>=spot*0.90)&(df["strike"]<=spot*1.10)]
            out=[]
            for _,row in df.iterrows():
                strike=float(row.get("strike",0)); bid=float(row.get("bid",0) or 0)
                ask=float(row.get("ask",0) or 0); iv=float(row.get("impliedVolatility",0) or 0)
                oi=int(row.get("openInterest",0) or 0); vol=int(row.get("volume",0) or 0)
                mono=round((spot-strike)/spot*100,1) if otype=="call" else round((strike-spot)/spot*100,1)
                out.append({"strike":strike,"type":otype,"bid":round(bid,2),"ask":round(ask,2),
                    "mid":round((bid+ask)/2,2),"iv_pct":round(iv*100,1),"open_interest":oi,
                    "volume":vol,"in_the_money":bool(row.get("inTheMoney",False)),
                    "moneyness_pct":mono,"bid_ask_spread":round(ask-bid,2)})
            return sorted(out,key=lambda x:x["strike"])

        calls_out=_process(chain.calls,"call") if option_type in ("calls","both") else []
        puts_out= _process(chain.puts, "put")  if option_type in ("puts","both")  else []
        all_opts=calls_out+puts_out

        oi_by_s={}
        for o in all_opts: oi_by_s[o["strike"]]=oi_by_s.get(o["strike"],0)+o["open_interest"]
        max_pain=max(oi_by_s,key=oi_by_s.get) if oi_by_s else None

        ivs=[o["iv_pct"] for o in all_opts if o["iv_pct"]>0]
        atm_iv=None
        for o in sorted(all_opts,key=lambda x:abs(x["strike"]-spot)):
            if o.get("iv_pct",0)>0: atm_iv=o["iv_pct"]; break
        avg_iv=round(sum(ivs)/len(ivs),1) if ivs else 0
        pc_ratio=(round(sum(o["open_interest"] for o in puts_out)/max(sum(o["open_interest"] for o in calls_out),1),2)
                  if puts_out and calls_out else None)
        iv_signal=("🔴 High IV — sell strategies favored" if atm_iv and atm_iv>40 else
                   "🟡 Elevated IV — event priced in" if atm_iv and atm_iv>25 else
                   "🟢 Low IV — buy strategies favored" if atm_iv else "⚪ No IV data")

        return {
            "ticker":ticker,"spot":spot,"expiry":exp,"expiry_index":idx,
            "available_expiries":list(expiries[:6]),"calls":calls_out,"puts":puts_out,
            "summary":{"total_calls":len(calls_out),"total_puts":len(puts_out),
                       "max_pain_strike":max_pain,"avg_iv_pct":avg_iv,"atm_iv_pct":atm_iv,
                       "put_call_oi_ratio":pc_ratio,"iv_signal":iv_signal},
            "revolut_available":on_rev,
            "revolut_note":(f"💳 {ticker} on Revolut — IV signal: {'big move expected' if atm_iv and atm_iv>30 else 'steady state'}"
                           if on_rev else f"❌ {ticker} not on Revolut"),
        }

    loop=asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _fetch)
    except Exception as e:
        raise HTTPException(502, detail=str(e))


# ─── Update health + /docs banner ────────────────────────────────────────────

# Override health to reflect v5
@app.get("/health", tags=["System"], include_in_schema=False)
async def health_v5():
    return {"status":"ok","version":"5.0.0","tools":25,"new_in_v5":["correlation","options_analysis","geopolitical_energy","fundamentals","options_chain"]}
