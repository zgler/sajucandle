"""
Fork된 sajucandle.manseryeok 엔진으로 재검증.

목표:
- 새 CSV + KST 기준 절기 비교 로직이 정확히 작동하는지 확인
- 특히 2024 입춘(17:27 KST) 경계 처리 재검증
- Day pillar는 이미 검증됨, 시주·월주 전이가 핵심
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# src 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.manseryeok.core import SajuCalculator

calc = SajuCalculator()
print(f"[INFO] CSV 경로: {calc.csv_path}")
print(f"[INFO] 데이터 범위: {calc.min_year} ~ {calc.max_year}\n")

OUT_DIR = Path(__file__).parent / "smoke_output_forked"
OUT_DIR.mkdir(exist_ok=True)

cases = [
    # 입춘 경계 핵심 (KST 17:27)
    {
        "label": "입춘전_17:00 (KST)",
        "args": dict(year=2024, month=2, day=4, hour=17, minute=0,
                     city="Seoul", use_solar_time=True),
        "expected_month_branch": "丑",  # 아직 입춘 전
    },
    {
        "label": "입춘경계_17:26",
        "args": dict(year=2024, month=2, day=4, hour=17, minute=26,
                     city="Seoul", use_solar_time=True),
        "expected_month_branch": "丑",  # 1분 전
    },
    {
        "label": "입춘경계_17:28",
        "args": dict(year=2024, month=2, day=4, hour=17, minute=28,
                     city="Seoul", use_solar_time=True),
        "expected_month_branch": "寅",  # 1분 후
    },
    {
        "label": "입춘후_18:00",
        "args": dict(year=2024, month=2, day=4, hour=18, minute=0,
                     city="Seoul", use_solar_time=True),
        "expected_month_branch": "寅",
    },
    # 일반 날짜
    {
        "label": "오늘_2026-04-23_정오",
        "args": dict(year=2026, month=4, day=23, hour=12, minute=0,
                     city="Seoul", use_solar_time=True),
    },
    # 야자시
    {
        "label": "야자시_2024-01-01_23:30",
        "args": dict(year=2024, month=1, day=1, hour=23, minute=30,
                     city="Seoul", use_solar_time=True, early_zi_time=True),
    },
    # 설날
    {
        "label": "설날_2024-02-10_12:00",
        "args": dict(year=2024, month=2, day=10, hour=12, minute=0,
                     city="Seoul", use_solar_time=True),
    },
    # 과거 서머타임 시대
    {
        "label": "서머타임_1988-08-15_12:00",
        "args": dict(year=1988, month=8, day=15, hour=12, minute=0,
                     city="Seoul", use_solar_time=True),
    },
]

all_results = []
pass_count = 0
fail_count = 0
for c in cases:
    args = c["args"]
    try:
        result = calc.calculate_saju(**args)
    except Exception as e:
        result = {"error": str(e)}
        all_results.append({"label": c["label"], "error": str(e), "args": args})
        print(f"[ERROR] {c['label']}: {e}")
        fail_count += 1
        continue

    expected = c.get("expected_month_branch")
    actual = result.get("month_branch")
    status = ""
    if expected:
        if expected == actual:
            status = f" [OK] 월지={actual}"
            pass_count += 1
        else:
            status = f" [FAIL] 기대={expected} 실제={actual}"
            fail_count += 1

    print(f"{c['label']}: 연={result.get('year_pillar')} 월={result.get('month_pillar')} "
          f"일={result.get('day_pillar')} 시={result.get('hour_pillar')}{status}")

    all_results.append({
        "label": c["label"],
        "args": args,
        "result": result,
    })

print(f"\n[SUMMARY] 기대값 일치 {pass_count} / 전체 검증 {pass_count + fail_count}")

out_file = OUT_DIR / "results.json"
with out_file.open("w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
print(f"상세: {out_file}")
