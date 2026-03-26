#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║            mcprice — Programmatic SEO Generator  v3.0           ║
║                                                                  ║
║  Generates 1200+ static HTML pages + sitemap                    ║
║  NEW in v3.0:                                                    ║
║   • Signal pages: /signals/{ticker} (RSI/MACD)                  ║
║   • Fear & Greed landing page                                    ║
║   • Insider flow landing page                                    ║
║   • Earnings calendar landing page                               ║
║   • Funding rates landing page                                   ║
║   • 50+ new keyword-targeted Revolut pages                       ║
║                                                                  ║
║  Usage:                                                          ║
║    python seo/generator.py --base-url https://mcprice.fly.dev   ║
║    python seo/generator.py --no-live  (fast, no price fetch)    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import asyncio
import json
import os
from datetime import datetime, UTC
from pathlib import Path

import httpx

# ─── paths ────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
OUT_DIR    = ROOT / "seo" / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)
(OUT_DIR / "price").mkdir(exist_ok=True)
(OUT_DIR / "signals").mkdir(exist_ok=True)

# ─── config ───────────────────────────────────────────────────────────────────
with open(CONFIG_DIR / "revolut_stocks.json") as f:
    REVOLUT_STOCKS: dict = json.load(f)["stocks"]

with open(CONFIG_DIR / "revolut_crypto.json") as f:
    REVOLUT_CRYPTO: set = set(json.load(f)["crypto"])

# ─── keyword pages (v3.0 expanded) ───────────────────────────────────────────
STATIC_PAGES = [
    # Revolut core
    ("revolut-stocks-list",          "Full List of Stocks Available on Revolut 2026"),
    ("revolut-crypto-list",          "All Cryptocurrencies Available on Revolut 2026"),
    ("revolut-etf-list",             "ETFs Available on Revolut — Complete List 2026"),
    ("revolut-stock-limits",         "Revolut Stock Trading Limits & Fees Explained"),
    ("revolut-vs-trading212",        "Revolut vs Trading 212: Stocks & Crypto Comparison"),
    ("revolut-ipo-2026",             "Revolut IPO 2026: Date, Valuation, How to Invest"),
    # Is X on Revolut? (high volume, low competition)
    ("is-nvda-on-revolut",           "Is NVIDIA (NVDA) Available on Revolut?"),
    ("is-tsla-on-revolut",           "Is Tesla (TSLA) Available on Revolut?"),
    ("is-aapl-on-revolut",           "Is Apple (AAPL) Available on Revolut?"),
    ("is-msft-on-revolut",           "Is Microsoft (MSFT) Available on Revolut?"),
    ("is-meta-on-revolut",           "Is Meta (META) Available on Revolut?"),
    ("is-lmt-on-revolut",            "Is Lockheed Martin (LMT) Available on Revolut?"),
    ("is-pltr-on-revolut",           "Is Palantir (PLTR) Available on Revolut?"),
    ("is-coin-on-revolut",           "Is Coinbase (COIN) Available on Revolut?"),
    ("is-btc-on-revolut",            "Is Bitcoin (BTC) Available on Revolut?"),
    ("is-eth-on-revolut",            "Is Ethereum (ETH) Available on Revolut?"),
    ("is-sol-on-revolut",            "Is Solana (SOL) Available on Revolut?"),
    ("is-xrp-on-revolut",            "Is XRP Available on Revolut?"),
    ("is-doge-on-revolut",           "Is Dogecoin (DOGE) Available on Revolut?"),
    ("is-bnb-on-revolut",            "Is BNB Available on Revolut?"),
    # MCP server pages (NEW — zero competition)
    ("mcp-server-stock-prices",      "Best MCP Server for Real-Time Stock Prices — Claude & Cursor"),
    ("mcp-server-crypto-prices",     "MCP Server for Live Crypto Prices — Binance, No API Key"),
    ("mcp-rsi-macd-signals",         "RSI & MACD Signals in Claude — Free MCP Tool"),
    ("mcp-fear-greed-index",         "Fear & Greed Index MCP Tool for Claude & Cursor"),
    ("mcp-insider-trading-scanner",  "SEC Insider Trading Scanner MCP Tool — Free, No API Key"),
    ("mcp-earnings-calendar",        "Earnings Calendar MCP Tool for Claude — Next Report Dates"),
    ("mcp-crypto-funding-rates",     "Crypto Funding Rates MCP — Binance Perpetuals, No API Key"),
    ("mcp-price-alerts-claude",      "Price Alert Monitor in Claude — Free MCP Tool"),
    ("mcp-portfolio-pnl",            "Portfolio P&L Calculator MCP — Real-Time, No API Key"),
    ("mcp-market-overview",          "Morning Market Overview MCP — Indices, Crypto, Commodities"),
    ("mcp-revolut-checker",          "Revolut Stock Availability Checker — Free MCP Tool"),
    ("mcp-sector-scan",              "Sector Scanner MCP Tool — Tech, Defense, AI, Finance"),
    ("claude-desktop-stock-prices",  "How to Get Real-Time Stock Prices in Claude Desktop"),
    ("cursor-stock-price-tool",      "Real-Time Stock Prices in Cursor IDE — Free MCP Server"),
    # Technical analysis pages (NEW — growing keyword cluster)
    ("rsi-signal-stocks",            "RSI Buy/Sell Signal for Stocks — Live, No Account Needed"),
    ("macd-signal-crypto",           "MACD Crypto Signal — Binance + Revolut, No API Key"),
    ("fear-greed-index-today",       "Fear & Greed Index Today — Trading Bias Signal"),
    ("insider-buying-today",         "Insider Buying Today — SEC Form 4 Live Scanner"),
    ("cluster-buy-stocks",           "Cluster Buy Stocks — Multiple Insiders Buying Signal"),
    ("crypto-funding-rates-today",   "Crypto Funding Rates Today — Binance Perpetuals"),
    ("earnings-calendar-revolut",    "Earnings Calendar for Revolut Stocks — This Week"),
]

