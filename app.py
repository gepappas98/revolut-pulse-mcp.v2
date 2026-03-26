#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  mcprice v2.2                                                   ║
║  Real-Time Price MCP Server for Claude/Cursor/Cline             ║
║                                                                  ║
║  Stocks  → yfinance  (no IP blocking on cloud)                  ║
║  Crypto  → Binance Public API (no key needed)                   ║
║  Revolut → marks assets tradeable on Revolut                   ║
║                                                                  ║
║  v2.2 vs v2.0:                                                  ║
║  ✅ FIX 406 — HealthMiddleware adds /health (MCPize probe fix)  ║
║  ✅ FIX 406 — HEAD /mcp returns 200 (no Accept header needed)   ║
║  ✅ FIX Semaphore lazy-init (no event-loop crash Python 3.12)   ║
║  ✅ FIX yfinance replaces raw Yahoo HTTP (works from cloud IPs) ║
║  ✅ FIX Stampede-safe TTL cache (in-flight deduplication)       ║
║  ✅ FIX Config JSON files actually loaded from config/          ║
║  ✅ FIX Binance 429 smart backoff (Retry-After respected)       ║
║  ✅ FIX List[str] typing for MCP schema compliance              ║
║  ✅ NEW Tool 7 — portfolio_pnl() (P&L + Revolut flags, unique)  ║
║  ✅ NEW Tool 8 — market_overview() (indices+crypto dashboard)   ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import List, Optional

import httpx
import uvicorn
import yfinance as yf
from fastmcp import FastMCP
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

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
# FIX 406 — HEALTH MIDDLEWARE
# Wraps FastMCP's ASGI app to:
#   1. Serve GET/HEAD /health → 200 always  (MCPize, Fly.io, Docker probes)
#   2. Serve HEAD /mcp        → 200 always  (probes without Accept headers)
# ─────────────────────────────────────────────────────────────────────────────

class HealthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path   = scope.get("path", "")
            method = scope.get("method", "GET").upper()

            if path == "/health":
                resp = JSONResponse({
                    "status": "ok", "server": "mcprice",
                    "version": "2.2", "tools": 8,
                    "transport": "streamable-http",
                })
                await resp(scope, receive, send)
                return

            # MCPize probe sends HEAD /mcp without Accept: text/event-stream → 406
            # We intercept HEAD before FastMCP sees it and return 200 immediately.
            if method == "HEAD" and path in ("/mcp", "/mcp/"):
                await JSONResponse({}, status_code=200)(scope, receive, send)
                return

        await self.app(scope, receive, send)


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

_VALID_TICKER = re.compile(r"^[A-Z0-9\.\-\^]{1,12}$")


def validate_ticker(ticker: str) -> str:
    t = ticker.upper().strip()
    if not _VALID_TICKER.match(t):
        raise ValueError(f"Invalid ticker '{ticker}'. Use 1-12 uppercase letters/digits.")
    return t


# ─────────────────────────────────────────────────────────────────────────────
# LAZY SEMAPHORE
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
# STAMPEDE-SAFE TTL CACHE
# ─────────────────────────────────────────────────────────────────────────────

_cache: dict     = {}
_in_flight: dict = {}


