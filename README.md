# mcprice ⚡

> **MCP Server** for **real-time stock & crypto prices**  
> in Claude Desktop / Cursor.  
>  
> Stocks → **Yahoo Finance** (no API key needed)  
> Crypto → **Binance Public API** (no API key needed)  
> Companion to: [revolut-pulse](https://github.com/gepappas98/revolut-pulse) (insider trades)

[![mcprice MCP server](https://glama.ai/mcp/servers/gepappas98/revolut-pulse-mcp.v2/badges/card.svg)](https://glama.ai/mcp/servers/gepappas98/revolut-pulse-mcp.v2)

---

## 🧰 Tools (6 total)

| Tool | What it does | Source |
|------|-------------|--------|
| `get_price("NVDA")` | Price + 24h change for 1 stock | Yahoo Finance |
| `get_prices_bulk(["NVDA","LMT","GLD"])` | Bulk prices for a list of stocks | Yahoo Finance |
| `get_crypto_price("BTC")` | Crypto price + high/low/volume 24h | Binance |
| `price_snapshot(["NVDA","BTC","ETH"])` | Rich snapshot for stocks + crypto | Yahoo + Binance |
| `revolut_price_check("LMT")` | Price + "is it on Revolut?" | Yahoo Finance |
| `crypto_top_movers(limit=10)` | Top gainers/losers 24h | Binance |

---

## ⚡ Quick Start (2 minutes)

### Step 1 — Clone the repo

```bash
git clone https://github.com/gepappas98/revolut-pulse-mcp.v2.git
cd revolut-pulse-mcp.v2

# Recommended: using uv
uv run --with fastmcp,httpx python app.py
```

### Step 2 — Install & run

**With `uv` (recommended):**
```bash
# Install uv (once):
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run:
uv run --with fastmcp,httpx python app.py
```

**With `pip`:**
```bash
pip install -r requirements.txt
python app.py
```

---

## 🤖 Claude Desktop — Setup

Open: **Claude Desktop → Settings → Developer → Edit Config**

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcprice": {
      "command": "uv",
      "args": ["run", "--with", "fastmcp,httpx", "python", "app.py"],
      "cwd": "/path/to/revolut-pulse-mcp.v2"
    }
  }
}
```

> 💡 **Pro tip**: If you also have `revolut-pulse-mcp`, add both together:

```json
{
  "mcpServers": {
    "revolut-pulse-mcp": {
      "command": "uv",
      "args": ["run", "--with", "fastmcp,httpx,beautifulsoup4", "python", "app.py"],
      "cwd": "/Users/george/revolut-pulse-mcp"
    },
    "mcprice": {
      "command": "uv",
      "args": ["run", "--with", "fastmcp,httpx", "python", "app.py"],
      "cwd": "/Users/george/mcprice"
    }
  }
}
```

Now you can ask Claude:
> _"Show me the latest insider trades for NVDA and tell me the current price"_

And Claude will use **both servers simultaneously**! 🔥

---

## 🎯 Cursor — Setup

`Cursor → Settings → MCP → Add server
• Name: mcprice
• Command: uv run --with fastmcp,httpx python app.py
• Working directory: revolut-pulse-mcp.v2 folder`

---

## 🚀 Deploy on Railway (1 click)

1. Fork this repo on GitHub
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
3. Select the `mcprice` repo
4. Add environment variables:
   ```
   MCP_TRANSPORT = http
   PORT          = 8080
   ```
5. Railway gives you a URL: `https://mcprice-production.up.railway.app`

Connect to Claude Desktop (remote):
```json
{
  "mcpServers": {
    "mcprice": {
      "type": "http",
      "url": "https://mcprice-production.up.railway.app/mcp"
    }
  }
}
```

---

## 🛩️ Deploy on Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Deploy (from the project folder)
flyctl auth login
flyctl launch --name mcprice --region ams
flyctl secrets set MCP_TRANSPORT=http
flyctl deploy
```

URL: `https://mcprice.fly.dev/mcp`

---

## 💬 Usage Examples

```
# Stock price
"What is NVIDIA trading at right now?"
→ get_price("NVDA")

# Revolut check
"Can I buy Lockheed Martin on Revolut?"
→ revolut_price_check("LMT")

# Defense stocks
"Show me prices for LMT, RTX, NOC, BA"
→ get_prices_bulk(["LMT","RTX","NOC","BA"])

# Crypto
"Where is Bitcoin today?"
→ get_crypto_price("BTC")

# Top movers
"Which cryptos are moving today?"
→ crypto_top_movers(limit=10)

# Full snapshot
"Show me all my assets"
→ price_snapshot(["NVDA","AAPL","GLD","SPY","BTC","ETH"])
```

---

## 🔗 Architecture — Revolut Ecosystem

```
Claude / Cursor
      │
      ├── revolut-pulse-mcp  →  Insider trades (SEC Form 4)
      │                         is_revolut_tradable()
      │                         check_insider_alerts()
      │
      └── mcprice            →  Real-time prices
                                get_price()
                                revolut_price_check()
                                crypto_top_movers()
```

---

## 📁 File Structure

```
mcprice/
├── app.py              ← All server code (6 tools)
├── requirements.txt    ← fastmcp, httpx
├── mcp.json            ← Config for Claude/Cursor
├── Dockerfile          ← For Railway/Fly.io
├── railway.json        ← Railway config
├── fly.toml            ← Fly.io config
├── .gitignore
├── .github/
│   └── workflows/
│       └── test.yml    ← GitHub Actions CI
└── README.md
```

---

## 🔒 Notes

- **No API key required** — Yahoo Finance & Binance Public API are free
- Rate limit: ~60 requests/min on Yahoo Finance — avoid bulk calls with >20 tickers
- Stock prices may have a 15–20 minute delay (Yahoo Finance free tier)
- Binance crypto prices are **real-time** (no delay)
- **Not financial advice**

📁 This is v2
Improved structure with api/, config/, seo/ folders, better Docker support, and mcpize.yaml for easier publishing.
⭐ Star the repo if you're using it!

Just say the word! 🚀