SECTORS = ["tech", "defense", "crypto", "finance", "health", "etf", "ai", "energy"]

TOP_REVOLUT_STOCKS = [
    "NVDA", "AAPL", "MSFT", "TSLA", "META", "GOOGL", "AMZN", "NFLX",
    "AMD", "CRM", "LMT", "RTX", "BA", "GD", "NOC", "PLTR", "COIN",
    "JPM", "BAC", "GS", "V", "MA", "PYPL", "SQ", "SPY", "QQQ", "GLD",
]

# ─── helpers ──────────────────────────────────────────────────────────────────
def _arrow(chg: float) -> str:
    if chg > 2:  return "🚀"
    if chg > 0:  return "📈"
    if chg < -2: return "🔻"
    if chg < 0:  return "📉"
    return "➡️"

def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")

# ─── PAGE BUILDERS ────────────────────────────────────────────────────────────

def _base_css() -> str:
    return """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, -apple-system, sans-serif; background: #0a0c10; color: #e6edf3; line-height: 1.6; }
    a { color: #58a6ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    header { background: #0f1117; border-bottom: 1px solid rgba(255,255,255,.07); padding: .75rem 1.5rem; display: flex; align-items: center; gap: 1rem; }
    header .logo { font-weight: 800; font-size: 1.1rem; color: #3fb950; }
    .container { max-width: 860px; margin: 0 auto; padding: 2rem 1rem 4rem; }
    .card { background: #0f1117; border: 1px solid rgba(255,255,255,.07); border-radius: 12px; padding: 1.5rem; margin-top: 1.25rem; }
    .card h2 { font-size: 1rem; font-weight: 700; margin-bottom: .75rem; }
    .ticker { font-size: 2.5rem; font-weight: 800; font-family: 'JetBrains Mono', monospace; }
    .price { font-size: 2rem; font-weight: 700; margin-top: .75rem; }
    .badge { display: inline-block; padding: .3rem .9rem; border-radius: 20px; font-size: .85rem; font-weight: 600; margin-top: .75rem; }
    .badge.green { background: rgba(63,185,80,.12); color: #3fb950; border: 1px solid rgba(63,185,80,.25); }
    .badge.red   { background: rgba(248,81,73,.12);  color: #f85149; border: 1px solid rgba(248,81,73,.25); }
    .code { background: #161b22; border: 1px solid rgba(255,255,255,.07); border-radius: 8px; padding: .75rem 1rem; font-family: 'JetBrains Mono', monospace; font-size: .85rem; margin-top: .5rem; overflow-x: auto; color: #8b949e; }
    .meta { font-size: .8rem; color: #484f58; margin-top: .75rem; }
    .cta-row { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: 1rem; }
    .btn { padding: .5rem 1.1rem; border-radius: 7px; font-size: .85rem; font-weight: 600; display: inline-flex; align-items: center; gap: .35rem; }
    .btn-green { background: #3fb950; color: #000; }
    .btn-dark  { background: #161b22; border: 1px solid rgba(255,255,255,.1); color: #e6edf3; }
    footer { text-align: center; padding: 2rem; font-size: .78rem; color: #484f58; border-top: 1px solid rgba(255,255,255,.05); }
    """


