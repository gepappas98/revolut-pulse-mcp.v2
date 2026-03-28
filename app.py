#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  mcprice v2.1                                                    ║
║  Real-Time Price MCP Server for Claude/Cursor                    ║
║                                                                  ║
║  Stocks  → Yahoo Finance  (no key needed)                        ║
║  Crypto  → Binance Public API (no key needed)                    ║
║  Revolut → marks assets tradeable on Revolut                     ║
║                                                                  ║
║  v2.1 fixes:                                                     ║
║  ✅ /health endpoint (Railway healthcheck)                        ║
║  ✅ Lazy semaphore init (safe across event loops)                 ║
║  ✅ Config loaded from disk (config/*.json → fallback hardcoded)  ║
║  ✅ Dockerfile copies config/ directory                           ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

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
# FIX #1 — /health endpoint (Railway healthcheckPath requires 200 OK)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "service": "mcprice",
        "version": "2.1",
        "transport": os.environ.get("MCP_TRANSPORT", "stdio"),
    })

# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

_VALID_TICKER = re.compile(r"^[A-Z0-9\.\-\^]{1,12}$")


def validate_ticker(ticker: str) -> str:
    """Sanitise and validate a ticker symbol. Raises ValueError on bad input."""
    t = ticker.upper().strip()
    if not _VALID_TICKER.match(t):
        raise ValueError(
            f"Invalid ticker '{ticker}'. "
            "Use 1-12 uppercase letters/digits (e.g. AAPL, BTC, SPY)."
        )
    return t


# ─────────────────────────────────────────────────────────────────────────────
# TTL IN-MEMORY CACHE
# ─────────────────────────────────────────────────────────────────────────────

_cache: dict = {}


def ttl_cache(ttl: int = 30):
    """
    Async TTL decorator.
    ttl=30 for stocks (Yahoo ~15min delay anyway)
    ttl=10 for crypto (Binance is real-time, keep fresh)
    """
    def decorator(func):
        async def wrapper(*args):
            key = f"{func.__name__}:{args}"
            now = time.monotonic()
            if key in _cache:
                data, expiry = _cache[key]
                if now < expiry:
                    logger.debug("Cache HIT %s", key)
                    return data
            logger.debug("Cache MISS %s", key)
            result = await func(*args)
            _cache[key] = (result, now + ttl)
            return result
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# FIX #2 — RATE LIMITER (lazy init — safe across event loops in Python 3.10+)
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
# RETRY WITH EXPONENTIAL BACKOFF
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_with_retry(fn, *args, retries: int = 3, base_delay: float = 0.5):
    """Retry async fn up to retries times with exponential backoff."""
    last_exc = Exception("unknown")
    for attempt in range(retries):
        try:
            return await fn(*args)
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                wait = base_delay * (2 ** attempt)
                logger.warning(
                    "Retry %d/%d for %s — %s (wait %.1fs)",
                    attempt + 1, retries, getattr(fn, '__name__', str(fn)), exc, wait,
                )
                await asyncio.sleep(wait)
    raise last_exc


# ─────────────────────────────────────────────────────────────────────────────
# FIX #3 — CONFIG: load from config/*.json, fall back to hardcoded defaults
# ─────────────────────────────────────────────────────────────────────────────

_REVOLUT_STOCKS_DEFAULT: dict = {
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
    "GLD": "Gold ETF", "SLV": "Silver ETF", "TLT": "20yr Treasury ETF",
    "XLK": "Tech SPDR", "XLE": "Energy SPDR", "XLF": "Finance SPDR",
    "XLV": "Health SPDR", "XLI": "Industrial SPDR", "ITA": "Aerospace & Defense ETF",
    "ARKK": "ARK Innovation ETF", "VOO": "Vanguard S&P 500", "SOXX": "Semiconductor ETF",
    "DDOG": "Datadog", "NET": "Cloudflare", "CRWD": "CrowdStrike", "PANW": "Palo Alto",
    "ZS": "Zscaler", "FTNT": "Fortinet", "SNAP": "Snap", "PINS": "Pinterest",
    "ZM": "Zoom", "RBLX": "Roblox", "SPOT": "Spotify", "LYFT": "Lyft",
    "HUBS": "HubSpot", "TEAM": "Atlassian", "TWLO": "Twilio", "DOCU": "DocuSign",
    "OKTA": "Okta", "PATH": "UiPath", "U": "Unity", "AI": "C3.ai",
}

_REVOLUT_CRYPTO_DEFAULT: set = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "DOT", "AVAX", "MATIC", "LINK",
    "UNI", "ATOM", "LTC", "BCH", "XLM", "ALGO", "VET", "THETA", "FIL", "AAVE",
    "COMP", "SNX", "MKR", "SUSHI", "YFI", "BAT", "ZRX", "ENJ", "MANA", "SAND",
    "AXS", "CHZ", "GALA", "IMX", "APE", "NEAR", "FTM", "HBAR", "ICP", "ETC",
    "TRX", "EOS", "NEO", "DASH", "ZEC", "XMR", "QTUM", "ONT", "ZIL", "ICX",
    "BNB", "OP", "ARB", "SUI", "SEI", "TIA", "PYTH", "JUP",
}


def _load_config() -> tuple[dict, set]:
    """Load Revolut lists from config/*.json — fallback to hardcoded defaults."""
    config_dir = Path(__file__).parent / "config"
    stocks = dict(_REVOLUT_STOCKS_DEFAULT)
    crypto = set(_REVOLUT_CRYPTO_DEFAULT)

    stocks_file = config_dir / "revolut_stocks.json"
    if stocks_file.exists():
        try:
            data = json.loads(stocks_file.read_text())
            loaded = data.get("stocks", {})
            if loaded:
                stocks = loaded
                logger.info("Loaded %d stocks from config/revolut_stocks.json", len(stocks))
        except Exception as e:
            logger.warning("Could not load stocks config: %s — using defaults", e)

    crypto_file = config_dir / "revolut_crypto.json"
    if crypto_file.exists():
        try:
            data = json.loads(crypto_file.read_text())
            loaded = data.get("crypto", [])
            if loaded:
                crypto = set(loaded)
                logger.info("Loaded %d crypto from config/revolut_crypto.json", len(crypto))
        except Exception as e:
            logger.warning("Could not load crypto config: %s — using defaults", e)

    return stocks, crypto


REVOLUT_STOCKS, REVOLUT_CRYPTO = _load_config()

KNOWN_CRYPTO: set = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "DOT", "AVAX",
    "MATIC", "LINK", "UNI", "ATOM", "LTC", "BCH", "BNB", "OP", "ARB",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; mcprice/2.1; "
        "+https://github.com/gepappas98/revolut-pulse-mcp.v2)"
    )
}

# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER LAYER — Yahoo Finance
# ─────────────────────────────────────────────────────────────────────────────

@ttl_cache(ttl=30)
async def _yahoo_quote(ticker: str) -> dict:
    """Yahoo Finance v8 chart endpoint — cached 30 seconds."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    logger.info("Yahoo fetch: %s", ticker)
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
        r = await c.get(url, params={"interval": "1d", "range": "2d"}, headers=HEADERS)
        r.raise_for_status()
        data = r.json()
    meta = data["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice", 0.0)
    prev = meta.get("chartPreviousClose") or meta.get("previousClose", price)
    change = price - prev
    change_pct = (change / prev * 100) if prev else 0.0
    return {
        "ticker": ticker,
        "name": meta.get("longName") or meta.get("shortName") or ticker,
        "price": round(price, 4),
        "change": round(change, 4),
        "change_pct": round(change_pct, 2),
        "volume": meta.get("regularMarketVolume", 0),
        "market_cap": meta.get("marketCap"),
        "currency": meta.get("currency", "USD"),
        "source": "Yahoo Finance",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER LAYER — Binance
# ─────────────────────────────────────────────────────────────────────────────

@ttl_cache(ttl=10)
async def _binance_ticker(symbol: str) -> dict:
    """Binance 24h ticker — cached 10 seconds."""
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym += "USDT"
    logger.info("Binance fetch: %s", sym)
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbol": sym},
        )
        r.raise_for_status()
        d = r.json()
    base = sym.replace("USDT", "")
    return {
        "ticker": base,
        "pair": sym,
        "price": round(float(d["lastPrice"]), 6),
        "change": round(float(d["priceChange"]), 6),
        "change_pct": round(float(d["priceChangePercent"]), 2),
        "high_24h": round(float(d["highPrice"]), 6),
        "low_24h": round(float(d["lowPrice"]), 6),
        "volume_usd_24h": round(float(d["quoteVolume"]), 0),
        "currency": "USDT",
        "source": "Binance",
        "revolut_crypto": base in REVOLUT_CRYPTO,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK Yahoo → Binance
# ─────────────────────────────────────────────────────────────────────────────

async def _get_stock_price(ticker: str) -> dict:
    try:
        return await fetch_with_retry(limited_call, _yahoo_quote, ticker)
    except Exception as exc:
        logger.warning("Yahoo failed for %s (%s) — trying Binance fallback", ticker, exc)
        try:
            return await fetch_with_retry(limited_call, _binance_ticker, ticker)
        except Exception as exc2:
            logger.error("Both providers failed for %s: %s", ticker, exc2)
            return {"ticker": ticker, "error": str(exc2), "source": "all providers failed"}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _arrow(change_pct: float) -> str:
    if change_pct > 2:  return "🚀"
    if change_pct > 0:  return "📈"
    if change_pct < -2: return "🔻"
    if change_pct < 0:  return "📉"
    return "➡️"


def _enrich_stock(q: dict) -> dict:
    t = q.get("ticker", "")
    q["revolut_available"] = t in REVOLUT_STOCKS
    if t in REVOLUT_STOCKS:
        q["revolut_name"] = REVOLUT_STOCKS[t]
    cp = q.get("change_pct", 0)
    sign = "+" if cp >= 0 else ""
    q["emoji"] = _arrow(cp)
    q["summary"] = (
        f"{q['emoji']} {t}: ${q.get('price', '?')} ({sign}{cp}%)"
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
    Source: Yahoo Finance (30s cache). Falls back to Binance on failure.

    Args:
        ticker: Symbol e.g. "NVDA", "SPY", "LMT"
    """
    try:
        ticker = validate_ticker(ticker)
    except ValueError as e:
        return {"error": str(e)}
    quote = await _get_stock_price(ticker)
    return _enrich_stock(quote) if quote else {"ticker": ticker, "error": "No data"}


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2 — get_prices_bulk
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_prices_bulk(tickers: list) -> dict:
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

    quotes = await asyncio.gather(*[_get_stock_price(t) for t in validated])
    results = [_enrich_stock(q) for q in quotes if q]
    valid = [r for r in results if "error" not in r]
    return {
        "count": len(results),
        "results": results,
        "errors": errors,
        "gainers": sorted(valid, key=lambda x: x.get("change_pct", 0), reverse=True)[:3],
        "losers": sorted(valid, key=lambda x: x.get("change_pct", 0))[:3],
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
    except Exception as exc:
        logger.error("Binance failed for %s: %s", symbol, exc)
        return {"ticker": symbol, "error": str(exc)}
    if result:
        cp = result.get("change_pct", 0)
        sign = "+" if cp >= 0 else ""
        result["emoji"] = _arrow(cp)
        result["summary"] = (
            f"{result['emoji']} {symbol}: ${result.get('price', '?')} "
            f"({sign}{cp}% 24h)"
            + (" 💳 Revolut Crypto" if result.get("revolut_crypto") else "")
        )
    return result or {"symbol": symbol, "error": "Not found on Binance"}


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 4 — price_snapshot
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def price_snapshot(tickers: Optional[list] = None) -> dict:
    """
    Rich snapshot for a watchlist (stocks + crypto).
    Uses default watchlist if no tickers provided.
    """
    DEFAULT_STOCKS = ["NVDA", "AAPL", "MSFT", "TSLA", "LMT", "RTX", "GLD", "SPY", "META", "AMZN"]
    DEFAULT_CRYPTO = ["BTC", "ETH", "SOL", "XRP", "DOGE"]

    if tickers:
        upper = [t.upper().strip() for t in tickers[:25]]
        stock_list = [t for t in upper if t not in KNOWN_CRYPTO]
        crypto_list = [t for t in upper if t in KNOWN_CRYPTO]
    else:
        stock_list, crypto_list = DEFAULT_STOCKS, DEFAULT_CRYPTO

    stock_results, crypto_results = await asyncio.gather(
        asyncio.gather(*[_get_stock_price(t) for t in stock_list], return_exceptions=True),
        asyncio.gather(*[fetch_with_retry(limited_call, _binance_ticker, t) for t in crypto_list], return_exceptions=True),
    )

    stocks_out = [_enrich_stock(q) for q in stock_results if isinstance(q, dict) and "error" not in q]
    crypto_out = []
    for q in crypto_results:
        if isinstance(q, dict) and "error" not in q:
            q["emoji"] = _arrow(q.get("change_pct", 0))
            crypto_out.append(q)

    all_valid = stocks_out + crypto_out
    avg_chg = sum(x.get("change_pct", 0) for x in all_valid) / len(all_valid) if all_valid else 0
    top_gainer = max(all_valid, key=lambda x: x.get("change_pct", 0), default=None)
    top_loser  = min(all_valid, key=lambda x: x.get("change_pct", 0), default=None)

    return {
        "stocks": stocks_out,
        "crypto": crypto_out,
        "summary": {
            "total_assets": len(all_valid),
            "avg_change_pct": round(avg_chg, 2),
            "market_mood": "🟢 Risk-On" if avg_chg > 0 else "🔴 Risk-Off",
            "top_gainer": {"ticker": top_gainer["ticker"], "change_pct": top_gainer.get("change_pct")} if top_gainer else None,
            "top_loser":  {"ticker": top_loser["ticker"],  "change_pct": top_loser.get("change_pct")}  if top_loser  else None,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 5 — revolut_price_check
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def revolut_price_check(ticker: str) -> dict:
    """
    Combined: is it on Revolut? + current price.

    Args:
        ticker: Stock or ETF symbol e.g. "LMT", "GLD", "ITA"
    """
    try:
        ticker = validate_ticker(ticker)
    except ValueError as e:
        return {"error": str(e)}

    quote = await _get_stock_price(ticker)
    on_rev = ticker in REVOLUT_STOCKS

    if not quote or "error" in quote:
        return {
            "ticker": ticker,
            "revolut_available": on_rev,
            "price": None,
            "quick_verdict": (
                f"{'✅' if on_rev else '❌'} {ticker} "
                f"{'on Revolut' if on_rev else 'NOT on Revolut'} — price unavailable"
            ),
        }

    cp = quote.get("change_pct", 0)
    sign = "+" if cp >= 0 else ""
    name = REVOLUT_STOCKS.get(ticker, quote.get("name", ticker))
    return {
        "ticker": ticker,
        "name": name,
        "revolut_available": on_rev,
        "price": quote["price"],
        "change_pct": cp,
        "volume": quote.get("volume"),
        "currency": quote.get("currency", "USD"),
        "emoji": _arrow(cp),
        "quick_verdict": (
            f"{'✅ 💳' if on_rev else '❌'} {ticker} ({name}): "
            f"${quote['price']} ({sign}{cp}%) "
            + ("— available on Revolut 💳" if on_rev else "— NOT on Revolut")
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 6 — crypto_top_movers
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def crypto_top_movers(
    limit: int = 10,
    min_volume_usd: float = 10_000_000,
) -> dict:
    """
    Top crypto gainers & losers over 24h from Binance (no API key).

    Args:
        limit: Results per category (default 10)
        min_volume_usd: Minimum 24h USD volume (default $10M)
    """
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://api.binance.com/api/v3/ticker/24hr")
            r.raise_for_status()
            all_tickers = r.json()
    except Exception as exc:
        logger.error("Binance top-movers failed: %s", exc)
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
        chg = float(t.get("priceChangePercent", 0))
        filtered.append({
            "ticker": base,
            "price": round(float(t["lastPrice"]), 6),
            "change_pct": round(chg, 2),
            "volume_usd_24h": round(vol, 0),
            "revolut": base in REVOLUT_CRYPTO,
            "emoji": _arrow(chg),
        })

    return {
        "gainers": sorted(filtered, key=lambda x: x["change_pct"], reverse=True)[:limit],
        "losers": sorted(filtered, key=lambda x: x["change_pct"])[:limit],
        "revolut_movers": [
            x for x in sorted(filtered, key=lambda x: abs(x["change_pct"]), reverse=True)
            if x["revolut"]
        ][:limit],
        "total_pairs_scanned": len(filtered),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        port = int(os.environ.get("PORT", "8080"))
        logger.info("mcprice v2.1 starting on http://0.0.0.0:%d/mcp  health→/health", port)
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        logger.info("mcprice v2.1 starting (stdio mode)")
        mcp.run(transport="stdio")
