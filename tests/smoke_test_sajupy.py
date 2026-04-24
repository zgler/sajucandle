"""
sajupy 기초 동작 스모크 테스트.

결과는 UTF-8로 JSON 파일에 저장 (Windows cp949 콘솔 한글 깨짐 회피).
검증 데이터셋 본격 테스트는 별도로 진행.
"""

import json
import sys
from pathlib import Path
from sajupy import calculate_saju, get_saju_details, solar_to_lunar

# UTF-8 강제 출력
sys.stdout.reconfigure(encoding="utf-8")

OUT_DIR = Path(__file__).parent / "smoke_output"
OUT_DIR.mkdir(exist_ok=True)

cases = [
    {
        "label": "오늘_2026-04-22_정오_서울",
        "args": dict(year=2026, month=4, day=22, hour=12, minute=0,
                     city="Seoul", use_solar_time=True),
    },
    {
        "label": "야자시_ealry_true_2024-01-01_23:30",
        "args": dict(year=2024, month=1, day=1, hour=23, minute=30,
                     city="Seoul", use_solar_time=True, early_zi_time=True),
    },
    {
        "label": "야자시_early_false_2024-01-01_23:30",
        "args": dict(year=2024, month=1, day=1, hour=23, minute=30,
                     city="Seoul", use_solar_time=True, early_zi_time=False),
    },
    {
        "label": "입춘직전_2024-02-04_17:00",
        "args": dict(year=2024, month=2, day=4, hour=17, minute=0,
                     city="Seoul", use_solar_time=True),
    },
    {
        "label": "입춘직후_2024-02-04_18:00",
        "args": dict(year=2024, month=2, day=4, hour=18, minute=0,
                     city="Seoul", use_solar_time=True),
    },
    {
        "label": "입춘당일_17:27_정확한_경계",
        "args": dict(year=2024, month=2, day=4, hour=17, minute=27,
                     city="Seoul", use_solar_time=True),
    },
    # 한국 공개 명사 (BTS RM, 김남준): 1994-09-12, 시간은 12:36 KST 설
    {
        "label": "김남준_1994-09-12_12:36",
        "args": dict(year=1994, month=9, day=12, hour=12, minute=36,
                     city="Seoul", use_solar_time=True),
    },
    # 서머타임 시대 생년 (한국 1987~1988 서머타임 시행)
    {
        "label": "서머타임_1988-08-15_10:00",
        "args": dict(year=1988, month=8, day=15, hour=10, minute=0,
                     city="Seoul", use_solar_time=True),
    },
    # 음양력 경계 (2024 설: 2/10)
    {
        "label": "설날당일_2024-02-10_00:00",
        "args": dict(year=2024, month=2, day=10, hour=0, minute=0,
                     city="Seoul", use_solar_time=True),
    },
    # 윤달 케이스 (2023 음력 윤2월)
    {
        "label": "윤달샘플_2023-03-22_12:00",
        "args": dict(year=2023, month=3, day=22, hour=12, minute=0,
                     city="Seoul", use_solar_time=True),
    },
]

all_results = []
for c in cases:
    result = calculate_saju(**c["args"])
    try:
        details = get_saju_details(result)
    except Exception as e:
        details = {"error": str(e)}
    all_results.append({
        "label": c["label"],
        "input": c["args"],
        "saju": result,
        "details": details,
    })

# 음양력 변환
lunar_tests = {
    "2024-01-01": solar_to_lunar(2024, 1, 1),
    "2024-02-10 (설)": solar_to_lunar(2024, 2, 10),
    "2023-03-22 (윤2월)": solar_to_lunar(2023, 3, 22),
}
all_results.append({"label": "lunar_conversion", "data": lunar_tests})

out_file = OUT_DIR / "results.json"
with out_file.open("w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)

print(f"✅ 결과 저장: {out_file}")
print(f"총 {len(cases)}개 케이스 처리")
