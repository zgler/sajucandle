FROM python:3.12-slim

WORKDIR /app

# 의존성 먼저 설치 (레이어 캐시 활용)
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# 런타임
CMD ["python", "-m", "sajucandle.bot"]
