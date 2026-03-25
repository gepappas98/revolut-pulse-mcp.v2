# mcprice ⚡ — Real-Time Stock & Crypto Prices MCP

> **Lightweight MCP server** for **real-time stock & crypto prices** directly inside Claude Desktop and Cursor.  
> No API keys • Zero cost • Pairs perfectly with revolut-pulse (insider trades).

**Stocks** → Yahoo Finance (public)  
**Crypto** → Binance Public API (real-time)  
**Revolut bonus** → `revolut_price_check` tells you if a stock is tradable on Revolut.

Perfect for traders, Revolut users, and AI coding assistants.

---

## 🧰 Tools (6 powerful tools)

| Tool                          | Description                                      | Example Call                     |
|-------------------------------|--------------------------------------------------|----------------------------------|
| `get_price("NVDA")`           | Current price + 24h change + volume              | `get_price("AAPL")`              |
| `get_prices_bulk([...])`      | Batch prices (up to 20 tickers)                  | `get_prices_bulk(["LMT","RTX"])` |
| `get_crypto_price("BTC")`     | Real-time crypto + 24h high/low/volume           | `get_crypto_price("ETH")`        |
| `price_snapshot([...])`       | Full watchlist snapshot (stocks + crypto)        | `price_snapshot(["NVDA","BTC"])` |
| `revolut_price_check("LMT")`  | Price + “Is it tradable on Revolut?”             | `revolut_price_check("BA")`      |
| `crypto_top_movers(limit=10)` | Top gainers & losers in last 24h                 | `crypto_top_movers()`            |

---

## ⚡ Quick Start (under 2 minutes)

```bash
git clone https://github.com/gepappas98/revolut-pulse-mcp.git
cd revolut-pulse-mcp

# Recommended: uv
uv run --with fastmcp,httpx python app.py