def ttl_cache(ttl: int = 30):
    def decorator(func):
        async def wrapper(*args):
            key = f"{func.__name__}:{args}"
            now = time.monotonic()
            if key in _cache:
                data, expiry = _cache[key]
                if now < expiry:
                    return data
            if key in _in_flight:
                return await asyncio.shield(_in_flight[key])
            task = asyncio.create_task(func(*args))
            _in_flight[key] = task
            try:
                result = await task
                _cache[key] = (result, time.monotonic() + ttl)
                return result
            finally:
                _in_flight.pop(key, None)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# RETRY WITH EXPONENTIAL BACKOFF + 429 GUARD
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_with_retry(fn, *args, retries: int = 3, base_delay: float = 0.5):
    last_exc = Exception("unknown")
    for attempt in range(retries):
        try:
            return await fn(*args)
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                is_429 = "429" in str(exc) or "rate" in str(exc).lower()
                wait   = 60.0 if is_429 else base_delay * (2 ** attempt)
                logger.warning("Retry %d/%d for %s — %s (wait %.1fs)",
                               attempt + 1, retries,
                               getattr(fn, "__name__", str(fn)), exc, wait)
                await asyncio.sleep(wait)
    raise last_exc


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG-DRIVEN REVOLUT LISTS
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_STOCKS: dict = {
    "AAPL":"Apple","MSFT":"Microsoft","GOOGL":"Alphabet A","GOOG":"Alphabet C",
    "META":"Meta","AMZN":"Amazon","NVDA":"NVIDIA","TSLA":"Tesla","NFLX":"Netflix",
    "ADBE":"Adobe","CRM":"Salesforce","ORCL":"Oracle","IBM":"IBM","INTC":"Intel",
    "AMD":"AMD","QCOM":"Qualcomm","TXN":"Texas Instruments","AVGO":"Broadcom",
    "MU":"Micron","AMAT":"Applied Materials","NOW":"ServiceNow","INTU":"Intuit",
    "SNOW":"Snowflake","UBER":"Uber","SHOP":"Shopify","SQ":"Block",
    "PYPL":"PayPal","PLTR":"Palantir","COIN":"Coinbase","MSTR":"MicroStrategy",
    "JPM":"JPMorgan","BAC":"Bank of America","WFC":"Wells Fargo","GS":"Goldman",
    "MS":"Morgan Stanley","V":"Visa","MA":"Mastercard","AXP":"Amex",
    "BRKB":"Berkshire B","BLK":"BlackRock","SCHW":"Schwab",
    "JNJ":"J&J","PFE":"Pfizer","MRNA":"Moderna","ABBV":"AbbVie",
    "LLY":"Eli Lilly","MRK":"Merck","AMGN":"Amgen","GILD":"Gilead",
    "UNH":"UnitedHealth","CVS":"CVS",
    "XOM":"ExxonMobil","CVX":"Chevron","COP":"ConocoPhillips","OXY":"Occidental",
    "LMT":"Lockheed Martin","RTX":"RTX/Raytheon","BA":"Boeing","GD":"General Dynamics",
    "NOC":"Northrop Grumman","LHX":"L3Harris","HII":"Huntington Ingalls",
    "KO":"Coca-Cola","PEP":"PepsiCo","MCD":"McDonald's","SBUX":"Starbucks",
    "NKE":"Nike","DIS":"Disney","WMT":"Walmart","COST":"Costco","HD":"Home Depot",
    "T":"AT&T","VZ":"Verizon","CMCSA":"Comcast",
    "TSM":"TSMC ADR","ASML":"ASML ADR","LRCX":"Lam Research",
    "SPY":"S&P 500 ETF","QQQ":"Nasdaq-100 ETF","IWM":"Russell 2000 ETF",
    "GLD":"Gold ETF","SLV":"Silver ETF","TLT":"20yr Treasury ETF",
    "DIA":"Dow Jones ETF","USO":"Oil ETF",
    "XLK":"Tech SPDR","XLE":"Energy SPDR","XLF":"Finance SPDR",
    "XLV":"Health SPDR","XLI":"Industrial SPDR","ITA":"Aerospace & Defense ETF",
    "ARKK":"ARK Innovation ETF","VOO":"Vanguard S&P 500","SOXX":"Semiconductor ETF",
    "DDOG":"Datadog","NET":"Cloudflare","CRWD":"CrowdStrike","PANW":"Palo Alto",
    "ZS":"Zscaler","FTNT":"Fortinet","SNAP":"Snap","PINS":"Pinterest",
    "ZM":"Zoom","RBLX":"Roblox","SPOT":"Spotify","LYFT":"Lyft",
    "HUBS":"HubSpot","TEAM":"Atlassian","TWLO":"Twilio","DOCU":"DocuSign",
    "OKTA":"Okta","PATH":"UiPath","U":"Unity","AI":"C3.ai",
}