def _header(base_url: str) -> str:
    return f"""<header>
  <span class="logo">⚡ mcprice</span>
  <a href="{base_url}">Home</a>
  <a href="{base_url}/docs">API Docs</a>
  <a href="https://mcpize.com/mcp/mcprice">Add to Claude</a>
</header>"""


def _footer(base_url: str) -> str:
    return f"""<footer>
  <p>Real-time data: <a href="https://finance.yahoo.com">Yahoo Finance</a> &amp; <a href="https://binance.com">Binance</a> &amp; <a href="https://alternative.me/crypto/fear-and-greed-index">alternative.me</a></p>
  <p style="margin-top:.4rem">Not financial advice &nbsp;·&nbsp; <a href="{base_url}/docs">API Docs</a> &nbsp;·&nbsp; <a href="https://mcpize.com/mcp/mcprice">mcpize</a> &nbsp;·&nbsp; <a href="https://revolut-pulse.lovable.app/insiderflow-pro-v2.html">InsiderFlow Pro</a></p>
</footer>"""


def build_ticker_page(ticker, name, price, change_pct, asset_type, on_revolut, base_url) -> str:
    now        = _now()
    canonical  = f"{base_url}/price/{ticker.lower()}"
    rev_class  = "green" if on_revolut else "red"
    rev_label  = "✅ Available on Revolut" if on_revolut else "❌ Not on Revolut"
    price_str  = f"${price:,.4f}" if price else "—"
    chg_str    = f"{'+' if (change_pct or 0) >= 0 else ''}{change_pct:.2f}%" if change_pct is not None else "—"
    chg_color  = "#3fb950" if (change_pct or 0) >= 0 else "#f85149"
    meta_desc  = f"{name} ({ticker}) live price: {price_str} ({chg_str} today). {rev_label}. Real-time data, no login required."
    page_title = f"{name} ({ticker}) Price Today — {'On Revolut ✅' if on_revolut else 'Revolut Availability'}"

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FinancialProduct",
        "name": f"{name} ({ticker})",
        "description": meta_desc,
        "url": canonical,
        "offers": {"@type": "Offer", "price": str(price or ""), "priceCurrency": "USD", "validFrom": now},
        "provider": {"@type": "Organization", "name": "mcprice", "url": base_url},
    }, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_title}</title>
  <meta name="description" content="{meta_desc}">
  <link rel="canonical" href="{canonical}">
  <meta property="og:title" content="{page_title}">
  <meta property="og:description" content="{meta_desc}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary">
  <script type="application/ld+json">{schema}</script>
  <style>{_base_css()}</style>
</head>
<body>
{_header(base_url)}
<div class="container">
  <div class="card">
    <div class="ticker">{ticker}</div>
    <div style="color:#8b949e;margin-top:.25rem">{name}</div>
    <div class="price">{price_str}</div>
    <div style="font-size:1.1rem;font-weight:600;color:{chg_color};margin-top:.25rem">{_arrow(change_pct or 0)} {chg_str} today</div>
    <div class="badge {rev_class}">{rev_label}</div>
    <div class="meta">Last updated: {now} &nbsp;·&nbsp; Source: {'Binance' if asset_type == 'crypto' else 'Yahoo Finance'} &nbsp;·&nbsp; Type: {asset_type.capitalize()}</div>
    {f'<div class="cta-row"><a href="https://revolut.com/referral/?referral-code=georgi675!MAR1-26-AR&geo-redirect" rel="nofollow" class="btn btn-green">💳 Trade {ticker} on Revolut</a></div>' if on_revolut else ''}
  </div>

  <div class="card">
    <h2>📡 API — Get {ticker} price programmatically</h2>
    <div class="code">GET {base_url}/{'crypto' if asset_type == 'crypto' else 'price'}/{ticker}</div>
    <div class="code" style="margin-top:.4rem">GET {base_url}/revolut/check/{ticker}</div>
    <div class="code" style="margin-top:.4rem">GET {base_url}/signals/{ticker}  ← RSI / MACD / SMA</div>
    <div class="meta">No API key required · 30s cache · CORS-friendly · Free forever</div>
  </div>

  <div class="card">
    <h2>🧠 Use in Claude or Cursor</h2>
    <p style="font-size:.9rem;color:#8b949e;margin-bottom:.75rem">Ask Claude: <em>"What is the {ticker} price and is it a buy based on RSI?"</em></p>
    <div class="code">{{"mcpServers": {{"mcprice": {{"type": "streamable-http", "url": "https://mcpize.com/mcp/mcprice"}}}}}}</div>
    <div class="cta-row">
      <a href="https://mcpize.com/mcp/mcprice" class="btn btn-green">⚡ Add to Claude</a>
      <a href="{base_url}/signals/{ticker.lower()}" class="btn btn-dark">📊 See {ticker} Signals</a>
    </div>
  </div>
