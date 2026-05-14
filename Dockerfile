FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

COPY data/tickers/ ./data/tickers/
COPY data/manseryeok/ ./data/manseryeok/
COPY data/solar_terms/ ./data/solar_terms/

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

CMD ["sh", "-c", "uvicorn sajucandle.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
