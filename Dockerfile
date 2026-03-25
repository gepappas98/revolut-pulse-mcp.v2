FROM python:3.12-slim

WORKDIR /app

# Copy requirements first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app + config (FIX: config/ was missing — JSON files never loaded in container)
COPY app.py .
COPY config/ ./config/

# Default: HTTP transport for cloud deploy
ENV MCP_TRANSPORT=http
# FIX: PORT matches fly.toml (was 8000, fly.toml sends 8080 → mismatch)
ENV PORT=8080

EXPOSE 8080

CMD ["python", "app.py"]
