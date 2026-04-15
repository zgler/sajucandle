"""uvicorn 엔트리 포인트. Railway의 $PORT env를 Python에서 직접 읽음.

Railway Custom Start Command: `python -m sajucandle.api_main`
로컬: `python -m sajucandle.api_main` 또는 `uvicorn sajucandle.api:app`
"""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    # api.app 참조 문자열로 넘겨야 reload가 되고 워커도 잘 뜸
    uvicorn.run("sajucandle.api:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
