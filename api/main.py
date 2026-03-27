#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║              mcprice — FastAPI HTTP Layer  v3.0                  ║
║                                                                  ║
║  Exposes the same logic as the MCP server over plain HTTP.       ║
║  Useful for:                                                     ║
║    • Programmatic SEO pages                                      ║
║    • Browser / JS frontends                                      ║
║    • Webhook integrations                                        ║
║    • Direct REST calls without MCP client                        ║
║                                                                  ║
║  v3.0 new endpoints (+6):                                        ║
║    GET /fear-greed           — Fear & Greed index + bias         ║
║    GET /earnings             — Next earnings + EPS estimates      ║
║    GET /signals/{ticker}     — RSI/SMA/EMA/MACD signal engine    ║
║    GET /insider-flow         — SEC Form 4 cluster buy scan       ║
║    GET /funding-rates        — Binance perp funding rates        ║
║    POST /alert-check         — Multi-ticker price alert monitor  ║
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
    title="mcprice API v4",
    description=(
        "Real-time stock & crypto prices. 20 endpoints. No API key required. "
        "Stocks via yfinance, crypto via Binance. "
        "Fear & Greed · Technical Signals · Insider Flow · Earnings · Funding Rates."
    ),
    version="4.0.0",
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