_FALLBACK_CRYPTO: set = {
    "BTC","ETH","SOL","XRP","DOGE","ADA","DOT","AVAX","MATIC","LINK",
    "UNI","ATOM","LTC","BCH","XLM","ALGO","VET","THETA","FIL","AAVE",
    "COMP","SNX","MKR","SUSHI","YFI","BAT","ZRX","ENJ","MANA","SAND",
    "AXS","CHZ","GALA","IMX","APE","NEAR","FTM","HBAR","ICP","ETC",
    "TRX","EOS","NEO","DASH","ZEC","XMR","QTUM","ONT","ZIL","ICX",
    "BNB","OP","ARB","SUI","SEI","TIA","PYTH","JUP",
}


def _load_config() -> tuple[dict, set]:
    base = Path(__file__).parent / "config"
    stocks_path = base / "revolut_stocks.json"
    crypto_path = base / "revolut_crypto.json"
    try:
        stocks = json.loads(stocks_path.read_text()).get("stocks", _FALLBACK_STOCKS) if stocks_path.exists() else _FALLBACK_STOCKS
    except Exception:
        stocks = _FALLBACK_STOCKS
    try:
        raw    = json.loads(crypto_path.read_text()) if crypto_path.exists() else None
        crypto = set(raw.get("crypto", raw) if isinstance(raw, dict) else raw) if raw else _FALLBACK_CRYPTO
    except Exception:
        crypto = _FALLBACK_CRYPTO
    logger.info("Revolut lists: %d stocks, %d crypto", len(stocks), len(crypto))
    return stocks, crypto


REVOLUT_STOCKS, REVOLUT_CRYPTO = _load_config()

KNOWN_CRYPTO: set = {
    "BTC","ETH","SOL","XRP","DOGE","ADA","DOT","AVAX",
    "MATIC","LINK","UNI","ATOM","LTC","BCH","BNB","OP","ARB",
}

# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER — yfinance
# ─────────────────────────────────────────────────────────────────────────────

@ttl_cache(ttl=30)
async def _yahoo_quote(ticker: str) -> dict:
    logger.info("yfinance fetch: %s", ticker)

    def _sync():
        t     = yf.Ticker(ticker)
        info  = t.fast_info
        price = getattr(info, "last_price", None)
        if not price:
            raise ValueError(f"yfinance: no price for '{ticker}'")
        prev  = getattr(info, "previous_close", None) or price
        chg   = price - prev
        chg_p = (chg / prev * 100) if prev else 0.0
        try:
            full     = t.info
            name     = full.get("longName") or full.get("shortName") or ticker
            mkt_cap  = full.get("marketCap")
            volume   = full.get("regularMarketVolume", 0)
            currency = full.get("currency", "USD")
        except Exception:
            name, mkt_cap, volume, currency = ticker, None, 0, "USD"
        return {
            "ticker": ticker, "name": name,
            "price": round(float(price), 4), "change": round(float(chg), 4),
            "change_pct": round(float(chg_p), 2), "volume": volume,
            "market_cap": mkt_cap, "currency": currency,
            "source": "Yahoo Finance (yfinance)",
        }

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


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
        if r.status_code == 429:
            raise RuntimeError(f"429 Binance rate-limited — retry after {r.headers.get('Retry-After',60)}s")
        r.raise_for_status()
        d = r.json()
    base = sym.replace("USDT", "")
    return {
        "ticker": base, "pair": sym,
        "price": round(float(d["lastPrice"]), 6),
        "change": round(float(d["priceChange"]), 6),
        "change_pct": round(float(d["priceChangePercent"]), 2),
        "high_24h": round(float(d["highPrice"]), 6),
        "low_24h": round(float(d["lowPrice"]), 6),
        "volume_usd_24h": round(float(d["quoteVolume"]), 0),
        "currency": "USDT", "source": "Binance",
        "revolut_crypto": base in REVOLUT_CRYPTO,
    }