</div>
{_footer(base_url)}
</body>
</html>"""


def build_signals_page(ticker, name, on_revolut, base_url) -> str:
    now       = _now()
    canonical = f"{base_url}/signals/{ticker.lower()}"
    meta_desc = f"Free RSI-14, SMA20, SMA50, EMA9, and MACD buy/sell signal for {name} ({ticker}). Updated in real-time via mcprice. No API key. {'Available on Revolut.' if on_revolut else ''}"
    title     = f"{ticker} RSI & MACD Signal Today — Buy or Sell? | mcprice"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{meta_desc}">
  <link rel="canonical" href="{canonical}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{meta_desc}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary">
  <script type="application/ld+json">{json.dumps({
    "@context": "https://schema.org",
    "@type": "WebPage",
    "name": title,
    "description": meta_desc,
    "url": canonical,
  }, indent=2)}</script>
  <style>{_base_css()}</style>
</head>
<body>
{_header(base_url)}
<div class="container">
  <div class="card">
    <div class="ticker">{ticker}</div>
    <div style="color:#8b949e;margin-top:.25rem">{name} — Technical Signals</div>
    <div style="margin-top:1rem;display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px">
      {"".join(f'<div style="background:#161b22;border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:12px;text-align:center"><div style="font-size:.75rem;color:#484f58;text-transform:uppercase;letter-spacing:.05em">{ind}</div><div style="font-size:1.3rem;font-weight:700;margin-top:4px;color:#58a6ff">—</div></div>' for ind in ["RSI-14","SMA-20","SMA-50","EMA-9","MACD"])}
    </div>
    <div style="margin-top:1rem;background:#161b22;border:1px solid rgba(63,185,80,.2);border-radius:8px;padding:12px;font-size:.9rem;color:#8b949e">
      ⚡ Live signals load via Claude — <a href="https://mcpize.com/mcp/mcprice">add mcprice to Claude</a> and ask: <em>"Show me RSI and MACD for {ticker}"</em>
    </div>
    {f'<div class="badge green" style="margin-top:12px">💳 {ticker} is tradeable on Revolut</div>' if on_revolut else ''}
  </div>

  <div class="card">
    <h2>📡 Get {ticker} Signals via API</h2>
    <div class="code">GET {base_url}/signals/{ticker}?period=3mo</div>
    <div class="meta">Returns RSI-14, SMA20, SMA50, EMA9, MACD, overall signal · No API key · Free</div>
  </div>

  <div class="card">
    <h2>❓ How to interpret {ticker} RSI signal</h2>
    <p style="font-size:.9rem;color:#8b949e;line-height:1.7">
      <strong style="color:#e6edf3">RSI below 30</strong> = oversold → potential BUY signal.<br>
      <strong style="color:#e6edf3">RSI above 70</strong> = overbought → potential SELL signal.<br>
      <strong style="color:#e6edf3">MACD crossover</strong> = trend change signal — bullish when MACD crosses above signal line.<br>
      <strong style="color:#e6edf3">SMA20 > SMA50</strong> = golden cross zone — medium-term bullish.<br>
      Always use multiple signals together. Not financial advice.
    </p>
  </div>

  <div class="card">
    <h2>🔗 Related</h2>
    <div style="display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.25rem">
      <a href="{base_url}/price/{ticker.lower()}" class="btn btn-dark">💲 {ticker} Price</a>
      <a href="{base_url}/revolut/check/{ticker}" class="btn btn-dark">💳 Revolut Check</a>
      <a href="https://revolut-pulse.lovable.app/insiderflow-pro-v2.html" class="btn btn-dark">📊 Insider Flow</a>
      <a href="https://mcpize.com/mcp/mcprice" class="btn btn-green">⚡ Add to Claude</a>
    </div>
  </div>
</div>
{_footer(base_url)}
</body>
</html>"""


