FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

COPY app.py .
COPY api/ api/
COPY seo/ seo/
COPY config/ config/

ENV BASE_URL=https://mcprice.fly.dev
EXPOSE 8001

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
