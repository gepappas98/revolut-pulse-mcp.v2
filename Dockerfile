FROM python:3.12-slim

WORKDIR /app

# Copy requirements first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app.py .

# FIX #2: Copy config directory (revolut_stocks.json + revolut_crypto.json)
# Without this the config files are missing and app falls back to hardcoded defaults
COPY config/ ./config/

# Default: HTTP transport for cloud deploy
ENV MCP_TRANSPORT=http
ENV PORT=8080

EXPOSE 8080

CMD ["python", "app.py"]