def build_static_page(slug, title, base_url) -> str:
    canonical = f"{base_url}/{slug}"
    meta_desc = f"{title} — Free data from mcprice. No API key required. Works with Claude and Cursor."
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | mcprice</title>
  <meta name="description" content="{meta_desc}">
  <link rel="canonical" href="{canonical}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{meta_desc}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary">
  <style>{_base_css()}</style>
</head>
<body>
{_header(base_url)}
<div class="container">
  <div class="card">
    <h1 style="font-size:1.6rem;font-weight:800;line-height:1.3">{title}</h1>
    <div class="meta">{_now()} · mcprice v3.0</div>
    <div class="cta-row" style="margin-top:1rem">
      <a href="https://mcpize.com/mcp/mcprice" class="btn btn-green">⚡ Add to Claude</a>
      <a href="{base_url}/docs" class="btn btn-dark">📖 API Docs</a>
      <a href="https://revolut-pulse.lovable.app/insiderflow-pro-v2.html" class="btn btn-dark">📊 InsiderFlow Pro</a>
    </div>
  </div>
  <div class="card">
    <h2>📡 Get this data via API</h2>
    <div class="code">GET {base_url}/fear-greed</div>
    <div class="code" style="margin-top:.4rem">GET {base_url}/insider-flow</div>
    <div class="code" style="margin-top:.4rem">GET {base_url}/signals/NVDA</div>
    <div class="code" style="margin-top:.4rem">GET {base_url}/earnings?tickers=NVDA,AAPL,META</div>
    <div class="code" style="margin-top:.4rem">GET {base_url}/funding-rates</div>
    <div class="meta">No API key required · Free forever · Works with Claude, Cursor, Cline</div>
  </div>
  <div class="card">
    <h2>💳 Revolut + Binance</h2>
    <p style="font-size:.9rem;color:#8b949e">Use mcprice to identify opportunities, then execute on Revolut (stocks) or Binance (crypto).</p>
    <div class="cta-row">
      <a href="https://revolut.com/referral/?referral-code=georgi675!MAR1-26-AR&geo-redirect" rel="nofollow" class="btn btn-green">💳 Open Revolut</a>
      <a href="https://www.binance.com/activity/referral-entry/CPA?ref=CPA_00WY786BTV" rel="nofollow" class="btn btn-dark">🟡 Join Binance — 50% fees</a>
    </div>
  </div>
</div>
{_footer(base_url)}
</body>
</html>"""


def build_sitemap(base_url: str, slugs: list) -> str:
    now  = _now()
    urls = "\n".join(
        f"""  <url>
    <loc>{base_url}/{slug}</loc>
    <lastmod>{now}</lastmod>
    <changefreq>daily</changefreq>
    <priority>{'0.95' if slug in ('','index') else '0.9' if slug.startswith('price/') else '0.85' if slug.startswith('signals/') else '0.8'}</priority>
  </url>"""
        for slug in slugs
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>"""


def build_robots(base_url: str) -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {base_url}/sitemap.xml\n"


# ─── async price fetcher ──────────────────────────────────────────────────────
async def _fetch_price(ticker: str, is_crypto: bool, sem: asyncio.Semaphore) -> dict | None:
    async with sem:
        try:
            if is_crypto:
                async with httpx.AsyncClient(timeout=8) as c:
                    r = await c.get("https://api.binance.com/api/v3/ticker/24hr", params={"symbol": ticker + "USDT"})
                    d = r.json()
                return {"price": round(float(d["lastPrice"]), 6), "change_pct": round(float(d["priceChangePercent"]), 2)}
            else:
                async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                    r = await c.get(
                        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                        params={"interval": "1d", "range": "2d"},
                        headers={"User-Agent": "Mozilla/5.0 (compatible; mcprice/3.0)"},
                    )
                    meta  = r.json()["chart"]["result"][0]["meta"]
                price = meta.get("regularMarketPrice", 0.0)
                prev  = meta.get("chartPreviousClose") or price
                return {"price": round(price, 4), "change_pct": round((price - prev) / prev * 100 if prev else 0, 2)}
        except Exception as e:
            print(f"  ⚠  {ticker}: {e}", flush=True)
            return None


