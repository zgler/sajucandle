"""프로젝트 루트 및 data 디렉토리 탐색 유틸리티.

소스 트리(개발)와 pip install 후(Docker) 모두에서 data/ 폴더를 찾을 수 있도록
여러 경로를 순서대로 시도한다.

탐색 순서:
  1. __file__ 기준 parents[3] (소스 트리: src/sajucandle/_paths.py → 3단계 위)
  2. CWD (Docker WORKDIR = /app)
  3. /app (Docker 하드코딩 폴백)
"""

from __future__ import annotations

from pathlib import Path


def _find_project_root() -> Path:
    """data/ 디렉토리가 존재하는 프로젝트 루트를 반환한다."""
    candidates = [
        Path(__file__).resolve().parents[3],  # 소스 트리
        Path.cwd(),                            # Docker WORKDIR
        Path("/app"),                          # Docker 하드코딩 폴백
    ]
    for p in candidates:
        if (p / "data").is_dir():
            return p
    # 어디에도 없으면 소스 트리 경로 반환 (기존 동작 유지)
    return candidates[0]


PROJECT_ROOT = _find_project_root()
DATA_DIR = PROJECT_ROOT / "data"
