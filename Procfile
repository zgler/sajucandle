web: sh -c "python -m uvicorn sajucandle.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"
worker: python -m sajucandle.scheduler.runner --daemon
