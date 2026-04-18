FROM python:3.12-slim

LABEL org.opencontainers.image.title="QuntaTradeAI"
LABEL org.opencontainers.image.description="Claude-powered multi-venue AI trading agent (crypto + forex)."

WORKDIR /app

RUN pip install --no-cache-dir \
    hyperliquid-python-sdk \
    anthropic \
    python-dotenv \
    aiohttp \
    requests \
    rich \
    ccxt \
    pyyaml

COPY src ./src
COPY risk.yaml ./risk.yaml

ENV APP_PORT=3000
EXPOSE 3000

ENTRYPOINT ["python", "-m", "src.main"]