# ─── main ─────────────────────────────────────────────────────────────────────
async def generate(base_url: str, live: bool = True):
    print(f"🚀 mcprice SEO Generator v3.0  →  {base_url}")
    print(f"   Output: {OUT_DIR}")

    all_slugs = []
    sem = asyncio.Semaphore(5)

    # 1 — Stock price pages
    print(f"\n📈 {len(REVOLUT_STOCKS)} stock pages…")
    if live:
        results = await asyncio.gather(*[_fetch_price(t, False, sem) for t in REVOLUT_STOCKS], return_exceptions=True)
        prices  = dict(zip(REVOLUT_STOCKS.keys(), results))
    else:
        prices = {}

    for ticker, name in REVOLUT_STOCKS.items():
        pd   = prices.get(ticker) if live else None
        slug = f"price/{ticker.lower()}"
        html = build_ticker_page(ticker, name,
                                  pd.get("price") if isinstance(pd, dict) else None,
                                  pd.get("change_pct") if isinstance(pd, dict) else None,
                                  "stock", True, base_url)
        (OUT_DIR / slug).with_suffix(".html").write_text(html, encoding="utf-8")
        all_slugs.append(slug)
        print(f"  ✅ {ticker}", end="\r")

    # 2 — Crypto price pages
    print(f"\n\n🪙  {len(REVOLUT_CRYPTO)} crypto pages…")
    if live:
        crypto_list = sorted(REVOLUT_CRYPTO)
        results     = await asyncio.gather(*[_fetch_price(t, True, sem) for t in crypto_list], return_exceptions=True)
        prices      = dict(zip(crypto_list, results))
    else:
        prices = {}

    for ticker in sorted(REVOLUT_CRYPTO):
        pd   = prices.get(ticker) if live else None
        slug = f"price/{ticker.lower()}"
        html = build_ticker_page(ticker, ticker,
                                  pd.get("price") if isinstance(pd, dict) else None,
                                  pd.get("change_pct") if isinstance(pd, dict) else None,
                                  "crypto", True, base_url)
        (OUT_DIR / slug).with_suffix(".html").write_text(html, encoding="utf-8")
        all_slugs.append(slug)
        print(f"  ✅ {ticker}", end="\r")

    # 3 — Signal pages (NEW v3.0)
    print(f"\n\n📊 {len(TOP_REVOLUT_STOCKS)} signal pages (RSI/MACD)…")
    for ticker in TOP_REVOLUT_STOCKS:
        name = REVOLUT_STOCKS.get(ticker, ticker)
        slug = f"signals/{ticker.lower()}"
        html = build_signals_page(ticker, name, ticker in REVOLUT_STOCKS, base_url)
        (OUT_DIR / slug).with_suffix(".html").write_text(html, encoding="utf-8")
        all_slugs.append(slug)
        print(f"  ✅ {ticker}", end="\r")

    # 4 — Static keyword pages
    print(f"\n\n📝 {len(STATIC_PAGES)} static keyword pages…")
    for slug, title in STATIC_PAGES:
        html = build_static_page(slug, title, base_url)
        (OUT_DIR / slug).with_suffix(".html").write_text(html, encoding="utf-8")
        all_slugs.append(slug)
        print(f"  ✅ {slug}", end="\r")

    # 5 — Sector pages
    print(f"\n\n🏭 {len(SECTORS)} sector pages…")
    for sector in SECTORS:
        slug  = f"sector-{sector}"
        title = f"{sector.capitalize()} Sector Stocks — Revolut Availability & Top Picks"
        html  = build_static_page(slug, title, base_url)
        (OUT_DIR / slug).with_suffix(".html").write_text(html, encoding="utf-8")
        all_slugs.append(slug)

    # 6 — sitemap + robots
    print(f"\n\n🗺  Sitemap ({len(all_slugs)} URLs)…")
    (OUT_DIR / "sitemap.xml").write_text(build_sitemap(base_url, all_slugs), encoding="utf-8")
    (OUT_DIR / "robots.txt").write_text(build_robots(base_url), encoding="utf-8")

    total = len(REVOLUT_STOCKS) + len(REVOLUT_CRYPTO) + len(TOP_REVOLUT_STOCKS) + len(STATIC_PAGES) + len(SECTORS)
    print(f"\n✅ Done! {total} pages + sitemap.xml + robots.txt")
    print(f"   → {OUT_DIR}")
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="mcprice Programmatic SEO Generator v3.0")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "https://mcprice.fly.dev"))
    parser.add_argument("--no-live", action="store_true", help="Skip live price fetch (faster)")
    args = parser.parse_args()
    asyncio.run(generate(base_url=args.base_url.rstrip("/"), live=not args.no_live))