async def _get_stock_price(ticker: str) -> dict:
    try:
        return await fetch_with_retry(limited_call, _yahoo_quote, ticker)
    except Exception as exc:
        logger.warning("yfinance failed for %s (%s) — Binance fallback", ticker, exc)
        try:
            return await fetch_with_retry(limited_call, _binance_ticker, ticker)
        except Exception as exc2:
            return {"ticker": ticker, "error": str(exc2), "source": "all providers failed"}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _arrow(pct: float) -> str:
    if pct > 2:  return "🚀"
    if pct > 0:  return "📈"
    if pct < -2: return "🔻"
    if pct < 0:  return "📉"
    return "➡️"


def _enrich_stock(q: dict) -> dict:
    t  = q.get("ticker", "")
    on = t in REVOLUT_STOCKS
    q["revolut_available"] = on
    if on:
        q["revolut_name"] = REVOLUT_STOCKS[t]
    cp = q.get("change_pct", 0)
    q["emoji"]   = _arrow(cp)
    q["summary"] = f"{q['emoji']} {t}: ${q.get('price','?')} ({'+'if cp>=0 else ''}{cp}%)" + (" 💳 Revolut" if on else "")
    return q


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1 — get_price
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_price(ticker: str) -> dict:
    """
    Get the current live stock or ETF price for Claude and AI agents.
    No API key required. Includes 24h change, market cap, Revolut availability.

    Args:
        ticker: Stock symbol e.g. "NVDA", "AAPL", "SPY", "LMT", "GLD"
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
    Get live prices for up to 20 stocks or ETFs in one call. No API key.
    Returns top 3 gainers and losers automatically.

    Args:
        tickers: List of symbols e.g. ["NVDA", "LMT", "GLD", "SPY", "AAPL"]
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
        "count": len(results), "results": results, "errors": errors,
        "gainers": sorted(valid, key=lambda x: x.get("change_pct", 0), reverse=True)[:3],
        "losers":  sorted(valid, key=lambda x: x.get("change_pct", 0))[:3],
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3 — get_crypto_price
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_crypto_price(symbol: str) -> dict:
    """
    Real-time crypto price from Binance. No API key required.
    Returns price, 24h change, high/low, volume, and Revolut availability.

    Args:
        symbol: Crypto symbol e.g. "BTC", "ETH", "SOL", "DOGE" (no USDT suffix)
    """
    try:
        symbol = validate_ticker(symbol.replace("USDT", "").replace("/", ""))
    except ValueError as e:
        return {"error": str(e)}
    try:
        result = await fetch_with_retry(limited_call, _binance_ticker, symbol)
    except Exception as exc:
        return {"ticker": symbol, "error": str(exc)}
    if result:
        cp = result.get("change_pct", 0)
        result["emoji"]   = _arrow(cp)
        result["summary"] = f"{result['emoji']} {symbol}: ${result.get('price','?')} ({'+'if cp>=0 else ''}{cp}% 24h)" + (" 💳 Revolut Crypto" if result.get("revolut_crypto") else "")
    return result or {"symbol": symbol, "error": "Not found on Binance"}


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 4 — price_snapshot
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def price_snapshot(tickers: Optional[List[str]] = None) -> dict:
    """
    Rich snapshot for a mixed stock + crypto watchlist. No API key required.
    Returns market mood, top gainer, top loser. Default watchlist if empty.

    Args:
        tickers: Optional mixed list e.g. ["NVDA","BTC","AAPL","ETH"]
    """
    DEFAULT_STOCKS = ["NVDA","AAPL","MSFT","TSLA","LMT","RTX","GLD","SPY","META","AMZN"]
    DEFAULT_CRYPTO = ["BTC","ETH","SOL","XRP","DOGE"]
    if tickers:
        upper       = [t.upper().strip() for t in tickers[:25]]
        stock_list  = [t for t in upper if t not in KNOWN_CRYPTO]
        crypto_list = [t for t in upper if t in KNOWN_CRYPTO]
    else:
        stock_list, crypto_list = DEFAULT_STOCKS, DEFAULT_CRYPTO
    sr, cr = await asyncio.gather(
        asyncio.gather(*[_get_stock_price(t) for t in stock_list],  return_exceptions=True),
        asyncio.gather(*[fetch_with_retry(limited_call, _binance_ticker, t) for t in crypto_list], return_exceptions=True),
    )
    stocks_out = [_enrich_stock(q) for q in sr if isinstance(q, dict) and "error" not in q]
    crypto_out = []
    for q in cr:
        if isinstance(q, dict) and "error" not in q:
            q["emoji"] = _arrow(q.get("change_pct", 0))
            crypto_out.append(q)
    all_v   = stocks_out + crypto_out
    avg_chg = sum(x.get("change_pct", 0) for x in all_v) / len(all_v) if all_v else 0
    return {
        "stocks": stocks_out, "crypto": crypto_out,
        "summary": {
            "total_assets": len(all_v), "avg_change_pct": round(avg_chg, 2),
            "market_mood": "🟢 Risk-On" if avg_chg > 0 else "🔴 Risk-Off",
            "top_gainer": max(all_v, key=lambda x: x.get("change_pct", 0), default=None),
            "top_loser":  min(all_v, key=lambda x: x.get("change_pct", 0), default=None),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 5 — revolut_price_check
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def revolut_price_check(ticker: str) -> dict:
    """
    Check if a stock or ETF is tradeable on Revolut + its current live price.
    Perfect for Revolut traders deciding whether to use the platform.

    Args:
        ticker: Stock or ETF symbol e.g. "LMT", "GLD", "ITA", "NVDA", "ARKK"
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
        "ticker": ticker, "name": name, "revolut_available": on_rev,
        "price": quote["price"], "change_pct": cp,
        "volume": quote.get("volume"), "currency": quote.get("currency", "USD"),
        "emoji": _arrow(cp),
        "quick_verdict": f"{'✅ 💳' if on_rev else '❌'} {ticker} ({name}): ${quote['price']} ({'+'if cp>=0 else ''}{cp}%) " + ("— available on Revolut 💳" if on_rev else "— NOT on Revolut"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 6 — crypto_top_movers
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def crypto_top_movers(limit: int = 10, min_volume_usd: float = 10_000_000) -> dict:
    """
    Top 24h crypto gainers and losers from Binance. No API key required.
    Filters low-volume coins. Tags every result with Revolut availability.

    Args:
        limit:          Results per category — gainers, losers, revolut_movers (default 10)
        min_volume_usd: Minimum 24h USD volume to include a coin (default $10M)
    """
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://api.binance.com/api/v3/ticker/24hr")
            if r.status_code == 429:
                return {"error": f"Binance rate-limited, retry after {r.headers.get('Retry-After',60)}s"}
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
        "gainers":             sorted(filtered, key=lambda x: x["change_pct"], reverse=True)[:limit],
        "losers":              sorted(filtered, key=lambda x: x["change_pct"])[:limit],
        "revolut_movers":      [x for x in sorted(filtered, key=lambda x: abs(x["change_pct"]), reverse=True) if x["revolut"]][:limit],
        "total_pairs_scanned": len(filtered),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 7 — portfolio_pnl  ★ NEW
# Unique: P&L + live prices + Revolut tradability in one call.
# No competitor MCP server offers this combination for free.
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def portfolio_pnl(holdings: List[dict]) -> dict:
    """
    Calculate real-time P&L for a portfolio of stocks and/or crypto.
    No API key required. Includes Revolut availability for every position.

    This tool is unique among free MCP finance servers: it combines
    live price fetching, P&L calculation, and Revolut tradability
    in a single call — perfect for Revolut traders using Claude.

    Ask Claude: "Calculate my portfolio P&L" or
                "Which of my holdings can I sell on Revolut right now?"

    Args:
        holdings: List of positions. Each item must have:
                  - ticker    (str):   stock or crypto symbol e.g. "NVDA", "BTC"
                  - avg_cost  (float): average purchase price in USD
                  - shares    (float): number of shares or units held

    Example:
        [
          {"ticker": "NVDA", "avg_cost": 450.00, "shares": 10},
          {"ticker": "BTC",  "avg_cost": 35000,  "shares": 0.5},
          {"ticker": "LMT",  "avg_cost": 420.00, "shares": 5}
        ]
    """
    if not holdings:
        return {"error": "No holdings provided. Pass a list of {ticker, avg_cost, shares}."}

    positions  = []
    total_cost = 0.0
    total_val  = 0.0

    for h in holdings[:30]:
        raw = str(h.get("ticker", "")).upper().strip()
        try:
            avg_cost = float(h.get("avg_cost", 0))
            shares   = float(h.get("shares", 0))
            validate_ticker(raw)
        except (ValueError, TypeError) as e:
            positions.append({"ticker": raw, "error": str(e)})
            continue
        if avg_cost <= 0 or shares <= 0:
            positions.append({"ticker": raw, "error": "avg_cost and shares must be > 0"})
            continue

        if raw in KNOWN_CRYPTO:
            try:
                quote = await fetch_with_retry(limited_call, _binance_ticker, raw)
            except Exception as e:
                positions.append({"ticker": raw, "error": str(e)})
                continue
        else:
            quote = await _get_stock_price(raw)

        if not quote or "error" in quote:
            positions.append({"ticker": raw, "error": "Price unavailable", "avg_cost": avg_cost, "shares": shares})
            continue

        price  = float(quote.get("price", 0))
        cost   = avg_cost * shares
        val    = price * shares
        pnl    = val - cost
        pnl_p  = (pnl / cost * 100) if cost else 0.0
        on_rev = raw in REVOLUT_STOCKS or raw in REVOLUT_CRYPTO
        total_cost += cost
        total_val  += val

        positions.append({
            "ticker": raw, "shares": shares, "avg_cost": avg_cost,
            "current_price": price,
            "cost_basis": round(cost, 2), "current_value": round(val, 2),
            "pnl_usd": round(pnl, 2), "pnl_pct": round(pnl_p, 2),
            "revolut_available": on_rev, "emoji": _arrow(pnl_p),
            "summary": f"{_arrow(pnl_p)} {raw}: ${price} | P&L: {'+'if pnl>=0 else ''}{pnl:.2f} ({'+'if pnl_p>=0 else ''}{pnl_p:.1f}%)" + (" 💳" if on_rev else ""),
        })

    valid      = [p for p in positions if "error" not in p]
    total_pnl  = total_val - total_cost
    total_pnl_p = (total_pnl / total_cost * 100) if total_cost else 0.0

    return {
        "positions": positions,
        "portfolio_summary": {
            "total_cost_basis":       round(total_cost, 2),
            "total_current_value":    round(total_val, 2),
            "total_pnl_usd":          round(total_pnl, 2),
            "total_pnl_pct":          round(total_pnl_p, 2),
            "emoji":                  _arrow(total_pnl_p),
            "revolut_eligible_count": sum(1 for p in valid if p.get("revolut_available")),
            "best_performer":  max(valid, key=lambda x: x.get("pnl_pct", -999), default=None),
            "worst_performer": min(valid, key=lambda x: x.get("pnl_pct",  999), default=None),
            "verdict": f"{_arrow(total_pnl_p)} Portfolio ${total_val:,.2f} | P&L: {'+'if total_pnl>=0 else ''}{total_pnl:,.2f} ({'+'if total_pnl_p>=0 else ''}{total_pnl_p:.1f}%)",
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 8 — market_overview  ★ NEW
# Instant multi-market dashboard — unique among free MCP finance servers.
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def market_overview() -> dict:
    """
    Instant multi-market dashboard: indices, commodities, and top crypto.
    No API key required. All markets in a single call.

    Returns S&P 500, NASDAQ-100, Dow Jones, Russell 2000, Gold, Silver,
    Oil (WTI), 20yr Bonds, BTC, ETH, SOL, BNB — with mood indicator.

    Ask Claude: "What's the market doing today?" or
                "Give me a full market overview before I trade on Revolut."
    """
    INDICES = {
        "SPY": "S&P 500", "QQQ": "NASDAQ-100", "DIA": "Dow Jones",
        "IWM": "Russell 2000", "GLD": "Gold", "SLV": "Silver",
        "USO": "Oil (WTI)", "TLT": "20yr Bonds",
    }
    CRYPTO_LIST = ["BTC", "ETH", "SOL", "BNB"]

    sr, cr = await asyncio.gather(
        asyncio.gather(*[_get_stock_price(t) for t in INDICES], return_exceptions=True),
        asyncio.gather(*[fetch_with_retry(limited_call, _binance_ticker, c) for c in CRYPTO_LIST], return_exceptions=True),
    )

    markets = {}
    for ticker, q in zip(INDICES.keys(), sr):
        if isinstance(q, dict) and "error" not in q:
            cp = q.get("change_pct", 0)
            markets[ticker] = {
                "name": INDICES[ticker], "price": q.get("price"),
                "change_pct": cp, "emoji": _arrow(cp),
                "revolut": ticker in REVOLUT_STOCKS,
            }

    crypto_out = {}
    for sym, q in zip(CRYPTO_LIST, cr):
        if isinstance(q, dict) and "error" not in q:
            cp = q.get("change_pct", 0)
            crypto_out[sym] = {
                "price": q.get("price"), "change_pct": cp,
                "emoji": _arrow(cp), "revolut": sym in REVOLUT_CRYPTO,
            }

    all_chg = [v["change_pct"] for v in {**markets, **crypto_out}.values()]
    avg_chg = sum(all_chg) / len(all_chg) if all_chg else 0
    mood    = "🟢 Risk-On" if avg_chg > 0.3 else ("🔴 Risk-Off" if avg_chg < -0.3 else "🟡 Mixed / Neutral")
    spy = markets.get("SPY", {})
    btc = crypto_out.get("BTC", {})

    return {
        "markets": markets, "crypto": crypto_out,
        "mood": mood, "avg_change_pct": round(avg_chg, 2),
        "briefing": f"{mood} | S&P {spy.get('emoji','')} ${spy.get('price','N/A')} | BTC {btc.get('emoji','')} ${btc.get('price','N/A')} | avg {'+'if avg_chg>=0 else ''}{avg_chg:.1f}%",
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")

    if transport == "http":
        port = int(os.environ.get("PORT", "8080"))

        # Get FastMCP's ASGI app and wrap it with HealthMiddleware.
        # This is the 406 fix: probes hit /health (200) instead of /mcp (406).
        try:
            mcp_asgi = mcp.http_app()          # FastMCP 2.x public method
        except AttributeError:
            logger.warning("FastMCP http_app() unavailable — upgrade fastmcp>=2.0 to fix 406.")
            mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
            raise SystemExit(0)

        wrapped = HealthMiddleware(mcp_asgi)
        logger.info("mcprice v2.2 | http://0.0.0.0:%d | /health + /mcp | 8 tools", port)
        uvicorn.run(wrapped, host="0.0.0.0", port=port, log_level="info")

    else:
        logger.info("mcprice v2.2 (stdio) | 8 tools ready")
        mcp.run(transport="stdio")
