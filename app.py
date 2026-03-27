#!/usr/bin/env python3

"""
╔══════════════════════════════════════════════════════════════════╗
║  mcprice v5.0                                                    ║
║  Real-Time Financial Intelligence MCP for Claude / Cursor        ║
║                                                                  ║
║  Stocks  → yfinance  (cloud-reliable, no raw HTTP blocks)        ║
║  Crypto  → Binance Public API + Futures (no key needed)          ║
║  Revolut → marks assets tradeable on Revolut                     ║
║  Insider → SEC EDGAR Form 4 via GitHub Actions                   ║
║                                                                  ║
║  v5.0 — Skills-to-MCP conversion (Awesome-Finance-Skills):       ║
║   ✅ stock_correlation      — co-movement, pairs, clustering      ║
║   ✅ options_analysis       — Black-Scholes payoff + Greeks       ║
║   ✅ geopolitical_energy_risk — Hormuz Monitor + oil signals      ║
║   ✅ stock_deep_data        — fundamentals, analysts, insiders    ║
║   ✅ options_chain          — live IV surface + OI + max pain     ║
║                                                                  ║
║  Tools (25 total):                                               ║
║   1.  get_price             — single stock/ETF price             ║
║   2.  get_prices_bulk       — up to 20 tickers at once           ║
║   3.  get_crypto_price      — Binance crypto price               ║
║   4.  price_snapshot        — mixed watchlist snapshot           ║
║   5.  revolut_price_check   — price + Revolut availability       ║
║   6.  crypto_top_movers     — Binance 24h gainers/losers         ║
║   7.  portfolio_pnl         — real-time P&L for holdings         ║
║   8.  market_overview       — indices + commodities + crypto     ║
║   9.  revolut_watchlist     — bulk Revolut check for watchlist   ║
║  10.  revolut_sector_scan   — sector scan + best Revolut pick    ║
║  11.  fear_greed_index      — Fear & Greed + trading bias        ║
║  12.  earnings_calendar     — next earnings + EPS estimates      ║
║  13.  technical_signals     — RSI/SMA/EMA/MACD signal engine     ║
║  14.  insider_flow_scan     — SEC Form 4 cluster buy detection   ║
║  15.  crypto_funding_rates  — Binance perp funding rates         ║
║  16.  price_alert_check     — multi-target alert monitor         ║
║  17.  financial_news        — live headlines (NewsNow, WallStrCN)║
║  18.  deepear_signals       — DeepEar Lite investment signals     ║
║  19.  prediction_markets    — Polymarket crowd probabilities      ║
║  20.  news_sentiment_score  — FinBERT-distilled text sentiment    ║
║  21.  stock_correlation     — co-move discovery + pair analysis  ║
║  22.  options_analysis      — BS payoff curves + Greeks (JSON)   ║
║  23.  geopolitical_energy_risk — Hormuz + oil trade signals      ║
║  24.  stock_deep_data       — fundamentals, analysts, dividends  ║
║  25.  options_chain         — live IV surface + OI + max pain    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import functools
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import List, Optional

import httpx
import yfinance as yf

# === FIX TzCache Error για Cloud Run / Railway ===
try:
    os.makedirs("/tmp/py-yfinance", exist_ok=True)
    yf.set_tz_cache_location("/tmp/py-yfinance")
    print("✅ yfinance TzCache set to /tmp/py-yfinance")
except Exception as e:
    print(f"⚠️  Could not set yfinance cache: {e}")
# ================================================

# === MCP Server Imports ===
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
# ==================================

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("mcprice")

# ─────────────────────────────────────────────────────────────────────────────
# SERVER
# ─────────────────────────────────────────────────────────────────────────────

mcp = FastMCP("mcprice")

# ─────────────────────────────────────────────────────────────────────────────
# HEALTH MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────────────

class HealthMiddleware(BaseHTTPMiddleware):
    """
    Intercepts health probes before they reach the MCP ASGI app.
      GET  /health → 200 {"status":"ok"}
      HEAD /health → 200 (empty body)
      HEAD /mcp    → 200 immediately (avoids 406 from streamable-http)
    """
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health" and request.method in ("GET", "HEAD"):
            body = b'{"status":"ok","service":"mcprice","version":"3.0"}'
            return Response(
                content=body if request.method == "GET" else b"",
                status_code=200,
                media_type="application/json",
            )
        if request.method == "HEAD" and request.url.path == "/mcp":
            return Response(status_code=200)
        return await call_next(request)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — load from JSON files, silent fallback to built-in defaults
# ─────────────────────────────────────────────────────────────────────────────

def _load_config() -> tuple[dict, set]:
    config_dir = Path(__file__).parent / "config"
    try:
        stocks = json.loads((config_dir / "revolut_stocks.json").read_text()).get("stocks", {})
        crypto = set(json.loads((config_dir / "revolut_crypto.json").read_text()).get("crypto", []))
        logger.info("Config loaded: %d stocks, %d crypto", len(stocks), len(crypto))
        return stocks, crypto
    except Exception as exc:
        logger.warning("Config load failed (%s) — using built-in defaults", exc)
        return _default_stocks(), _default_crypto()


def _default_stocks() -> dict:
    return {
        "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet A", "GOOG": "Alphabet C",
        "META": "Meta", "AMZN": "Amazon", "NVDA": "NVIDIA", "TSLA": "Tesla", "NFLX": "Netflix",
        "ADBE": "Adobe", "CRM": "Salesforce", "ORCL": "Oracle", "IBM": "IBM", "INTC": "Intel",
        "AMD": "AMD", "QCOM": "Qualcomm", "TXN": "Texas Instruments", "AVGO": "Broadcom",
        "MU": "Micron", "AMAT": "Applied Materials", "NOW": "ServiceNow", "INTU": "Intuit",
        "SNOW": "Snowflake", "UBER": "Uber", "SHOP": "Shopify", "SQ": "Block",
        "PYPL": "PayPal", "PLTR": "Palantir", "COIN": "Coinbase", "MSTR": "MicroStrategy",
        "JPM": "JPMorgan", "BAC": "Bank of America", "WFC": "Wells Fargo", "GS": "Goldman",
        "MS": "Morgan Stanley", "V": "Visa", "MA": "Mastercard", "AXP": "Amex",
        "BRKB": "Berkshire B", "BLK": "BlackRock", "SCHW": "Schwab",
        "JNJ": "J&J", "PFE": "Pfizer", "MRNA": "Moderna", "ABBV": "AbbVie",
        "LLY": "Eli Lilly", "MRK": "Merck", "AMGN": "Amgen", "GILD": "Gilead",
        "UNH": "UnitedHealth", "CVS": "CVS",
        "XOM": "ExxonMobil", "CVX": "Chevron", "COP": "ConocoPhillips", "OXY": "Occidental",
        "LMT": "Lockheed Martin", "RTX": "RTX/Raytheon", "BA": "Boeing", "GD": "General Dynamics",
        "NOC": "Northrop Grumman", "LHX": "L3Harris", "HII": "Huntington Ingalls",
        "KO": "Coca-Cola", "PEP": "PepsiCo", "MCD": "McDonald's", "SBUX": "Starbucks",
        "NKE": "Nike", "DIS": "Disney", "WMT": "Walmart", "COST": "Costco", "HD": "Home Depot",
        "T": "AT&T", "VZ": "Verizon", "CMCSA": "Comcast",
        "TSM": "TSMC ADR", "ASML": "ASML ADR", "LRCX": "Lam Research",
        "SPY": "S&P 500 ETF", "QQQ": "Nasdaq-100 ETF", "IWM": "Russell 2000 ETF",
        "DIA": "Dow Jones ETF", "GLD": "Gold ETF", "SLV": "Silver ETF",
        "TLT": "20yr Treasury ETF", "USO": "Oil ETF",
        "XLK": "Tech SPDR", "XLE": "Energy SPDR", "XLF": "Finance SPDR",
        "XLV": "Health SPDR", "XLI": "Industrial SPDR", "ITA": "Aerospace & Defense ETF",
        "ARKK": "ARK Innovation ETF", "VOO": "Vanguard S&P 500", "SOXX": "Semiconductor ETF",
        "DDOG": "Datadog", "NET": "Cloudflare", "CRWD": "CrowdStrike", "PANW": "Palo Alto",
        "ZS": "Zscaler", "FTNT": "Fortinet", "SNAP": "Snap", "PINS": "Pinterest",
        "ZM": "Zoom", "RBLX": "Roblox", "SPOT": "Spotify", "LYFT": "Lyft",
        "HUBS": "HubSpot", "TEAM": "Atlassian", "TWLO": "Twilio", "DOCU": "DocuSign",
        "OKTA": "Okta", "PATH": "UiPath", "U": "Unity", "AI": "C3.ai",
    }


def _default_crypto() -> set:
    return {
        "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "DOT", "AVAX", "MATIC", "LINK",
        "UNI", "ATOM", "LTC", "BCH", "XLM", "ALGO", "VET", "THETA", "FIL", "AAVE",
        "COMP", "SNX", "MKR", "SUSHI", "YFI", "BAT", "ZRX", "ENJ", "MANA", "SAND",
        "AXS", "CHZ", "GALA", "IMX", "APE", "NEAR", "FTM", "HBAR", "ICP", "ETC",
        "TRX", "EOS", "NEO", "DASH", "ZEC", "XMR", "QTUM", "ONT", "ZIL", "ICX",
        "BNB", "OP", "ARB", "SUI", "SEI", "TIA", "PYTH", "JUP",
    }


REVOLUT_STOCKS, REVOLUT_CRYPTO = _load_config()

# ─────────────────────────────────────────────────────────────────────────────
# ALL_CRYPTO — union of config + universal set  (replaces buggy KNOWN_CRYPTO)
#
# Problem with a small hardcoded KNOWN_CRYPTO:
#   - Misses coins that are on Binance but not in Revolut config
#     (e.g. TIA, PYTH, JUP, SEI, SUI, WLD, PEPE, FLOKI)
#   - Those coins get sent to yfinance → wrong data or error
#
# Fix: ALL_CRYPTO = REVOLUT_CRYPTO (from config) ∪ _UNIVERSAL_CRYPTO (hardcoded
#      top coins). Any ticker in this set is routed to Binance. Everything else
#      goes to yfinance. No coin is ever misrouted.
# ─────────────────────────────────────────────────────────────────────────────

_UNIVERSAL_CRYPTO: set = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "AVAX", "DOT", "MATIC",
    "LINK", "UNI", "ATOM", "LTC", "BCH", "XLM", "ALGO", "FIL", "AAVE", "COMP",
    "MKR", "SNX", "YFI", "SUSHI", "BAT", "ENJ", "MANA", "SAND", "AXS", "CHZ",
    "GALA", "IMX", "APE", "NEAR", "FTM", "HBAR", "ICP", "ETC", "TRX", "EOS",
    "NEO", "DASH", "ZEC", "XMR", "OP", "ARB", "SUI", "SEI", "TIA", "PYTH",
    "JUP", "WLD", "INJ", "BLUR", "PEPE", "FLOKI", "BONK", "SHIB", "TON",
}

ALL_CRYPTO: set = REVOLUT_CRYPTO | _UNIVERSAL_CRYPTO  # final routing set

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; mcprice/2.2; +https://github.com/gepappas98/mcprice)"
}

# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

_VALID_TICKER = re.compile(r"^[A-Z0-9\.\-\^]{1,12}$")


def validate_ticker(ticker: str) -> str:
    t = ticker.upper().strip()
    if not _VALID_TICKER.match(t):
        raise ValueError(
            f"Invalid ticker '{ticker}'. Use 1-12 uppercase letters/digits (e.g. AAPL, BTC, SPY)."
        )
    return t

# ─────────────────────────────────────────────────────────────────────────────
# TTL CACHE — stampede-safe with _in_flight deduplication
# ─────────────────────────────────────────────────────────────────────────────

_cache: dict     = {}
_in_flight: dict = {}


def ttl_cache(ttl: int = 30):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args):
            key = f"{func.__name__}:{args}"
            now = time.monotonic()
            if key in _cache:
                data, expiry = _cache[key]
                if now < expiry:
                    logger.debug("Cache HIT %s", key)
                    return data
            if key in _in_flight:
                logger.debug("Cache WAIT %s", key)
                await _in_flight[key].wait()
                if key in _cache:
                    return _cache[key][0]
            event = asyncio.Event()
            _in_flight[key] = event
            try:
                logger.debug("Cache MISS %s", key)
                result = await func(*args)
                _cache[key] = (result, now + ttl)
                return result
            finally:
                event.set()
                _in_flight.pop(key, None)
        return wrapper
    return decorator

# ─────────────────────────────────────────────────────────────────────────────
# RATE LIMITER — lazy init (avoids Python 3.12 event-loop crash at module level)
# ─────────────────────────────────────────────────────────────────────────────

_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(5)
    return _semaphore


async def limited_call(fn, *args):
    async with _get_semaphore():
        return await fn(*args)

# ─────────────────────────────────────────────────────────────────────────────
# RETRY — exponential backoff + 429 Retry-After support
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_with_retry(fn, *args, retries: int = 3, base_delay: float = 0.5):
    last_exc = Exception("unknown")
    for attempt in range(retries):
        try:
            return await fn(*args)
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code == 429:
                wait = min(float(exc.response.headers.get("Retry-After", 5)), 60.0)
                logger.warning("429 rate-limit on %s — waiting %.1fs", getattr(fn, "__name__", "?"), wait)
                await asyncio.sleep(wait)
                continue
            if attempt < retries - 1:
                wait = base_delay * (2 ** attempt)
                logger.warning("Retry %d/%d %s — %s (%.1fs)", attempt + 1, retries, getattr(fn, "__name__", "?"), exc, wait)
                await asyncio.sleep(wait)
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                wait = base_delay * (2 ** attempt)
                logger.warning("Retry %d/%d %s — %s (%.1fs)", attempt + 1, retries, getattr(fn, "__name__", "?"), exc, wait)
                await asyncio.sleep(wait)
    raise last_exc

# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER — yfinance  (more reliable on cloud IPs than raw Yahoo HTTP)
# ─────────────────────────────────────────────────────────────────────────────

@ttl_cache(ttl=30)
async def _yfinance_quote(ticker: str) -> dict:
    logger.info("yfinance fetch: %s", ticker)

    def _sync():
        t    = yf.Ticker(ticker)
        info = t.fast_info
        price   = float(info.last_price or 0)
        prev    = float(info.previous_close or price)
        change  = price - prev
        chg_pct = (change / prev * 100) if prev else 0.0
        return {
            "ticker":     ticker,
            "name":       getattr(info, "display_name", None) or ticker,
            "price":      round(price, 4),
            "change":     round(change, 4),
            "change_pct": round(chg_pct, 2),
            "volume":     int(getattr(info, "three_month_average_volume", 0) or 0),
            "market_cap": getattr(info, "market_cap", None),
            "currency":   getattr(info, "currency", "USD"),
            "source":     "yfinance",
        }

    return await asyncio.get_running_loop().run_in_executor(None, _sync)

# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER — Binance
# ─────────────────────────────────────────────────────────────────────────────

@ttl_cache(ttl=10)
async def _binance_ticker(symbol: str) -> dict:
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym += "USDT"
    logger.info("Binance fetch: %s", sym)
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get("https://api.binance.com/api/v3/ticker/24hr", params={"symbol": sym})
        r.raise_for_status()
        d    = r.json()
        base = sym.replace("USDT", "")
        return {
            "ticker":         base,
            "pair":           sym,
            "price":          round(float(d["lastPrice"]), 6),
            "change":         round(float(d["priceChange"]), 6),
            "change_pct":     round(float(d["priceChangePercent"]), 2),
            "high_24h":       round(float(d["highPrice"]), 6),
            "low_24h":        round(float(d["lowPrice"]), 6),
            "volume_usd_24h": round(float(d["quoteVolume"]), 0),
            "currency":       "USDT",
            "source":         "Binance",
            "revolut_crypto": base in REVOLUT_CRYPTO,
        }

# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK yfinance → Binance
# ─────────────────────────────────────────────────────────────────────────────

async def _get_stock_price(ticker: str) -> dict:
    try:
        return await fetch_with_retry(limited_call, _yfinance_quote, ticker)
    except Exception as exc:
        logger.warning("yfinance failed %s (%s) — Binance fallback", ticker, exc)
        try:
            return await fetch_with_retry(limited_call, _binance_ticker, ticker)
        except Exception as exc2:
            logger.error("All providers failed %s: %s", ticker, exc2)
            return {"ticker": ticker, "error": str(exc2), "source": "all providers failed"}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _arrow(chg: float) -> str:
    if chg > 2:  return "🚀"
    if chg > 0:  return "📈"
    if chg < -2: return "🔻"
    if chg < 0:  return "📉"
    return "➡️"


def _enrich_stock(q: dict) -> dict:
    t  = q.get("ticker", "")
    cp = q.get("change_pct", 0)
    q["revolut_available"] = t in REVOLUT_STOCKS
    if t in REVOLUT_STOCKS:
        q["revolut_name"] = REVOLUT_STOCKS[t]
    q["emoji"]   = _arrow(cp)
    q["summary"] = (
        f"{q['emoji']} {t}: ${q.get('price','?')} ({cp:+.2f}%)"
        + (" 💳 Revolut" if q["revolut_available"] else "")
    )
    return q


def _enrich_crypto(q: dict) -> dict:
    cp = q.get("change_pct", 0)
    q["emoji"]             = _arrow(cp)
    q["revolut_available"] = q.get("revolut_crypto", False)
    q["summary"] = (
        f"{q['emoji']} {q['ticker']}: ${q.get('price','?')} ({cp:+.2f}%)"
        + (" 💳 Revolut" if q["revolut_available"] else "")
    )
    return q

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1 — get_price
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_price(ticker: str) -> dict:
    """
    Current price for one stock or ETF.
    Source: yfinance (30s cache). Falls back to Binance on failure.

    Args:
        ticker: Symbol e.g. "NVDA", "SPY", "LMT"
    """
    try:
        ticker = validate_ticker(ticker)
    except ValueError as e:
        return {"error": str(e)}
    q = await _get_stock_price(ticker)
    return _enrich_stock(q) if q else {"ticker": ticker, "error": "No data"}

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2 — get_prices_bulk
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_prices_bulk(tickers: List[str]) -> dict:
    """
    Prices for multiple stocks/ETFs at once (max 20).

    Args:
        tickers: e.g. ["NVDA", "LMT", "GLD", "SPY"]
    """
    validated, errors = [], []
    for t in tickers[:20]:
        try:
            validated.append(validate_ticker(t))
        except ValueError as e:
            errors.append({"ticker": t, "error": str(e)})
    quotes  = await asyncio.gather(*[_get_stock_price(t) for t in validated])
    results = [_enrich_stock(q) for q in quotes if q]
    valid   = [r for r in results if "error" not in r]
    return {
        "count":   len(results),
        "results": results,
        "errors":  errors,
        "gainers": sorted(valid, key=lambda x: x.get("change_pct", 0), reverse=True)[:3],
        "losers":  sorted(valid, key=lambda x: x.get("change_pct", 0))[:3],
    }

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3 — get_crypto_price
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_crypto_price(symbol: str) -> dict:
    """
    Crypto price from Binance Public API (10s cache).

    Args:
        symbol: e.g. "BTC", "ETH", "SOL" (no USDT suffix needed)
    """
    try:
        symbol = validate_ticker(symbol.replace("USDT", "").replace("/", ""))
    except ValueError as e:
        return {"error": str(e)}
    try:
        result = await fetch_with_retry(limited_call, _binance_ticker, symbol)
        return _enrich_crypto(result)
    except Exception as exc:
        logger.error("Binance failed %s: %s", symbol, exc)
        return {"ticker": symbol, "error": str(exc)}

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 4 — price_snapshot
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def price_snapshot(tickers: Optional[List[str]] = None) -> dict:
    """
    Rich snapshot for a mixed watchlist (stocks + crypto).
    Uses default watchlist if no tickers provided.
    """
    DEFAULT_STOCKS = ["NVDA", "AAPL", "MSFT", "TSLA", "LMT", "RTX", "GLD", "SPY", "META", "AMZN"]
    DEFAULT_CRYPTO = ["BTC", "ETH", "SOL", "XRP", "DOGE"]

    if tickers:
        upper       = [t.upper().strip() for t in tickers[:25]]
        crypto_list = [t for t in upper if t in ALL_CRYPTO]   # ALL_CRYPTO — no misrouting
        stock_list  = [t for t in upper if t not in ALL_CRYPTO]
    else:
        stock_list, crypto_list = DEFAULT_STOCKS, DEFAULT_CRYPTO

    stock_res, crypto_res = await asyncio.gather(
        asyncio.gather(*[_get_stock_price(t) for t in stock_list],  return_exceptions=True),
        asyncio.gather(*[fetch_with_retry(limited_call, _binance_ticker, t) for t in crypto_list], return_exceptions=True),
    )

    stocks_out = [_enrich_stock(q)  for q in stock_res  if isinstance(q, dict) and "error" not in q]
    crypto_out = [_enrich_crypto(q) for q in crypto_res if isinstance(q, dict) and "error" not in q]

    all_valid  = stocks_out + crypto_out
    avg_chg    = sum(x.get("change_pct", 0) for x in all_valid) / len(all_valid) if all_valid else 0
    top_gainer = max(all_valid, key=lambda x: x.get("change_pct", 0), default=None)
    top_loser  = min(all_valid, key=lambda x: x.get("change_pct", 0), default=None)

    return {
        "stocks": stocks_out,
        "crypto": crypto_out,
        "summary": {
            "total_assets":   len(all_valid),
            "avg_change_pct": round(avg_chg, 2),
            "market_mood":    "🟢 Risk-On" if avg_chg > 0 else "🔴 Risk-Off",
            "top_gainer":     {"ticker": top_gainer["ticker"], "change_pct": top_gainer.get("change_pct")} if top_gainer else None,
            "top_loser":      {"ticker": top_loser["ticker"],  "change_pct": top_loser.get("change_pct")}  if top_loser  else None,
        },
    }

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 5 — revolut_price_check
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def revolut_price_check(ticker: str) -> dict:
    """
    Is this stock/ETF on Revolut? + current live price.

    Args:
        ticker: Stock or ETF symbol e.g. "LMT", "GLD", "ITA"
    """
    try:
        ticker = validate_ticker(ticker)
    except ValueError as e:
        return {"error": str(e)}

    quote  = await _get_stock_price(ticker)
    on_rev = ticker in REVOLUT_STOCKS

    if not quote or "error" in quote:
        return {
            "ticker": ticker, "revolut_available": on_rev, "price": None,
            "quick_verdict": f"{'✅' if on_rev else '❌'} {ticker} {'on Revolut' if on_rev else 'NOT on Revolut'} — price unavailable",
        }

    cp   = quote.get("change_pct", 0)
    name = REVOLUT_STOCKS.get(ticker, quote.get("name", ticker))
    return {
        "ticker":            ticker,
        "name":              name,
        "revolut_available": on_rev,
        "price":             quote["price"],
        "change_pct":        cp,
        "volume":            quote.get("volume"),
        "currency":          quote.get("currency", "USD"),
        "emoji":             _arrow(cp),
        "quick_verdict": (
            f"{'✅ 💳' if on_rev else '❌'} {ticker} ({name}): ${quote['price']} ({cp:+.2f}%) "
            + ("— available on Revolut 💳" if on_rev else "— NOT on Revolut")
        ),
    }

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 6 — crypto_top_movers
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def crypto_top_movers(limit: int = 10, min_volume_usd: float = 10_000_000) -> dict:
    """
    Top crypto gainers & losers over 24h from Binance (no API key).

    Args:
        limit: Results per category (default 10)
        min_volume_usd: Minimum 24h USD volume filter (default $10M)
    """
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://api.binance.com/api/v3/ticker/24hr")
            r.raise_for_status()
            all_tickers = r.json()
    except Exception as exc:
        return {"error": "Binance connection failed", "details": str(exc)}

    filtered = []
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        vol = float(t.get("quoteVolume", 0))
        if vol < min_volume_usd:
            continue
        base = sym[:-4]
        chg  = float(t.get("priceChangePercent", 0))
        filtered.append({
            "ticker": base, "price": round(float(t["lastPrice"]), 6),
            "change_pct": round(chg, 2), "volume_usd_24h": round(vol, 0),
            "revolut": base in REVOLUT_CRYPTO, "emoji": _arrow(chg),
        })

    return {
        "gainers": sorted(filtered, key=lambda x: x["change_pct"], reverse=True)[:limit],
        "losers":  sorted(filtered, key=lambda x: x["change_pct"])[:limit],
        "revolut_movers": [x for x in sorted(filtered, key=lambda x: abs(x["change_pct"]), reverse=True) if x["revolut"]][:limit],
        "total_pairs_scanned": len(filtered),
    }

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 7 — portfolio_pnl
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def portfolio_pnl(holdings: List[dict]) -> dict:
    """
    Real-time P&L calculator for a portfolio of stocks and/or crypto.
    Returns current value, profit/loss per asset, Revolut availability,
    best/worst performer, and portfolio summary.

    Args:
        holdings: List of dicts, e.g.:
            [
              {"ticker": "NVDA", "qty": 10,  "avg_price": 800.0},
              {"ticker": "BTC",  "qty": 0.5, "avg_price": 40000.0},
              {"ticker": "LMT",  "qty": 5,   "avg_price": 450.0}
            ]
    """
    if not holdings:
        return {"error": "No holdings provided"}

    results = []
    total_cost = total_current = 0.0

    for h in holdings[:30]:
        raw = h.get("ticker", "")
        qty = float(h.get("qty", 0))
        avg = float(h.get("avg_price", 0))
        try:
            ticker = validate_ticker(raw)
        except ValueError as e:
            results.append({"ticker": raw, "error": str(e)})
            continue

        try:
            q = await (fetch_with_retry(limited_call, _binance_ticker, ticker)
                       if ticker in ALL_CRYPTO else _get_stock_price(ticker))
        except Exception as exc:
            results.append({"ticker": ticker, "qty": qty, "avg_price": avg, "error": str(exc)})
            continue

        if not q or "error" in q:
            results.append({"ticker": ticker, "qty": qty, "avg_price": avg, "error": "Price unavailable"})
            continue

        cur   = float(q.get("price", 0))
        cost  = qty * avg
        val   = qty * cur
        pnl   = val - cost
        ppct  = (pnl / cost * 100) if cost else 0.0
        on_r  = ticker in REVOLUT_STOCKS or ticker in REVOLUT_CRYPTO

        total_cost    += cost
        total_current += val

        results.append({
            "ticker": ticker, "qty": qty, "avg_price": avg,
            "current_price": cur,
            "cost_basis":    round(cost, 2),
            "current_value": round(val,  2),
            "pnl":           round(pnl,  2),
            "pnl_pct":       round(ppct, 2),
            "revolut_available": on_r,
            "emoji": _arrow(ppct),
            "summary": (
                f"{_arrow(ppct)} {ticker}: ${cur} × {qty} = ${round(val,2)} "
                f"({round(pnl,2):+.2f} / {round(ppct,2):+.2f}%)"
                + (" 💳" if on_r else "")
            ),
        })

    tpnl  = total_current - total_cost
    tpct  = (tpnl / total_cost * 100) if total_cost else 0.0
    valid = [r for r in results if "error" not in r]

    return {
        "holdings": results,
        "portfolio_summary": {
            "total_cost":       round(total_cost, 2),
            "total_current":    round(total_current, 2),
            "total_pnl":        round(tpnl, 2),
            "total_pnl_pct":    round(tpct, 2),
            "portfolio_mood":   "🟢 In profit" if tpnl >= 0 else "🔴 In loss",
            "best_performer":   max(valid, key=lambda x: x.get("pnl_pct", 0), default=None),
            "worst_performer":  min(valid, key=lambda x: x.get("pnl_pct", 0), default=None),
            "on_revolut_count": sum(1 for r in valid if r.get("revolut_available")),
        },
    }

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 8 — market_overview
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def market_overview() -> dict:
    """
    Full market dashboard — no arguments needed. Perfect for morning briefing.

    Indices:     SPY (S&P 500), QQQ (Nasdaq), DIA (Dow), IWM (Russell 2000)
    Commodities: GLD (Gold), SLV (Silver), USO (Oil), TLT (Bonds)
    Crypto:      BTC, ETH, SOL, BNB
    """
    INDICES     = ["SPY", "QQQ", "DIA", "IWM"]
    COMMODITIES = ["GLD", "SLV", "USO", "TLT"]
    CRYPTO_LIST = ["BTC", "ETH", "SOL", "BNB"]

    ir, cr, xr = await asyncio.gather(
        asyncio.gather(*[_get_stock_price(t) for t in INDICES],     return_exceptions=True),
        asyncio.gather(*[_get_stock_price(t) for t in COMMODITIES], return_exceptions=True),
        asyncio.gather(*[fetch_with_retry(limited_call, _binance_ticker, t) for t in CRYPTO_LIST], return_exceptions=True),
    )

    indices_out     = [_enrich_stock(q)  for q in ir if isinstance(q, dict) and "error" not in q]
    commodities_out = [_enrich_stock(q)  for q in cr if isinstance(q, dict) and "error" not in q]
    crypto_out      = [_enrich_crypto(q) for q in xr if isinstance(q, dict) and "error" not in q]

    all_valid = indices_out + commodities_out + crypto_out
    avg_chg   = sum(x.get("change_pct", 0) for x in all_valid) / len(all_valid) if all_valid else 0
    spy_chg   = next((x.get("change_pct", 0) for x in indices_out if x["ticker"] == "SPY"), 0)
    btc_chg   = next((x.get("change_pct", 0) for x in crypto_out  if x["ticker"] == "BTC"), 0)

    if   spy_chg > 0 and btc_chg > 0: mood = "🟢 Risk-On — Equities & Crypto both up"
    elif spy_chg < 0 and btc_chg < 0: mood = "🔴 Risk-Off — Equities & Crypto both down"
    elif spy_chg > 0 and btc_chg < 0: mood = "🟡 Mixed — Equities up, Crypto down"
    elif spy_chg < 0 and btc_chg > 0: mood = "🟡 Mixed — Crypto up, Equities down"
    else:                              mood = "➡️ Neutral"

    return {
        "indices":     indices_out,
        "commodities": commodities_out,
        "crypto":      crypto_out,
        "overview": {
            "avg_change_pct": round(avg_chg, 2),
            "market_mood":    mood,
            "spy_change":     f"{spy_chg:+.2f}%",
            "btc_change":     f"{btc_chg:+.2f}%",
            "timestamp":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 9 — revolut_watchlist
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def revolut_watchlist(tickers: List[str]) -> dict:
    """
    Bulk Revolut availability check + live prices for a mixed stock/crypto watchlist.
    Splits results into: available on Revolut vs not available.
    Perfect for portfolio screening before opening a position.

    Args:
        tickers: Mixed list e.g. ["NVDA", "BTC", "LMT", "SOL", "ARKK"]
    """
    validated, errors = [], []
    for t in tickers[:30]:
        try:
            validated.append(validate_ticker(t))
        except ValueError as e:
            errors.append({"ticker": t, "error": str(e)})

    crypto_list = [t for t in validated if t in ALL_CRYPTO]
    stock_list  = [t for t in validated if t not in ALL_CRYPTO]

    sq, cq = await asyncio.gather(
        asyncio.gather(*[_get_stock_price(t) for t in stock_list],  return_exceptions=True),
        asyncio.gather(*[fetch_with_retry(limited_call, _binance_ticker, t) for t in crypto_list], return_exceptions=True),
    )

    all_results = (
        [_enrich_stock(q)  for q in sq if isinstance(q, dict) and "error" not in q] +
        [_enrich_crypto(q) for q in cq if isinstance(q, dict) and "error" not in q]
    )

    on_revolut  = [x for x in all_results if x.get("revolut_available")]
    off_revolut = [x for x in all_results if not x.get("revolut_available")]

    return {
        "total_checked":     len(all_results),
        "on_revolut_count":  len(on_revolut),
        "off_revolut_count": len(off_revolut),
        "on_revolut":        on_revolut,
        "off_revolut":       off_revolut,
        "errors":            errors,
        "verdict": (
            f"💳 {len(on_revolut)}/{len(all_results)} assets available on Revolut. "
            + (f"Not tradeable: {', '.join(x['ticker'] for x in off_revolut)}" if off_revolut else "All assets tradeable on Revolut! ✅")
        ),
    }

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 10 — revolut_sector_scan
# ─────────────────────────────────────────────────────────────────────────────

SECTORS: dict = {
    "tech":    ["NVDA", "AAPL", "MSFT", "META", "GOOGL", "AMD", "INTC", "AVGO", "TSM", "ASML"],
    "defense": ["LMT", "RTX", "BA", "GD", "NOC", "LHX", "HII", "ITA"],
    "crypto":  ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "AVAX", "ADA"],
    "energy":  ["XOM", "CVX", "COP", "OXY", "XLE"],
    "finance": ["JPM", "BAC", "GS", "MS", "V", "MA", "BLK", "SCHW"],
    "health":  ["JNJ", "PFE", "MRNA", "LLY", "UNH", "ABBV", "MRK", "AMGN"],
    "etf":     ["SPY", "QQQ", "GLD", "IWM", "TLT", "SOXX", "ARKK", "VOO", "ITA"],
    "ai":      ["NVDA", "MSFT", "GOOGL", "META", "PLTR", "AI", "SNOW", "NOW", "DDOG"],
}


@mcp.tool()
async def revolut_sector_scan(sector: str) -> dict:
    """
    Scan an entire market sector — live prices + Revolut availability for all tickers.
    Returns the best Revolut-tradeable pick of the day in that sector.

    Args:
        sector: One of: tech, defense, crypto, energy, finance, health, etf, ai
    """
    sector = sector.lower().strip()
    if sector not in SECTORS:
        return {"error": f"Unknown sector '{sector}'", "available_sectors": list(SECTORS.keys())}

    tickers = SECTORS[sector]
    is_crypto_sector = sector == "crypto"

    if is_crypto_sector:
        quotes = await asyncio.gather(
            *[fetch_with_retry(limited_call, _binance_ticker, t) for t in tickers],
            return_exceptions=True,
        )
        results = [_enrich_crypto(q) for q in quotes if isinstance(q, dict) and "error" not in q]
    else:
        quotes = await asyncio.gather(
            *[_get_stock_price(t) for t in tickers],
            return_exceptions=True,
        )
        results = [_enrich_stock(q) for q in quotes if isinstance(q, dict) and "error" not in q]

    valid      = [r for r in results if "error" not in r]
    on_revolut = [r for r in valid if r.get("revolut_available")]
    best       = max(on_revolut, key=lambda x: x.get("change_pct", 0), default=None)

    return {
        "sector":             sector,
        "total_scanned":      len(valid),
        "on_revolut_count":   len(on_revolut),
        "results":            sorted(valid, key=lambda x: x.get("change_pct", 0), reverse=True),
        "revolut_picks":      on_revolut,
        "best_revolut_today": best,
        "sector_avg_change":  round(sum(x.get("change_pct", 0) for x in valid) / len(valid), 2) if valid else 0,
        "verdict": (
            f"📊 {sector.upper()}: {len(on_revolut)}/{len(valid)} on Revolut. "
            + (f"Best today: {best['ticker']} ({best.get('change_pct',0):+.2f}%) 💳" if best else "No Revolut picks found.")
        ),
    }

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 11 — fear_greed_index
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def fear_greed_index() -> dict:
    """
    Current & historical Fear & Greed Index from alternative.me (no API key).
    Returns today's score, yesterday, last week, last month + trading bias signal.
    Perfect for timing entries/exits. Works for both crypto and stock markets.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://api.alternative.me/fng/",
                params={"limit": 5, "format": "json"},
            )
            r.raise_for_status()
            data = r.json().get("data", [])
    except Exception as exc:
        return {"error": f"Fear & Greed API failed: {exc}"}

    if not data:
        return {"error": "No data returned"}

    def _classify(score: int) -> str:
        if score <= 25:  return "😱 Extreme Fear"
        if score <= 40:  return "😨 Fear"
        if score <= 55:  return "😐 Neutral"
        if score <= 75:  return "😄 Greed"
        return "🤑 Extreme Greed"

    def _bias(score: int) -> str:
        if score <= 25:  return "🟢 Strong BUY signal — market oversold, historically best entry"
        if score <= 40:  return "🟡 Cautious BUY — fear creating opportunity"
        if score <= 55:  return "⚪ HOLD — neutral market, no clear edge"
        if score <= 75:  return "🟡 Consider TRIM — greed elevated, risk increasing"
        return "🔴 SELL / avoid new longs — extreme greed = near-term top risk"

    current = data[0]
    score   = int(current["value"])
    labels  = ["Today", "Yesterday", "Last Week", "2 Weeks Ago", "Last Month"]

    history = [
        {
            "period":    labels[i],
            "score":     int(d["value"]),
            "label":     d["value_classification"],
            "sentiment": _classify(int(d["value"])),
        }
        for i, d in enumerate(data[:5])
    ]

    return {
        "current_score":   score,
        "current_label":   current["value_classification"],
        "sentiment":       _classify(score),
        "trading_bias":    _bias(score),
        "history":         history,
        "revolut_tip": (
            "💳 Revolut Tip: Use Fear & Greed below 25 to buy blue-chip Revolut stocks "
            "(NVDA, AAPL, MSFT) at discounted prices. Above 75 = reduce exposure."
        ),
        "source": "alternative.me/fng",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 12 — earnings_calendar
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def earnings_calendar(tickers: List[str]) -> dict:
    """
    Next earnings date + EPS estimates for a list of stocks.
    High-impact tool: earnings = biggest single-day price movers.
    Perfect for pre-earnings plays on Revolut.

    Args:
        tickers: e.g. ["NVDA", "AAPL", "MSFT", "META"]
    """
    if not tickers:
        return {"error": "Provide at least one ticker"}

    results = []

    def _fetch_earnings(ticker: str) -> dict:
        try:
            t    = yf.Ticker(ticker)
            cal  = t.calendar  # dict with Earnings Date, EPS Estimate, etc.
            info = t.fast_info

            earnings_date = None
            if cal is not None:
                if hasattr(cal, "get"):
                    ed = cal.get("Earnings Date") or cal.get("earningsDate")
                    if ed is not None:
                        if hasattr(ed, "__iter__") and not isinstance(ed, str):
                            ed = list(ed)
                            earnings_date = str(ed[0])[:10] if ed else None
                        else:
                            earnings_date = str(ed)[:10]

            eps_est  = None
            rev_est  = None
            if cal is not None and hasattr(cal, "get"):
                eps_est = cal.get("EPS Estimate") or cal.get("epsEstimate")
                rev_est = cal.get("Revenue Estimate") or cal.get("revenueEstimate")
                if eps_est is not None:
                    try: eps_est = round(float(eps_est), 4)
                    except: eps_est = None
                if rev_est is not None:
                    try: rev_est = float(rev_est)
                    except: rev_est = None

            on_revolut = ticker in REVOLUT_STOCKS
            price      = round(float(info.last_price or 0), 2)

            return {
                "ticker":          ticker,
                "price":           price,
                "earnings_date":   earnings_date or "Not scheduled / unavailable",
                "eps_estimate":    eps_est,
                "revenue_estimate": rev_est,
                "revolut_available": on_revolut,
                "revolut_tip": (
                    f"💳 {ticker} is tradeable on Revolut — set a price alert before earnings!"
                    if on_revolut else
                    f"❌ {ticker} not on Revolut — consider comparable Revolut alternatives"
                ),
            }
        except Exception as exc:
            return {"ticker": ticker, "error": str(exc)}

    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, _fetch_earnings, t.upper().strip())
        for t in tickers[:15]
    ]
    results = await asyncio.gather(*tasks)

    upcoming = [
        r for r in results
        if "error" not in r
        and r["earnings_date"] not in ("Not scheduled / unavailable", None)
        and r["earnings_date"] >= time.strftime("%Y-%m-%d")
    ]
    upcoming_sorted = sorted(upcoming, key=lambda x: x["earnings_date"])
    on_revolut_upcoming = [r for r in upcoming_sorted if r.get("revolut_available")]

    return {
        "results":              list(results),
        "upcoming_sorted":      upcoming_sorted,
        "revolut_opportunities": on_revolut_upcoming,
        "summary": (
            f"📅 {len(upcoming_sorted)} upcoming earnings found. "
            f"💳 {len(on_revolut_upcoming)} tradeable on Revolut."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 13 — technical_signals
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def technical_signals(ticker: str, period: str = "3mo") -> dict:
    """
    RSI, SMA20, SMA50, EMA9 + buy/sell signal for any stock or ETF.
    Uses yfinance historical data — no API key needed.
    Great for timing entries on Revolut stocks.

    Args:
        ticker: Stock symbol e.g. "NVDA", "AAPL", "SPY"
        period: History window — "1mo", "3mo", "6mo", "1y" (default "3mo")
    """
    try:
        ticker = validate_ticker(ticker)
    except ValueError as e:
        return {"error": str(e)}

    def _calc(t: str, p: str) -> dict:
        import pandas as pd
        tk   = yf.Ticker(t)
        hist = tk.history(period=p)
        if hist.empty or len(hist) < 20:
            return {"ticker": t, "error": "Insufficient historical data"}

        close = hist["Close"]
        n     = len(close)

        # SMA
        sma20 = round(close.rolling(20).mean().iloc[-1], 2)
        sma50 = round(close.rolling(min(50, n)).mean().iloc[-1], 2)

        # EMA 9
        ema9  = round(close.ewm(span=9, adjust=False).mean().iloc[-1], 2)

        # RSI 14
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, float("nan"))
        rsi   = round(100 - (100 / (1 + rs.iloc[-1])), 1)

        # MACD (12,26,9)
        ema12   = close.ewm(span=12, adjust=False).mean()
        ema26   = close.ewm(span=26, adjust=False).mean()
        macd    = ema12 - ema26
        signal  = macd.ewm(span=9, adjust=False).mean()
        macd_v  = round(macd.iloc[-1], 4)
        sig_v   = round(signal.iloc[-1], 4)
        macd_cross = "🟢 Bullish crossover" if macd_v > sig_v else "🔴 Bearish crossover"

        cur = round(float(close.iloc[-1]), 2)

        # Signal logic
        signals = []
        if rsi < 30:    signals.append("🟢 RSI oversold (<30) — BUY signal")
        elif rsi > 70:  signals.append("🔴 RSI overbought (>70) — SELL signal")
        else:           signals.append(f"⚪ RSI neutral ({rsi})")

        if cur > sma20: signals.append("🟢 Price above SMA20 — bullish")
        else:           signals.append("🔴 Price below SMA20 — bearish")

        if sma20 > sma50: signals.append("🟢 SMA20 > SMA50 — golden cross zone")
        else:             signals.append("🔴 SMA20 < SMA50 — death cross zone")

        if cur > ema9: signals.append("🟢 Price above EMA9 — short-term momentum up")
        else:          signals.append("🔴 Price below EMA9 — short-term momentum down")

        bull_signals = sum(1 for s in signals if s.startswith("🟢"))
        overall = (
            "🟢 STRONG BUY"  if bull_signals >= 4 else
            "🟡 MILD BUY"    if bull_signals == 3 else
            "⚪ NEUTRAL"     if bull_signals == 2 else
            "🟡 MILD SELL"   if bull_signals == 1 else
            "🔴 STRONG SELL"
        )

        on_revolut = t in REVOLUT_STOCKS
        return {
            "ticker":      t,
            "current_price": cur,
            "period":      p,
            "rsi_14":      rsi,
            "sma_20":      sma20,
            "sma_50":      sma50,
            "ema_9":       ema9,
            "macd":        macd_v,
            "macd_signal": sig_v,
            "macd_cross":  macd_cross,
            "signals":     signals,
            "overall_signal": overall,
            "revolut_available": on_revolut,
            "revolut_action": (
                f"💳 {t} is on Revolut — {overall.split(' ', 1)[-1].lower()} signal active. Trade now!"
                if on_revolut else
                f"❌ {t} not on Revolut"
            ),
        }

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _calc, ticker, period)
        return result
    except Exception as exc:
        return {"ticker": ticker, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 14 — insider_flow_scan
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def insider_flow_scan(tickers: Optional[List[str]] = None) -> dict:
    """
    Recent SEC Form 4 insider buying/selling for stocks — fetched live from GitHub.
    Identifies cluster buys (multiple insiders buying = strong bullish signal).
    Flags which stocks are also on Revolut for immediate trading.
    Data updates every 2 hours via GitHub Actions.

    Args:
        tickers: Optional filter e.g. ["NVDA", "AAPL"]. Leave empty for all recent filings.
    """
    DATA_URL = (
        "https://raw.githubusercontent.com/gepappas98/revolut-pulse/main/public/insider-data.json"
    )
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(DATA_URL)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return {"error": f"Insider data unavailable: {exc}", "fallback": "Try again in 2 minutes"}

    filings = data.get("filings", [])
    if not filings:
        return {"error": "No filings in dataset"}

    # Filter by tickers if provided
    if tickers:
        upper_tickers = [t.upper().strip() for t in tickers]
        filings = [f for f in filings if f.get("ticker") in upper_tickers]

    buys  = [f for f in filings if f.get("isBuy")]
    sells = [f for f in filings if not f.get("isBuy")]

    # Cluster detection (≥3 insiders buying same ticker)
    from collections import Counter
    ticker_counts = Counter(f["ticker"] for f in buys)
    clusters = [
        {"ticker": t, "buy_count": c, "revolut": t in REVOLUT_STOCKS}
        for t, c in ticker_counts.most_common(10)
        if c >= 2
    ]

    # Top buys by value
    top_buys = sorted(buys, key=lambda x: x.get("value", 0), reverse=True)[:10]
    revolut_buys = [f for f in top_buys if f.get("ticker") in REVOLUT_STOCKS]

    # Enrich with Revolut flag
    for f in top_buys:
        f["revolut_available"] = f.get("ticker") in REVOLUT_STOCKS
        f["value_fmt"] = (
            f"${f['value']/1e6:.2f}M" if f.get("value", 0) >= 1_000_000
            else f"${f.get('value', 0)/1000:.0f}K"
        )

    return {
        "source":        "SEC EDGAR via GitHub Actions",
        "fetched_at":    data.get("fetchedAt", "unknown"),
        "total_filings": len(filings),
        "total_buys":    len(buys),
        "total_sells":   len(sells),
        "buy_sell_ratio": round(len(buys) / max(len(sells), 1), 2),
        "cluster_buys":  clusters,
        "top_buys":      top_buys,
        "revolut_actionable": revolut_buys,
        "market_signal": (
            "🟢 BULLISH — insiders buying heavily"  if len(buys) > len(sells) * 1.5 else
            "🔴 BEARISH — insiders selling"         if len(sells) > len(buys) * 1.5 else
            "⚪ NEUTRAL — mixed insider activity"
        ),
        "revolut_tip": (
            f"💳 {len(revolut_buys)} insider buys are tradeable on Revolut right now. "
            "Open revolut-pulse.lovable.app/insiderflow-pro-v2.html for the full screener."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 15 — crypto_funding_rates
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def crypto_funding_rates(symbols: Optional[List[str]] = None) -> dict:
    """
    Binance perpetual futures funding rates — free, no API key.
    Positive rate = longs paying shorts (bearish bias).
    Negative rate = shorts paying longs (bullish bias).
    Best contrarian signal in crypto trading.

    Args:
        symbols: e.g. ["BTC", "ETH", "SOL"]. Leave empty for top 15 by rate.
    """
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get("https://fapi.binance.com/fapi/v1/fundingRate",
                           params={"limit": 200})
            r.raise_for_status()
            raw = r.json()
    except Exception as exc:
        # fallback to premium endpoint
        try:
            async with httpx.AsyncClient(timeout=12) as c:
                r = await c.get("https://fapi.binance.com/fapi/v1/premiumIndex")
                r.raise_for_status()
                raw_idx = r.json()
                raw = [{"symbol": x["symbol"],
                        "fundingRate": x.get("lastFundingRate", "0"),
                        "fundingTime": x.get("nextFundingTime", 0)}
                       for x in raw_idx]
        except Exception as exc2:
            return {"error": f"Binance futures API failed: {exc2}"}

    processed = []
    seen = set()
    for item in raw:
        sym = item.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        base = sym[:-4]
        if base in seen:
            continue
        seen.add(base)
        rate = float(item.get("fundingRate", 0)) * 100  # to %
        processed.append({
            "symbol":       base,
            "rate_pct":     round(rate, 4),
            "annualized":   round(rate * 3 * 365, 1),  # 8h funding × 3/day × 365
            "bias":         "🔴 Bearish (longs paying)" if rate > 0 else "🟢 Bullish (shorts paying)",
            "signal": (
                "⚠️ EXTREME LONG SQUEEZE risk" if rate > 0.1 else
                "🔴 Crowded longs — caution"   if rate > 0.05 else
                "⚪ Neutral"                    if abs(rate) < 0.01 else
                "🟡 Mild short bias"            if rate < -0.01 else
                "🟢 Crowded shorts — contrarian BUY"
            ),
            "revolut_crypto": base in REVOLUT_CRYPTO,
        })

    if symbols:
        upper = [s.upper().strip() for s in symbols]
        processed = [p for p in processed if p["symbol"] in upper]
        processed = sorted(processed, key=lambda x: upper.index(x["symbol"])
                          if x["symbol"] in upper else 999)
    else:
        processed = sorted(processed, key=lambda x: abs(x["rate_pct"]), reverse=True)[:15]

    revolut_picks = [p for p in processed if p["revolut_crypto"]]
    extreme       = [p for p in processed if abs(p["rate_pct"]) > 0.05]

    return {
        "funding_rates": processed,
        "revolut_crypto": revolut_picks,
        "extreme_alerts": extreme,
        "summary": (
            f"📊 {len(processed)} pairs. "
            f"🔴 {sum(1 for p in processed if p['rate_pct'] > 0.05)} extreme long bias. "
            f"🟢 {sum(1 for p in processed if p['rate_pct'] < -0.01)} short squeeze setups."
        ),
        "source": "Binance Perpetual Futures (no key)",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 16 — price_alert_check
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def price_alert_check(alerts: List[dict]) -> dict:
    """
    Check if any price targets have been hit for a list of alerts.
    Pass your watchlist with target levels — get instant go/no-go verdict.
    Perfect for AI agents monitoring positions between chat sessions.

    Args:
        alerts: List of dicts e.g.:
            [
              {"ticker": "NVDA",  "target": 1000.0, "direction": "above"},
              {"ticker": "BTC",   "target": 90000,  "direction": "above"},
              {"ticker": "AAPL",  "target": 180.0,  "direction": "below"},
            ]
        direction: "above" = alert if price >= target, "below" = alert if price <= target
    """
    if not alerts:
        return {"error": "No alerts provided"}

    results  = []
    triggered = []
    safe      = []

    for alert in alerts[:20]:
        raw    = alert.get("ticker", "")
        target = float(alert.get("target", 0))
        direc  = alert.get("direction", "above").lower()

        try:
            ticker = validate_ticker(raw)
        except ValueError as e:
            results.append({"ticker": raw, "error": str(e)})
            continue

        try:
            q = await (
                fetch_with_retry(limited_call, _binance_ticker, ticker)
                if ticker in ALL_CRYPTO else _get_stock_price(ticker)
            )
        except Exception as exc:
            results.append({"ticker": ticker, "target": target, "error": str(exc)})
            continue

        price = float(q.get("price", 0))
        hit   = (price >= target if direc == "above" else price <= target)
        gap   = price - target
        gap_p = (gap / target * 100) if target else 0
        on_r  = ticker in REVOLUT_STOCKS or ticker in REVOLUT_CRYPTO

        entry = {
            "ticker":     ticker,
            "current":    price,
            "target":     target,
            "direction":  direc,
            "triggered":  hit,
            "gap":        round(gap, 4),
            "gap_pct":    round(gap_p, 2),
            "revolut_available": on_r,
            "verdict": (
                f"🚨 TRIGGERED — {ticker} ${price} {'≥' if direc == 'above' else '≤'} ${target}"
                + (" 💳 Trade on Revolut now!" if on_r else "")
                if hit else
                f"⏳ Not yet — {ticker} ${price} | {gap_p:+.1f}% from ${target} target"
            ),
        }
        results.append(entry)
        (triggered if hit else safe).append(entry)

    return {
        "triggered_count": len(triggered),
        "safe_count":      len(safe),
        "triggered":       triggered,
        "safe":            safe,
        "results":         results,
        "summary": (
            f"🚨 {len(triggered)} alerts TRIGGERED! " if triggered else "✅ No alerts triggered yet. "
        ) + f"{len(safe)} still pending.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 17 — financial_news
# Source: Awesome-Finance-Skills / alphaear-news (NewsNow API)
# ─────────────────────────────────────────────────────────────────────────────

NEWS_SOURCES = {
    # Finance
    "cls":           "财联社 (CLS Finance)",
    "wallstreetcn":  "Wall Street CN",
    "xueqiu":        "Xueqiu",
    # Global / Tech
    "hackernews":    "Hacker News",
    "36kr":          "36Kr Tech",
    # Social
    "weibo":         "Weibo Trending",
    "zhihu":         "Zhihu Hot",
}

@mcp.tool()
async def financial_news(source: str = "wallstreetcn", count: int = 10) -> dict:
    """
    Fetch real-time hot financial news headlines from multiple sources.
    No API key required. Great for pre-trade news scan.

    Args:
        source: News source. Options:
            Finance: "cls" (CLS), "wallstreetcn" (Wall Street CN), "xueqiu"
            Global:  "hackernews", "36kr"
            Social:  "weibo", "zhihu"
            Default: "wallstreetcn"
        count: Number of headlines to fetch (default 10, max 20)
    """
    source = source.lower().strip()
    if source not in NEWS_SOURCES:
        return {
            "error": f"Unknown source '{source}'",
            "available_sources": list(NEWS_SOURCES.keys()),
        }
    count = min(int(count), 20)

    url = f"https://newsnow.busiyi.world/api/s?id={source}"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers=HEADERS)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return {"error": f"NewsNow API failed: {exc}", "source": source}

    items = data.get("items", [])[:count]
    if not items:
        return {"error": "No news items returned", "source": source}

    headlines = []
    for i, item in enumerate(items, 1):
        headlines.append({
            "rank":    i,
            "title":   item.get("title", ""),
            "url":     item.get("url", ""),
            "pubtime": item.get("publish_time", ""),
        })

    # Quick sentiment scan on titles
    bullish_kw = {"rise", "up", "bull", "surge", "beat", "profit", "growth",
                  "gain", "strong", "high", "record", "buy", "rally", "上涨",
                  "涨", "利好", "增长", "盈利", "新高"}
    bearish_kw = {"fall", "down", "bear", "drop", "miss", "loss", "decline",
                  "weak", "low", "sell", "crash", "risk", "下跌", "跌", "利空",
                  "亏损", "下行", "风险", "警告"}

    bull_count = bear_count = 0
    for h in headlines:
        t = h["title"].lower()
        if any(k in t for k in bullish_kw): bull_count += 1
        if any(k in t for k in bearish_kw): bear_count += 1

    mood = "🟢 Bullish" if bull_count > bear_count else ("🔴 Bearish" if bear_count > bull_count else "⚪ Neutral")

    return {
        "source":       source,
        "source_name":  NEWS_SOURCES[source],
        "count":        len(headlines),
        "headlines":    headlines,
        "headline_mood": mood,
        "bull_signals": bull_count,
        "bear_signals": bear_count,
        "revolut_tip": (
            "💳 Cross-reference these headlines with revolut_price_check() "
            "or revolut_sector_scan() to find actionable Revolut trades."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 18 — deepear_signals
# Source: Awesome-Finance-Skills / alphaear-deepear-lite (DeepEar Lite API)
# ─────────────────────────────────────────────────────────────────────────────

@ttl_cache(ttl=120)  # 2-min cache — signals update every few hours
async def _fetch_deepear_raw() -> dict:
    url = "https://deepear.vercel.app/latest.json"
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.get(url, headers={
            "User-Agent": "mcprice/3.0 (MCP Server; +https://github.com/gepappas98/mcprice)",
            "Referer":    "https://deepear.vercel.app/lite",
        })
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def deepear_signals(limit: int = 5) -> dict:
    """
    Fetch live professional investment signals from DeepEar Lite — no API key.
    Each signal includes title, confidence, intensity, sentiment score,
    reasoning chain, and source links. Updated every few hours.
    Perfect for institutional-grade market intelligence.

    Args:
        limit: Number of signals to return (default 5, max 10)
    """
    limit = min(int(limit), 10)
    try:
        data = await _fetch_deepear_raw()
    except Exception as exc:
        return {"error": f"DeepEar API unavailable: {exc}"}

    generated_at = data.get("generated_at", "unknown")
    raw_signals   = data.get("signals", [])

    if not raw_signals:
        return {"error": "No signals in DeepEar feed", "generated_at": generated_at}

    signals = []
    for s in raw_signals[:limit]:
        sentiment  = float(s.get("sentiment_score", 0))
        confidence = float(s.get("confidence", 0))
        intensity  = float(s.get("intensity", 0))

        # Map sentiment to Revolut action
        if sentiment > 0.3 and confidence > 0.6:
            revolut_action = "💳 CONSIDER BUY on Revolut — strong positive signal"
        elif sentiment < -0.3 and confidence > 0.6:
            revolut_action = "⚠️  CAUTION — bearish signal, review Revolut holdings"
        else:
            revolut_action = "⏳ MONITOR — signal not strong enough for immediate action"

        sources = [
            {"name": src.get("name", "Link"), "url": src.get("url", "")}
            for src in s.get("sources", [])
        ]

        signals.append({
            "title":          s.get("title", ""),
            "summary":        s.get("summary", ""),
            "sentiment_score": round(sentiment, 3),
            "confidence":      round(confidence, 3),
            "intensity":       round(intensity, 3),
            "reasoning":       s.get("reasoning", ""),
            "sources":         sources,
            "revolut_action":  revolut_action,
            "emoji": (
                "🟢" if sentiment > 0.2 else
                "🔴" if sentiment < -0.2 else "⚪"
            ),
        })

    avg_sentiment  = round(sum(s["sentiment_score"] for s in signals) / len(signals), 3) if signals else 0
    avg_confidence = round(sum(s["confidence"] for s in signals) / len(signals), 3) if signals else 0

    return {
        "generated_at":   generated_at,
        "signals_count":  len(signals),
        "signals":        signals,
        "market_summary": {
            "avg_sentiment":  avg_sentiment,
            "avg_confidence": avg_confidence,
            "overall_mood":   (
                "🟢 Bullish consensus"   if avg_sentiment > 0.2 else
                "🔴 Bearish consensus"   if avg_sentiment < -0.2 else
                "⚪ Mixed / Neutral"
            ),
        },
        "source": "deepear.vercel.app/lite",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 19 — prediction_markets
# Source: Awesome-Finance-Skills / alphaear-news (PolymarketTools)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def prediction_markets(limit: int = 10, topic_filter: Optional[str] = None) -> dict:
    """
    Fetch live Polymarket prediction markets — crowd probability on real-world events.
    No API key needed. Shows where smart money places probability bets.
    Great for macro context: elections, crypto ETF approvals, Fed decisions, etc.

    Args:
        limit: Number of markets to return (default 10, max 30)
        topic_filter: Optional keyword filter e.g. "bitcoin", "fed", "election"
    """
    limit = min(int(limit), 30)
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://gamma-api.polymarket.com/markets",
                params={"active": "true", "closed": "false", "limit": str(limit * 2)},
                headers=HEADERS,
            )
            r.raise_for_status()
            raw = r.json()
    except Exception as exc:
        return {"error": f"Polymarket API failed: {exc}"}

    if not raw:
        return {"error": "No markets returned from Polymarket"}

    # Filter by topic if provided
    if topic_filter:
        kw = topic_filter.lower()
        raw = [m for m in raw if kw in (m.get("question", "") + m.get("slug", "")).lower()]

    markets = []
    for m in raw[:limit]:
        question = m.get("question", "")
        outcomes  = m.get("outcomes", [])
        prices    = m.get("outcomePrices", [])
        volume    = m.get("volume", 0)
        liquidity = m.get("liquidity", 0)

        # Parse probabilities
        prob_pairs = []
        try:
            outcomes_list = outcomes if isinstance(outcomes, list) else []
            prices_list   = prices   if isinstance(prices, list)   else []
            for o, p in zip(outcomes_list, prices_list):
                try:
                    prob_pairs.append({"outcome": str(o), "probability": f"{float(p)*100:.1f}%"})
                except Exception:
                    pass
        except Exception:
            pass

        # Signal: is the leading probability strong (>70%)?
        top_prob = 0.0
        if prob_pairs:
            try:
                top_prob = max(float(p.replace("%","")) for p in
                               [pp["probability"] for pp in prob_pairs])
            except Exception:
                pass

        signal = (
            f"🎯 HIGH CONVICTION ({top_prob:.0f}%) — market has strong consensus"
            if top_prob > 70 else
            "⚖️  CONTESTED — outcome still uncertain"
            if top_prob > 40 else
            "❓ WIDE OPEN — no clear market consensus"
        )

        markets.append({
            "question":    question,
            "probabilities": prob_pairs,
            "volume_usd":  round(float(volume), 0) if volume else 0,
            "liquidity":   round(float(liquidity), 0) if liquidity else 0,
            "signal":      signal,
            "slug_url":    f"https://polymarket.com/event/{m.get('slug', '')}",
        })

    # Sort by volume (most liquid markets first)
    markets.sort(key=lambda x: x["volume_usd"], reverse=True)

    return {
        "total_markets": len(markets),
        "topic_filter":  topic_filter or "none",
        "markets":       markets,
        "revolut_tip": (
            "💳 Use prediction markets for macro timing: "
            "if Bitcoin ETF approval probability > 80%, "
            "consider BTC via Revolut Crypto. "
            "If rate-cut probability high, tech stocks on Revolut benefit."
        ),
        "source": "Polymarket Gamma API (no key)",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 20 — news_sentiment_score
# Source: Awesome-Finance-Skills / alphaear-sentiment (adapted, zero deps)
# ─────────────────────────────────────────────────────────────────────────────

# Financial sentiment lexicon (distilled from FinBERT + domain knowledge)
_FIN_BULLISH = {
    # English
    "surge", "soar", "rally", "beat", "outperform", "upgrade", "bullish",
    "record high", "strong", "growth", "profit", "revenue beat", "raise",
    "buy", "overweight", "breakthrough", "expansion", "recovery", "upbeat",
    "positive", "gain", "rise", "climb", "boost", "exceed", "optimistic",
    # Finance specific
    "eps beat", "guidance raised", "buyback", "dividend increase", "market share",
    "customer growth", "margin expansion", "free cash flow",
}

_FIN_BEARISH = {
    # English
    "crash", "plunge", "slump", "miss", "underperform", "downgrade", "bearish",
    "record low", "weak", "loss", "revenue miss", "cut", "sell", "underweight",
    "recall", "layoff", "restructuring", "investigation", "lawsuit", "fraud",
    "negative", "fall", "drop", "decline", "concern", "warning", "risk",
    # Finance specific
    "eps miss", "guidance cut", "margin compression", "cash burn", "write-off",
    "impairment", "debt default", "tariff", "regulation", "fine", "penalty",
}

_FIN_STRONG_BULLISH = {
    "record earnings", "blowout quarter", "massive beat", "all-time high",
    "short squeeze", "massive rally", "explosive growth",
}

_FIN_STRONG_BEARISH = {
    "bankruptcy", "fraud", "collapse", "crisis", "catastrophic", "wipeout",
    "delisted", "sec investigation", "accounting scandal", "going concern",
}


def _keyword_sentiment(text: str) -> dict:
    """Pure-Python financial sentiment scoring — zero external deps."""
    t = text.lower()
    words = set(t.split())

    bull_hits  = [k for k in _FIN_BULLISH if k in t]
    bear_hits  = [k for k in _FIN_BEARISH if k in t]
    sbull_hits = [k for k in _FIN_STRONG_BULLISH if k in t]
    sbear_hits = [k for k in _FIN_STRONG_BEARISH if k in t]

    score = (
        len(bull_hits)  * 0.15 +
        len(sbull_hits) * 0.40 -
        len(bear_hits)  * 0.15 -
        len(sbear_hits) * 0.40
    )
    # Clamp to [-1, 1]
    score = max(-1.0, min(1.0, round(score, 3)))

    if score > 0.2:   label = "positive"
    elif score < -0.2: label = "negative"
    else:             label = "neutral"

    return {
        "score":       score,
        "label":       label,
        "bull_signals": bull_hits  + sbull_hits,
        "bear_signals": bear_hits  + sbear_hits,
    }


@mcp.tool()
async def news_sentiment_score(texts: List[str]) -> dict:
    """
    Fast financial sentiment scoring for a list of texts (headlines, news, etc.).
    Zero dependencies — pure Python keyword lexicon distilled from FinBERT.
    Score range: -1.0 (very bearish) to +1.0 (very bullish).

    Args:
        texts: List of financial text strings to analyze.
               e.g. ["NVDA beats earnings by 20%", "Fed cuts rates 50bps",
                     "Tesla misses delivery targets", "BTC hits all-time high"]
    """
    if not texts:
        return {"error": "No texts provided"}

    results = []
    total_score = 0.0

    for i, text in enumerate(texts[:30]):
        s = _keyword_sentiment(text)
        s["text"]   = text[:200]
        s["index"]  = i
        s["emoji"]  = "🟢" if s["score"] > 0.1 else ("🔴" if s["score"] < -0.1 else "⚪")
        s["summary"] = (
            f"{s['emoji']} {s['label'].upper()} ({s['score']:+.2f}) — {text[:60]}{'...' if len(text)>60 else ''}"
        )
        results.append(s)
        total_score += s["score"]

    n = len(results)
    avg = round(total_score / n, 3) if n else 0
    positive_count = sum(1 for r in results if r["label"] == "positive")
    negative_count = sum(1 for r in results if r["label"] == "negative")
    neutral_count  = sum(1 for r in results if r["label"] == "neutral")

    return {
        "results":        results,
        "count":          n,
        "avg_score":      avg,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "neutral_count":  neutral_count,
        "overall_mood": (
            "🟢 Bullish" if avg > 0.15 else
            "🔴 Bearish" if avg < -0.15 else
            "⚪ Neutral / Mixed"
        ),
        "revolut_tip": (
            "💳 Use with financial_news() to scan headlines, then run "
            "revolut_price_check() on the affected tickers."
        ),
        "method": "keyword-lexicon (FinBERT-distilled, zero external deps)",
    }


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        port = int(os.environ.get("PORT", "8080"))
        logger.info("mcprice v4.0 — http://0.0.0.0:%d/mcp", port)
        app = mcp.http_app()
        app.add_middleware(HealthMiddleware)
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        logger.info("mcprice v4.0 — stdio mode")
        mcp.run(transport="stdio")

# ═══════════════════════════════════════════════════════════════════════════════
# ██╗   ██╗███████╗     ███████╗██╗  ██╗██╗██╗     ██╗      ███████╗
# ██║   ██║██╔════╝     ██╔════╝██║ ██╔╝██║██║     ██║      ██╔════╝
# ██║   ██║███████╗     ███████╗█████╔╝ ██║██║     ██║      ███████╗
# ╚██╗ ██╔╝╚════██║     ╚════██║██╔═██╗ ██║██║     ██║      ╚════██║
#  ╚████╔╝ ███████║     ███████║██║  ██╗██║███████╗███████╗ ███████║
#   ╚═══╝  ╚══════╝     ╚══════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝ ╚══════╝
# ─────────────────────────────────────────────────────────────────────────────
#  Tools 21–25 — Converted from Awesome-Finance-Skills SKILL.md format
#  by GRG / mcprice v5.0
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 21 — stock_correlation
# Source: Awesome-Finance-Skills / stock-correlation SKILL.md
# Converted: Sub-skills A (co-movement discovery) + B (pairwise analysis)
#            + C (sector clustering) + D (realized/rolling correlation)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def stock_correlation(
    tickers: List[str],
    mode: str = "discover",
    period: str = "1y",
) -> dict:
    """
    Stock correlation engine — powered by the finance-skills stock-correlation SKILL.
    Finds co-moving stocks, computes pairwise relationships, sector clustering,
    and rolling/regime-conditional realized correlation.

    Args:
        tickers:
            - mode "discover":  single ticker to find correlated peers, e.g. ["NVDA"]
            - mode "pair":      exactly 2 tickers, e.g. ["AMD", "NVDA"]
            - mode "cluster":   3–15 tickers for full correlation matrix
            - mode "rolling":   exactly 2 tickers for time-varying analysis
        mode:   "discover" | "pair" | "cluster" | "rolling"  (default "discover")
        period: yfinance period — "1y", "2y", "6mo", "3mo"   (default "1y")

    Returns structured dict with correlations, signals, and Revolut flags.
    """
    import numpy as np
    import pandas as pd

    # ── validate ─────────────────────────────────────────────────────────────
    mode = mode.lower().strip()
    if mode not in ("discover", "pair", "cluster", "rolling"):
        return {"error": f"Unknown mode '{mode}'", "valid_modes": ["discover", "pair", "cluster", "rolling"]}
    tickers = [t.upper().strip() for t in tickers[:15]]
    if not tickers:
        return {"error": "Provide at least one ticker"}

    # ── shared download helper (run in executor — yfinance is sync) ───────────
    def _download(tkrs: list, per: str) -> pd.DataFrame:
        import yfinance as yf
        data = yf.download(tkrs, period=per, auto_adjust=True, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            closes = data["Close"]
        else:
            closes = data[["Close"]] if "Close" in data.columns else data
        closes = closes.dropna(axis=1, thresh=max(20, len(data) // 3))
        return closes

    def _log_returns(closes: pd.DataFrame) -> pd.DataFrame:
        import numpy as np
        return (closes / closes.shift(1)).apply(lambda x: x.map(
            lambda v: __import__('math').log(v) if v and v > 0 else float('nan')
        )).dropna()

    def _arrow_corr(c: float) -> str:
        if c >= 0.80: return "🔴 Very strong co-move"
        if c >= 0.60: return "🟠 Strong co-move"
        if c >= 0.40: return "🟡 Moderate"
        if c >= 0.20: return "⚪ Weak"
        if c >= -0.20: return "➡️ Near-zero"
        return "🟢 Inverse (hedge candidate)"

    loop = asyncio.get_running_loop()

    # ═════════════════════════════════════════════════════════════════════════
    # MODE A — Co-movement Discovery
    # ═════════════════════════════════════════════════════════════════════════
    if mode == "discover":
        target = tickers[0]

        # Build peer universe: same industry + AI sector peers + ETF proxies
        def _build_peer_universe(tgt: str) -> list:
            try:
                import yfinance as yf
                info = yf.Ticker(tgt).info
                industry = info.get("industry", "")
                sector   = info.get("sector", "")
            except Exception:
                industry = sector = ""

            # Curated sector universes (mirrors skill's sector_universes.md)
            SECTOR_MAP = {
                "Technology":           ["NVDA","AMD","AVGO","INTC","QCOM","TSM","ASML","LRCX","AMAT","MU","MSFT","AAPL","GOOGL","META"],
                "Financial Services":   ["JPM","BAC","GS","MS","V","MA","BLK","SCHW","AXP","WFC"],
                "Healthcare":           ["JNJ","PFE","LLY","ABBV","MRK","AMGN","GILD","UNH","CVS","MRNA"],
                "Energy":               ["XOM","CVX","COP","OXY","SLB","HAL","XLE","USO"],
                "Industrials":          ["LMT","RTX","BA","GD","NOC","LHX","HON","CAT","DE"],
                "Consumer Cyclical":    ["AMZN","TSLA","NKE","MCD","SBUX","HD","LOW","TGT","WMT"],
                "Communication Services":["GOOGL","META","DIS","NFLX","T","VZ","CMCSA","SNAP"],
                "Real Estate":          ["SPG","PLD","O","AMT","CCI","EQIX"],
            }
            peers = SECTOR_MAP.get(sector, [])
            if len(peers) < 10:
                for s in SECTOR_MAP.values():
                    peers += [t for t in s if t not in peers]
                peers = peers[:25]
            return [t for t in dict.fromkeys(peers) if t != tgt][:20]

        peers = await loop.run_in_executor(None, _build_peer_universe, target)
        all_tkrs = [target] + peers

        def _calc_discover():
            import yfinance as yf, numpy as np, pandas as pd, math
            data = yf.download(all_tkrs, period=period, auto_adjust=True, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                closes = data["Close"]
            else:
                closes = data
            closes = closes.dropna(axis=1, thresh=max(20, len(data)//3))
            returns = np.log(closes / closes.shift(1)).dropna()
            if target not in returns.columns:
                return {"error": f"Insufficient data for {target}"}
            corr_series = returns.corr()[target].drop(target, errors="ignore")
            ranked = corr_series.abs().sort_values(ascending=False)
            results = []
            for tkr in ranked.index[:12]:
                c = float(corr_series[tkr])
                try:
                    name = yf.Ticker(tkr).fast_info.display_name or tkr
                except Exception:
                    name = tkr
                results.append({
                    "ticker":      tkr,
                    "name":        name,
                    "correlation": round(c, 4),
                    "abs_corr":    round(abs(c), 4),
                    "strength":    _arrow_corr(c),
                    "revolut_available": tkr in REVOLUT_STOCKS,
                    "revolut_crypto":    tkr in REVOLUT_CRYPTO,
                })
            return results

        results = await loop.run_in_executor(None, _calc_discover)
        if isinstance(results, dict):
            return results

        on_revolut = [r for r in results if r["revolut_available"]]
        return {
            "mode":           "discover",
            "target":         target,
            "period":         period,
            "peers_scanned":  len(results),
            "top_correlated": results[:10],
            "revolut_picks":  on_revolut[:5],
            "best_pair": results[0] if results else None,
            "strategy_hints": {
                "sympathy_plays": [r["ticker"] for r in results[:3] if r["correlation"] > 0.6],
                "hedge_candidates": [r["ticker"] for r in results if r["correlation"] < -0.3],
                "revolut_trades": [r["ticker"] for r in on_revolut[:3]],
            },
            "note": "Correlation is not causation. Past correlations may not persist.",
        }

    # ═════════════════════════════════════════════════════════════════════════
    # MODE B — Pairwise Return Correlation (deep analysis)
    # ═════════════════════════════════════════════════════════════════════════
    if mode == "pair":
        if len(tickers) < 2:
            return {"error": "Provide 2 tickers for pair mode"}
        ta, tb = tickers[0], tickers[1]

        def _calc_pair():
            import yfinance as yf, numpy as np, pandas as pd, math
            data = yf.download([ta, tb], period=period, auto_adjust=True, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                closes = data["Close"][[ta, tb]].dropna()
            else:
                closes = data.dropna()
            returns = np.log(closes / closes.shift(1)).dropna()
            if ta not in returns.columns or tb not in returns.columns:
                return {"error": "Insufficient data for one or both tickers"}
            corr = float(returns[ta].corr(returns[tb]))
            cov  = returns.cov()
            beta = float(cov.loc[tb, ta] / cov.loc[ta, ta]) if cov.loc[ta, ta] != 0 else 0
            roll = returns[ta].rolling(60).corr(returns[tb])
            spread = np.log(closes[ta] / closes[tb])
            spread_z = float((spread - spread.mean()) / spread.std()) if spread.std() != 0 else 0
            return {
                "correlation":          round(corr, 4),
                "r_squared":            round(corr**2, 4),
                "beta_b_vs_a":          round(beta, 4),
                "rolling_60d_mean":     round(float(roll.mean()), 4),
                "rolling_60d_std":      round(float(roll.std()), 4),
                "rolling_60d_min":      round(float(roll.min()), 4),
                "rolling_60d_max":      round(float(roll.max()), 4),
                "rolling_60d_current":  round(float(roll.iloc[-1]), 4),
                "spread_z_score":       round(spread_z, 3),
                "observations":         len(returns),
            }

        metrics = await loop.run_in_executor(None, _calc_pair)
        if "error" in metrics:
            return metrics

        c = metrics["correlation"]
        interp = (
            "🔴 Very strongly correlated — move almost in lockstep" if c > 0.80 else
            "🟠 Strongly correlated — shared sector drivers" if c > 0.60 else
            "🟡 Moderately correlated — partial co-movement" if c > 0.40 else
            "⚪ Weakly correlated" if c > 0.20 else
            "🟢 Near-zero / inverse — potential hedge pair"
        )
        spread_signal = (
            "⚠️  Unusual divergence from historical ratio — mean-reversion trade potential"
            if abs(metrics["spread_z_score"]) > 2 else
            "✅ Spread within normal range"
        )
        return {
            "mode":          "pair",
            "ticker_a":      ta,
            "ticker_b":      tb,
            "period":        period,
            "metrics":       metrics,
            "interpretation": interp,
            "spread_signal": spread_signal,
            "revolut_a":     ta in REVOLUT_STOCKS,
            "revolut_b":     tb in REVOLUT_STOCKS,
            "trade_ideas": {
                "pair_trade": abs(metrics["spread_z_score"]) > 2,
                "z_score":    metrics["spread_z_score"],
                "action": (
                    f"Long {ta} / Short {tb}" if metrics["spread_z_score"] < -2 else
                    f"Long {tb} / Short {ta}" if metrics["spread_z_score"] > 2 else
                    "No divergence trade — spread in range"
                ),
            },
        }

    # ═════════════════════════════════════════════════════════════════════════
    # MODE C — Sector Clustering (correlation matrix)
    # ═════════════════════════════════════════════════════════════════════════
    if mode == "cluster":
        if len(tickers) < 3:
            return {"error": "Provide 3+ tickers for cluster mode"}

        def _calc_cluster():
            import yfinance as yf, numpy as np, pandas as pd, math
            data = yf.download(tickers, period=period, auto_adjust=True, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                closes = data["Close"].dropna(axis=1, thresh=max(20, len(data)//3))
            else:
                closes = data.dropna()
            returns = np.log(closes / closes.shift(1)).dropna()
            corr_m  = returns.corr()
            # Top pairs
            pairs = []
            cols = list(corr_m.columns)
            for i in range(len(cols)):
                for j in range(i+1, len(cols)):
                    pairs.append((cols[i], cols[j], round(float(corr_m.iloc[i, j]), 4)))
            pairs.sort(key=lambda x: abs(x[2]), reverse=True)
            # Avg per ticker
            avg_corr = {
                t: round(float(corr_m[t].drop(t).abs().mean()), 4)
                for t in corr_m.columns
            }
            matrix_rows = []
            for tkr in corr_m.index:
                row = {"ticker": tkr}
                for other in corr_m.columns:
                    row[other] = round(float(corr_m.loc[tkr, other]), 4)
                matrix_rows.append(row)
            return {
                "matrix": matrix_rows,
                "top_pairs":  [(a, b, c) for a, b, c in pairs[:5]],
                "weak_pairs": [(a, b, c) for a, b, c in pairs[-5:]],
                "avg_corr_per_ticker": avg_corr,
                "diversifiers": sorted(avg_corr.items(), key=lambda x: x[1])[:3],
                "most_connected": sorted(avg_corr.items(), key=lambda x: x[1], reverse=True)[:3],
            }

        result = await loop.run_in_executor(None, _calc_cluster)
        if "error" in result:
            return result

        return {
            "mode":    "cluster",
            "tickers": tickers,
            "period":  period,
            **result,
            "revolut_available": {t: t in REVOLUT_STOCKS for t in tickers},
            "insight": (
                f"Most connected: {result['most_connected'][0][0]} (avg corr {result['most_connected'][0][1]}). "
                f"Best diversifier: {result['diversifiers'][0][0]} (avg corr {result['diversifiers'][0][1]})."
            ),
        }

    # ═════════════════════════════════════════════════════════════════════════
    # MODE D — Realized / Rolling Correlation
    # ═════════════════════════════════════════════════════════════════════════
    if mode == "rolling":
        if len(tickers) < 2:
            return {"error": "Provide 2 tickers for rolling mode"}
        ta, tb = tickers[0], tickers[1]

        def _calc_rolling():
            import yfinance as yf, numpy as np, pandas as pd, math
            data = yf.download([ta, tb], period=period, auto_adjust=True, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                closes = data["Close"][[ta, tb]].dropna()
            else:
                closes = data.dropna()
            returns = np.log(closes / closes.shift(1)).dropna()
            if ta not in returns.columns or tb not in returns.columns:
                return {"error": "Insufficient data"}

            # Multi-window rolling
            windows_result = {}
            for w in [20, 60, 120]:
                roll = returns[ta].rolling(w).corr(returns[tb]).dropna()
                windows_result[f"{w}d"] = {
                    "current": round(float(roll.iloc[-1]), 4),
                    "mean":    round(float(roll.mean()), 4),
                    "std":     round(float(roll.std()), 4),
                    "min":     round(float(roll.min()), 4),
                    "max":     round(float(roll.max()), 4),
                }

            # Regime correlation
            regimes = {}
            ret_a = returns[ta]
            for name, mask in [
                ("all_days",          pd.Series(True, index=returns.index)),
                ("up_days",           ret_a > 0),
                ("down_days",         ret_a < 0),
                ("high_vol_top25pct", ret_a.abs() > ret_a.abs().quantile(0.75)),
                ("large_drawdown",    ret_a < -0.02),
            ]:
                subset = returns[mask]
                if len(subset) >= 20:
                    regimes[name] = {
                        "corr": round(float(subset[ta].corr(subset[tb])), 4),
                        "days": int(mask.sum()),
                    }

            crisis_amplification = (
                regimes.get("large_drawdown", {}).get("corr", 0) >
                regimes.get("all_days", {}).get("corr", 0) + 0.1
            )
            return {
                "rolling_windows": windows_result,
                "regime_correlation": regimes,
                "crisis_amplification": crisis_amplification,
            }

        result = await loop.run_in_executor(None, _calc_rolling)
        if isinstance(result, dict) and "error" in result:
            return result

        return {
            "mode":    "rolling",
            "ticker_a": ta,
            "ticker_b": tb,
            "period":   period,
            **result,
            "key_insight": (
                "⚠️  Correlation spikes during sell-offs — diversification may FAIL in crisis"
                if result.get("crisis_amplification") else
                "✅ Correlation is stable across market regimes"
            ),
            "revolut_a": ta in REVOLUT_STOCKS,
            "revolut_b": tb in REVOLUT_STOCKS,
        }

    return {"error": "Unknown mode"}


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 22 — options_analysis
# Source: Awesome-Finance-Skills / options-payoff SKILL.md
# Converted to pure JSON output (no HTML — MCP returns structured data)
# Supports: butterfly, vertical_spread, iron_condor, straddle, strangle,
#           covered_call, naked_put, calendar_spread (BS approximation)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def options_analysis(
    strategy: str,
    underlying: str,
    spot: float,
    strikes: List[float],
    premium: float,
    dte: int = 30,
    iv: float = 0.20,
    quantity: int = 1,
    multiplier: int = 100,
    risk_free_rate: float = 0.043,
) -> dict:
    """
    Black-Scholes options payoff & theoretical value analysis.
    Converted from the finance-skills options-payoff SKILL.md.
    Returns expiry payoff curve, breakevens, max P&L, Greeks, and Revolut context.

    Args:
        strategy:       "butterfly" | "vertical_spread" | "iron_condor" |
                        "straddle" | "strangle" | "covered_call" | "naked_put"
        underlying:     Ticker symbol e.g. "SPY", "NVDA", "AAPL"
        spot:           Current underlying price e.g. 580.0
        strikes:        Strike prices list (order matters per strategy):
                        butterfly/iron_condor: [K1, K2, K3] or [K1,K2,K3,K4]
                        vertical_spread:       [K_long, K_short]
                        straddle/naked_put/covered_call: [K]
                        strangle:              [K_put, K_call]
        premium:        Net premium paid (positive=debit) or received (negative=credit)
        dte:            Days to expiry (default 30)
        iv:             Implied volatility as decimal e.g. 0.20 = 20% (default 0.20)
        quantity:       Number of contracts (default 1)
        multiplier:     Contract multiplier (default 100 for equity options)
        risk_free_rate: Annual risk-free rate (default 0.043 = 4.3%)
    """
    import math

    def norm_cdf(x: float) -> float:
        """Cumulative standard normal — Abramowitz & Stegun 26.2.17"""
        if x < -8: return 0.0
        if x >  8: return 1.0
        t = 1 / (1 + 0.2316419 * abs(x))
        poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
        p = 1 - (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x) * poly
        return p if x >= 0 else 1 - p

    def bs_call(S: float, K: float, T: float, r: float, sig: float) -> float:
        if T <= 0: return max(S - K, 0)
        d1 = (math.log(S / K) + (r + 0.5 * sig**2) * T) / (sig * math.sqrt(T))
        d2 = d1 - sig * math.sqrt(T)
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)

    def bs_put(S: float, K: float, T: float, r: float, sig: float) -> float:
        return bs_call(S, K, T, r, sig) - S + K * math.exp(-r * T)

    def bs_delta(S, K, T, r, sig, opt="call") -> float:
        if T <= 0: return 1.0 if (S > K and opt == "call") else 0.0
        d1 = (math.log(S / K) + (r + 0.5 * sig**2) * T) / (sig * math.sqrt(T))
        return norm_cdf(d1) if opt == "call" else norm_cdf(d1) - 1

    T = dte / 365.0
    strat = strategy.lower().strip()

    # ── scan price range for payoff curve (21 points) ────────────────────────
    min_s = min(strikes) * 0.80
    max_s = max(strikes) * 1.20
    price_range = [round(min_s + (max_s - min_s) * i / 20, 2) for i in range(21)]

    def expiry_pnl(S: float) -> float:
        """Per-contract P&L at expiry (excluding premium which is added separately)."""
        if strat == "butterfly":
            k1, k2, k3 = strikes[0], strikes[1], strikes[2]
            if   S >= k3: return 0
            elif S >= k2: return k3 - S
            elif S >= k1: return S - k1
            else:         return 0
        elif strat == "vertical_spread":
            k1, k2 = strikes[0], strikes[1]
            return max(S - k1, 0) - max(S - k2, 0)
        elif strat == "iron_condor":
            k1, k2, k3, k4 = (strikes + [strikes[-1]+1])[:4]
            put_spread  = max(k2 - S, 0) - max(k1 - S, 0)
            call_spread = max(S - k3, 0) - max(S - k4, 0)
            return -(put_spread + call_spread)
        elif strat == "straddle":
            k = strikes[0]
            return max(S - k, 0) + max(k - S, 0)
        elif strat == "strangle":
            kp, kc = strikes[0], strikes[1]
            return max(kp - S, 0) + max(S - kc, 0)
        elif strat == "covered_call":
            k = strikes[0]
            return S - spot - max(S - k, 0)   # long stock + short call
        elif strat == "naked_put":
            k = strikes[0]
            return -max(k - S, 0)
        return 0

    def theory_pnl(S: float) -> float:
        """Theoretical P&L at current DTE via Black-Scholes."""
        if strat == "butterfly":
            k1, k2, k3 = strikes[0], strikes[1], strikes[2]
            v = (bs_put(S, k1, T, risk_free_rate, iv)
               - 2 * bs_put(S, k2, T, risk_free_rate, iv)
               + bs_put(S, k3, T, risk_free_rate, iv))
            return v
        elif strat == "vertical_spread":
            k1, k2 = strikes[0], strikes[1]
            return bs_call(S, k1, T, risk_free_rate, iv) - bs_call(S, k2, T, risk_free_rate, iv)
        elif strat == "straddle":
            k = strikes[0]
            return bs_call(S, k, T, risk_free_rate, iv) + bs_put(S, k, T, risk_free_rate, iv)
        elif strat == "strangle":
            kp, kc = strikes[0], strikes[1]
            return bs_put(S, kp, T, risk_free_rate, iv) + bs_call(S, kc, T, risk_free_rate, iv)
        elif strat == "naked_put":
            return -bs_put(S, strikes[0], T, risk_free_rate, iv)
        elif strat == "covered_call":
            return S - spot - bs_call(S, strikes[0], T, risk_free_rate, iv)
        return expiry_pnl(S)

    # ── compute payoff curve (net of premium, scaled by qty × multiplier) ────
    scale = quantity * multiplier

    curve_expiry  = [round((expiry_pnl(p) - premium) * scale, 2) for p in price_range]
    curve_theory  = [round((theory_pnl(p)  - premium) * scale, 2) for p in price_range]

    # ── key stats ─────────────────────────────────────────────────────────────
    max_profit = max(curve_expiry)
    max_loss   = min(curve_expiry)

    # breakevens (sign change in expiry curve)
    breakevens = []
    for i in range(len(curve_expiry) - 1):
        if curve_expiry[i] * curve_expiry[i+1] <= 0:
            # linear interpolation
        
            p1, p2 = price_range[i], price_range[i+1]
            v1, v2 = curve_expiry[i], curve_expiry[i+1]
            if v2 - v1 != 0:
                be = round(p1 - v1 * (p2 - p1) / (v2 - v1), 2)
                breakevens.append(be)

    # current theoretical P&L at spot
    current_theory_pnl = round((theory_pnl(spot) - premium) * scale, 2)

    # Greeks at spot
    k_center = strikes[len(strikes)//2]
    delta_v = round(bs_delta(spot, k_center, T, risk_free_rate, iv), 4)

    # ── revolut context ───────────────────────────────────────────────────────
    on_revolut = underlying.upper() in REVOLUT_STOCKS

    return {
        "strategy":    strat,
        "underlying":  underlying.upper(),
        "spot":        spot,
        "strikes":     strikes,
        "dte":         dte,
        "iv_pct":      round(iv * 100, 1),
        "premium":     premium,
        "quantity":    quantity,
        "multiplier":  multiplier,
        "scale":       scale,
        # Key stats
        "max_profit_usd":    max_profit,
        "max_loss_usd":      max_loss,
        "breakevens":        breakevens,
        "current_theory_pnl": current_theory_pnl,
        "risk_reward_ratio": round(abs(max_profit / max_loss), 2) if max_loss != 0 else None,
        # Greeks (simplified at center strike)
        "delta_approx": delta_v,
        "theta_per_day_approx": round(
            -bs_call(spot, k_center, T, risk_free_rate, iv) * iv / (2 * math.sqrt(T * 365)) if T > 0 else 0, 4
        ),
        # Payoff curve (21 points)
        "payoff_curve": {
            "prices":        price_range,
            "expiry_pnl":   curve_expiry,
            "theory_pnl":   curve_theory,
        },
        # Revolut context
        "revolut_available": on_revolut,
        "revolut_note": (
            f"💳 {underlying.upper()} is tradeable on Revolut — however Revolut does NOT support options. "
            "Use this analysis for directional bias and then trade the underlying stock on Revolut."
            if on_revolut else
            f"❌ {underlying.upper()} not on Revolut — use for research only."
        ),
        "strategy_summary": (
            f"{strat.replace('_',' ').title()}: "
            f"Max profit ${max_profit:+.0f} / Max loss ${max_loss:+.0f} / "
            f"Breakeven(s): {', '.join(f'${b}' for b in breakevens) or 'N/A'}"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 23 — geopolitical_energy_risk
# Source: Awesome-Finance-Skills / hormuz-strait SKILL.md
# Full Hormuz Strait Monitor integration + Revolut energy trade signals
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def geopolitical_energy_risk() -> dict:
    """
    Real-time Strait of Hormuz status — shipping transits, oil prices,
    stranded vessels, war-risk insurance, diplomatic situation, and
    global trade impact. Converted from finance-skills hormuz-strait SKILL.md.

    No arguments. Perfect for energy sector traders and macro context.
    Returns structured JSON with Revolut energy trade signals.
    """
    HORMUZ_API = "https://hormuzstraitmonitor.com/api/dashboard"

    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(HORMUZ_API, headers=HEADERS)
            r.raise_for_status()
            payload = r.json()
    except Exception as exc:
        return {
            "error": f"Hormuz Monitor API unavailable: {exc}",
            "fallback": "Check https://hormuzstraitmonitor.com directly",
            "revolut_tip": (
                "💳 When Hormuz data is unavailable, monitor XOM, CVX, OXY, XLE on Revolut "
                "via revolut_sector_scan('energy') for real-time oil sector pricing."
            ),
        }

    if not payload.get("success"):
        return {"error": "Hormuz Monitor returned success=false", "raw": payload}

    d = payload.get("data", {})

    # ── extract sections ──────────────────────────────────────────────────────
    strait     = d.get("straitStatus", {})
    ships      = d.get("shipCount", {})
    oil        = d.get("oilPrice", {})
    stranded   = d.get("strandedVessels", {})
    insurance  = d.get("insurance", {})
    throughput = d.get("throughput", {})
    diplomacy  = d.get("diplomacy", {})
    gti        = d.get("globalTradeImpact", {})
    timeline   = d.get("crisisTimeline", {}).get("events", [])
    news       = d.get("news", [{}])

    # ── risk classification ───────────────────────────────────────────────────
    ins_level  = insurance.get("level", "normal")
    risk_emoji = {"normal": "🟢", "elevated": "🟡", "high": "🔴", "critical": "🚨"}.get(ins_level, "⚪")

    pct_normal = ships.get("percentOfNormal", 100)
    traffic_signal = (
        "🚨 MAJOR DISRUPTION — traffic severely below normal" if pct_normal < 60 else
        "🔴 SIGNIFICANT disruption" if pct_normal < 80 else
        "🟡 Mild disruption" if pct_normal < 95 else
        "🟢 Normal traffic"
    )

    # ── Revolut energy trade signals ─────────────────────────────────────────
    REVOLUT_ENERGY = {t: REVOLUT_STOCKS.get(t, t) for t in ["XOM","CVX","COP","OXY","XLE","USO","SLV","GLD"]}
    on_revolut_energy = [t for t in REVOLUT_ENERGY if t in REVOLUT_STOCKS]

    brent_chg = oil.get("changePercent24h", 0)
    if ins_level in ("high", "critical") or pct_normal < 80:
        trade_bias = "🔴 BULLISH oil — consider XOM, CVX, OXY, XLE on Revolut (long energy)"
        hedge_tip  = "Consider GLD as safe-haven via Revolut (Gold ETF)"
    elif ins_level == "elevated":
        trade_bias = "🟡 MILD bullish oil — monitor XLE, OXY for breakout entry on Revolut"
        hedge_tip  = "Watch for escalation before committing to energy longs"
    else:
        trade_bias = "🟢 Normal — no Hormuz premium in oil prices. Focus on fundamentals."
        hedge_tip  = "No hedging urgency from Hormuz risk currently"

    return {
        "source":       "hormuzstraitmonitor.com",
        "last_updated": d.get("lastUpdated", payload.get("timestamp", "unknown")),
        "strait_status": {
            "status":      strait.get("status", "UNKNOWN"),
            "since":       strait.get("since"),
            "description": strait.get("description"),
        },
        "ship_traffic": {
            "current_transits":  ships.get("currentTransits"),
            "last_24h":          ships.get("last24h"),
            "normal_daily":      ships.get("normalDaily"),
            "percent_of_normal": pct_normal,
            "signal":            traffic_signal,
        },
        "oil_price": {
            "brent_usd":      oil.get("brentPrice"),
            "change_24h":     oil.get("change24h"),
            "change_pct_24h": brent_chg,
            "trend":          "📈 Rising" if brent_chg > 0 else "📉 Falling",
        },
        "stranded_vessels": {
            "total":        stranded.get("total", 0),
            "tankers":      stranded.get("tankers", 0),
            "bulk":         stranded.get("bulk", 0),
            "other":        stranded.get("other", 0),
            "change_today": stranded.get("changeToday", 0),
        },
        "insurance_risk": {
            "level":           ins_level,
            "emoji":           risk_emoji,
            "war_risk_pct":    insurance.get("warRiskPercent"),
            "normal_pct":      insurance.get("normalPercent"),
            "multiplier":      insurance.get("multiplier"),
            "interpretation": {
                "normal":   "No elevated risk — shipping operating normally",
                "elevated": "Some disruption — monitor closely",
                "high":     "Significant risk — active disruption or credible threat",
                "critical": "Severe disruption — major impact on global oil supply",
            }.get(ins_level, "Unknown"),
        },
        "cargo_throughput": {
            "today_dwt":     throughput.get("todayDWT"),
            "average_dwt":   throughput.get("averageDWT"),
            "percent_normal": throughput.get("percentOfNormal"),
            "last_7_days":   throughput.get("last7Days", []),
        },
        "diplomacy": {
            "status":   diplomacy.get("status"),
            "headline": diplomacy.get("headline"),
            "parties":  diplomacy.get("parties", []),
            "summary":  diplomacy.get("summary"),
        },
        "global_trade_impact": {
            "pct_world_oil_at_risk":       gti.get("percentOfWorldOilAtRisk"),
            "estimated_daily_cost_bn_usd": gti.get("estimatedDailyCostBillions"),
            "affected_regions":            gti.get("affectedRegions", []),
            "alternative_routes":          gti.get("alternativeRoutes", []),
            "spr_days":                    gti.get("supplyChainImpact", {}).get("sprStatusDays"),
        },
        "crisis_timeline":  timeline[-5:] if timeline else [],
        "latest_news":      news[0] if news else {},
        "revolut_energy_signals": {
            "trade_bias":          trade_bias,
            "hedge_tip":           hedge_tip,
            "revolut_energy_tickers": on_revolut_energy,
            "suggested_tools": [
                "revolut_sector_scan('energy')",
                "technical_signals('XLE')",
                "price_alert_check([{'ticker':'OXY','target':...,'direction':'above'}])",
            ],
        },
        "risk_summary": (
            f"{risk_emoji} Hormuz {strait.get('status','UNKNOWN')} | "
            f"Traffic: {pct_normal}% of normal | "
            f"Insurance: {ins_level.upper()} ({insurance.get('multiplier','?')}× normal) | "
            f"Brent: ${oil.get('brentPrice','?')} ({brent_chg:+.2f}%)"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 24 — stock_deep_data
# Source: Awesome-Finance-Skills / yfinance-data SKILL.md
# Exposes: income statement, balance sheet, cash flow, analyst targets,
#          institutional holders, insider transactions, dividends, news
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def stock_deep_data(
    ticker: str,
    data_type: str = "overview",
    quarterly: bool = False,
) -> dict:
    """
    Deep fundamental data via yfinance — balance sheet, income statement,
    cash flow, analyst ratings, institutional holders, insider transactions,
    dividends, and company news. Converted from finance-skills yfinance-data SKILL.md.

    Args:
        ticker:    Stock symbol e.g. "NVDA", "AAPL", "MSFT"
        data_type: What to fetch:
            "overview"       — company info, P/E, beta, sector, market cap
            "income"         — income statement (revenue, EPS, net income, EBITDA)
            "balance"        — balance sheet (assets, liabilities, equity, cash)
            "cashflow"       — cash flow statement (operating, investing, financing FCF)
            "analysts"       — analyst price targets + recommendations + upgrades
            "holders"        — institutional + insider holdings
            "insiders"       — insider buy/sell transactions (SEC Form 4)
            "dividends"      — dividend history + yield
            "news"           — latest company news
            "all"            — overview + analysts + key financial ratios
        quarterly: Use quarterly data instead of annual (for income/balance/cashflow)
    """
    try:
        ticker = validate_ticker(ticker)
    except ValueError as e:
        return {"error": str(e)}

    dt = data_type.lower().strip()
    valid = ["overview","income","balance","cashflow","analysts","holders","insiders","dividends","news","all"]
    if dt not in valid:
        return {"error": f"Unknown data_type '{dt}'", "valid": valid}

    on_revolut = ticker in REVOLUT_STOCKS

    def _fetch() -> dict:
        import yfinance as yf
        import pandas as pd

        tk   = yf.Ticker(ticker)
        info = tk.info or {}
        fi   = tk.fast_info

        def _safe_df(df) -> list:
            """Convert DataFrame to list of dicts, handle MultiIndex columns."""
            if df is None or (hasattr(df, 'empty') and df.empty):
                return []
            try:
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.droplevel(0, axis=1)
                df = df.reset_index()
                return df.head(4).to_dict(orient="records")
            except Exception:
                return []

        def _fmt_big(v) -> str:
            if v is None: return "N/A"
            try:
                v = float(v)
                if v >= 1e12: return f"${v/1e12:.2f}T"
                if v >= 1e9:  return f"${v/1e9:.2f}B"
                if v >= 1e6:  return f"${v/1e6:.2f}M"
                return f"${v:.2f}"
            except Exception:
                return str(v)

        result: dict = {"ticker": ticker, "revolut_available": on_revolut}

        if dt in ("overview", "all"):
            result["overview"] = {
                "name":          info.get("shortName", ticker),
                "sector":        info.get("sector"),
                "industry":      info.get("industry"),
                "country":       info.get("country"),
                "employees":     info.get("fullTimeEmployees"),
                "market_cap":    _fmt_big(info.get("marketCap")),
                "current_price": round(float(fi.last_price or 0), 2),
                "52w_high":      round(float(info.get("fiftyTwoWeekHigh", 0) or 0), 2),
                "52w_low":       round(float(info.get("fiftyTwoWeekLow", 0) or 0), 2),
                "trailing_pe":   round(float(info.get("trailingPE", 0) or 0), 2),
                "forward_pe":    round(float(info.get("forwardPE", 0) or 0), 2),
                "peg_ratio":     round(float(info.get("pegRatio", 0) or 0), 2),
                "pb_ratio":      round(float(info.get("priceToBook", 0) or 0), 2),
                "beta":          round(float(info.get("beta", 0) or 0), 2),
                "dividend_yield": f"{round((info.get('dividendYield') or 0)*100, 2)}%",
                "revenue_ttm":   _fmt_big(info.get("totalRevenue")),
                "ebitda":        _fmt_big(info.get("ebitda")),
                "profit_margin": f"{round((info.get('profitMargins') or 0)*100, 2)}%",
                "gross_margin":  f"{round((info.get('grossMargins') or 0)*100, 2)}%",
                "short_ratio":   info.get("shortRatio"),
                "description":   (info.get("longBusinessSummary") or "")[:400],
            }

        if dt == "income":
            stmt = tk.quarterly_income_stmt if quarterly else tk.income_stmt
            result["income_statement"] = _safe_df(stmt.T) if stmt is not None and not stmt.empty else []
            result["period"] = "quarterly" if quarterly else "annual"

        if dt == "balance":
            bs = tk.quarterly_balance_sheet if quarterly else tk.balance_sheet
            result["balance_sheet"] = _safe_df(bs.T) if bs is not None and not bs.empty else []
            result["period"] = "quarterly" if quarterly else "annual"

        if dt == "cashflow":
            cf = tk.quarterly_cashflow if quarterly else tk.cashflow
            result["cashflow"] = _safe_df(cf.T) if cf is not None and not cf.empty else []
            # FCF from latest
            try:
                op  = float(cf.loc["Operating Cash Flow"].iloc[0])
                cap = float(cf.loc["Capital Expenditure"].iloc[0])
                result["free_cash_flow_latest"] = _fmt_big(op + cap)
            except Exception:
                result["free_cash_flow_latest"] = "N/A"
            result["period"] = "quarterly" if quarterly else "annual"

        if dt in ("analysts", "all"):
            try:
                targets = tk.analyst_price_targets
                recs    = tk.recommendations
                upgrades= tk.upgrades_downgrades

                result["analyst_targets"] = {
                    "current":     round(float(targets.get("current", 0) or 0), 2),
                    "mean":        round(float(targets.get("mean", 0) or 0), 2),
                    "high":        round(float(targets.get("high", 0) or 0), 2),
                    "low":         round(float(targets.get("low", 0) or 0), 2),
                    "num_analysts": targets.get("numberOfAnalysts"),
                }
                if recs is not None and not recs.empty:
                    latest = recs.iloc[0]
                    result["recommendation"] = {
                        "period":   str(recs.index[0])[:10],
                        "strong_buy":  int(latest.get("strongBuy", 0)),
                        "buy":         int(latest.get("buy", 0)),
                        "hold":        int(latest.get("hold", 0)),
                        "sell":        int(latest.get("sell", 0)),
                        "strong_sell": int(latest.get("strongSell", 0)),
                    }
                if upgrades is not None and not upgrades.empty:
                    result["recent_upgrades"] = upgrades.head(5).reset_index().to_dict(orient="records")
            except Exception as e:
                result["analyst_targets"] = {"error": str(e)}

        if dt == "holders":
            try:
                inst = tk.institutional_holders
                result["institutional_holders"] = _safe_df(inst) if inst is not None else []
                mut  = tk.mutualfund_holders
                result["mutualfund_holders"] = _safe_df(mut)[:5] if mut is not None else []
            except Exception as e:
                result["holders_error"] = str(e)

        if dt == "insiders":
            try:
                insider = tk.insider_transactions
                result["insider_transactions"] = _safe_df(insider)[:10] if insider is not None else []
                insider_buys  = insider[insider["Shares"] > 0] if insider is not None and not insider.empty else None
                result["insider_summary"] = {
                    "total_transactions": len(insider) if insider is not None else 0,
                    "buys":  len(insider_buys) if insider_buys is not None else 0,
                    "sells": (len(insider) - len(insider_buys)) if insider is not None and insider_buys is not None else 0,
                    "signal": (
                        "🟢 Net buying — insider confidence" if insider_buys is not None and len(insider_buys) > len(insider)//2
                        else "🔴 Net selling" if insider is not None and len(insider) > 0
                        else "⚪ No recent insider activity"
                    ),
                }
            except Exception as e:
                result["insiders_error"] = str(e)

        if dt == "dividends":
            try:
                divs = tk.dividends
                result["dividend_history"] = []
                if divs is not None and not divs.empty:
                    for dt_idx, v in divs.tail(8).items():
                        result["dividend_history"].append({
                            "date": str(dt_idx)[:10],
                            "amount": round(float(v), 4),
                        })
                result["dividend_yield"]   = f"{round((info.get('dividendYield') or 0)*100, 2)}%"
                result["payout_ratio"]     = f"{round((info.get('payoutRatio') or 0)*100, 2)}%"
                result["ex_dividend_date"] = info.get("exDividendDate")
            except Exception as e:
                result["dividends_error"] = str(e)

        if dt == "news":
            try:
                news_items = tk.news or []
                result["news"] = [
                    {
                        "title":      item.get("title"),
                        "publisher":  item.get("publisher"),
                        "link":       item.get("link"),
                        "published":  item.get("providerPublishTime"),
                    }
                    for item in news_items[:8]
                ]
            except Exception as e:
                result["news_error"] = str(e)

        if dt == "all":
            # Add quick financial health summary
            pe  = float(info.get("trailingPE", 0) or 0)
            peg = float(info.get("pegRatio", 0) or 0)
            pm  = float(info.get("profitMargins", 0) or 0)
            result["health_score"] = {
                "valuation": "cheap" if pe < 15 else "fair" if pe < 30 else "expensive",
                "growth_adj": "undervalued" if 0 < peg < 1 else "fair" if peg < 2 else "expensive/no growth",
                "profitability": "high margin" if pm > 0.2 else "moderate" if pm > 0.05 else "thin/loss",
                "revolut_verdict": (
                    f"💳 {ticker} IS on Revolut — fundamental analysis supports "
                    + ("📈 accumulation" if pe < 25 and pm > 0.1 else "⏳ monitoring")
                    if on_revolut else
                    f"❌ {ticker} NOT on Revolut"
                ),
            }

        return result

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _fetch)
    except Exception as exc:
        return {"ticker": ticker, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 25 — options_chain
# Source: Awesome-Finance-Skills / yfinance-data SKILL.md (options chain section)
# Live options chain with Greeks approximation + IV surface + Revolut signal
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def options_chain(
    ticker: str,
    expiry_index: int = 0,
    option_type: str = "both",
    near_money_only: bool = True,
) -> dict:
    """
    Live options chain via yfinance — calls, puts, IV, open interest, volume.
    Converted from finance-skills yfinance-data SKILL.md options section.

    Args:
        ticker:         Stock symbol e.g. "AAPL", "NVDA", "SPY"
        expiry_index:   0 = nearest expiry, 1 = next, 2 = third, etc. (default 0)
        option_type:    "calls" | "puts" | "both" (default "both")
        near_money_only: Show only strikes within 10% of spot price (default True)
    """
    try:
        ticker = validate_ticker(ticker)
    except ValueError as e:
        return {"error": str(e)}

    on_revolut = ticker in REVOLUT_STOCKS

    def _fetch_chain():
        import yfinance as yf
        import pandas as pd, math

        tk      = yf.Ticker(ticker)
        spot    = round(float(tk.fast_info.last_price or 0), 2)
        expiries = tk.options

        if not expiries:
            return {"error": f"No options data available for {ticker}"}

        idx  = min(expiry_index, len(expiries) - 1)
        exp  = expiries[idx]
        chain = tk.option_chain(exp)

        def _process(df: pd.DataFrame, otype: str) -> list:
            if df is None or df.empty:
                return []
            df = df.copy()
            # near-money filter
            if near_money_only and spot > 0:
                df = df[
                    (df["strike"] >= spot * 0.90) &
                    (df["strike"] <= spot * 1.10)
                ]
            results = []
            for _, row in df.iterrows():
                strike = float(row.get("strike", 0))
                bid    = float(row.get("bid", 0) or 0)
                ask    = float(row.get("ask", 0) or 0)
                last   = float(row.get("lastPrice", 0) or 0)
                iv     = float(row.get("impliedVolatility", 0) or 0)
                oi     = int(row.get("openInterest", 0) or 0)
                vol    = int(row.get("volume", 0) or 0)
                itm    = bool(row.get("inTheMoney", False))

                # Moneyness
                if spot > 0:
                    mono_pct = round((spot - strike) / spot * 100, 1) if otype == "calls" else round((strike - spot) / spot * 100, 1)
                else:
                    mono_pct = 0.0

                results.append({
                    "strike":        strike,
                    "type":          otype,
                    "bid":           round(bid, 2),
                    "ask":           round(ask, 2),
                    "last":          round(last, 2),
                    "mid":           round((bid + ask) / 2, 2),
                    "iv_pct":        round(iv * 100, 1),
                    "open_interest": oi,
                    "volume":        vol,
                    "in_the_money":  itm,
                    "moneyness_pct": mono_pct,
                    "bid_ask_spread": round(ask - bid, 2),
                })
            return sorted(results, key=lambda x: x["strike"])

        calls_out = _process(chain.calls, "call") if option_type in ("calls","both") else []
        puts_out  = _process(chain.puts,  "put")  if option_type in ("puts","both")  else []

        all_opts = calls_out + puts_out
        # Max pain: strike with most OI both sides
        oi_by_strike = {}
        for o in all_opts:
            oi_by_strike[o["strike"]] = oi_by_strike.get(o["strike"], 0) + o["open_interest"]
        max_pain_strike = max(oi_by_strike, key=oi_by_strike.get) if oi_by_strike else None

        # IV surface summary
        if all_opts:
            ivs = [o["iv_pct"] for o in all_opts if o["iv_pct"] > 0]
            avg_iv = round(sum(ivs)/len(ivs), 1) if ivs else 0
            atm_iv = None
            for o in sorted(all_opts, key=lambda x: abs(x["strike"]-spot)):
                if o.get("iv_pct", 0) > 0:
                    atm_iv = o["iv_pct"]
                    break
        else:
            avg_iv = atm_iv = 0

        return {
            "ticker":        ticker,
            "spot":          spot,
            "expiry":        exp,
            "expiry_index":  idx,
            "available_expiries": list(expiries[:6]),
            "calls":         calls_out,
            "puts":          puts_out,
            "summary": {
                "total_calls":     len(calls_out),
                "total_puts":      len(puts_out),
                "max_pain_strike": max_pain_strike,
                "avg_iv_pct":      avg_iv,
                "atm_iv_pct":      atm_iv,
                "put_call_oi_ratio": (
                    round(sum(o["open_interest"] for o in puts_out) /
                          max(sum(o["open_interest"] for o in calls_out), 1), 2)
                    if puts_out and calls_out else None
                ),
                "iv_signal": (
                    "🔴 High IV — expensive premium, sell strategies favored" if atm_iv and atm_iv > 40 else
                    "🟡 Elevated IV — earnings/event likely priced in" if atm_iv and atm_iv > 25 else
                    "🟢 Low IV — cheap premium, buy strategies favored" if atm_iv else
                    "⚪ IV data unavailable"
                ),
            },
            "revolut_available": on_revolut,
            "revolut_note": (
                f"💳 {ticker} on Revolut — use IV signal for directional timing: "
                + ("high IV → expect big move" if atm_iv and atm_iv > 30 else "normal IV → steady state")
                if on_revolut else f"❌ {ticker} not on Revolut"
            ),
        }

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _fetch_chain)
    except Exception as exc:
        return {"ticker": ticker, "error": str(exc)}
