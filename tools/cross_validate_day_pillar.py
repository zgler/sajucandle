"""
day_pillar 앵커 오프셋 확정.

방법: lunar-python(중국 농력 라이브러리, 활성 프로젝트) 결과를
sajupy CSV 및 우리 CSV와 20개 샘플에서 비교한다.

lunar-python는 중국 전통 농력/바지 계산 라이브러리로, 천문 데이터 기반의 정확한
간지 계산을 제공한다. 중국식 관행 기준이지만 day_pillar(일진)은 국가·관행 관계없이
UTC 기반 천문학적 일자가 같으므로 동일해야 한다.
"""

import csv
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from lunar_python import Solar

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent

STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]


def lunar_python_day_pillar(target: date) -> str:
    """lunar-python으로 해당 날짜(정오 기준)의 일주 조회."""
    solar = Solar.fromYmdHms(target.year, target.month, target.day, 12, 0, 0)
    lunar = solar.getLunar()
    # 바지 계산
    ba = lunar.getEightChar()
    return ba.getDay()  # e.g. "甲戌" 반환


def load_sajupy_csv_day_pillar():
    """sajupy 원본 CSV에서 일주 조회."""
    pillars = {}
    csv_path = ROOT / ".venv" / "Lib" / "site-packages" / "sajupy" / "calendar_data.csv"
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                y, m, d = int(row["year"]), int(row["month"]), int(row["day"])
                pillars[date(y, m, d)] = row.get("day_pillar", "").strip()
            except (KeyError, ValueError):
                continue
    return pillars


def main():
    # 20개 샘플: 다양한 연도·달
    samples = [
        date(1900, 1, 1),
        date(1920, 6, 15),
        date(1950, 12, 31),
        date(1970, 7, 20),
        date(1984, 2, 2),   # 60갑자 시작 근처
        date(1984, 2, 5),
        date(2000, 1, 1),
        date(2000, 12, 31),
        date(2010, 3, 14),
        date(2020, 1, 1),
        date(2024, 2, 10),  # 설날
        date(2024, 1, 1),
        date(2024, 4, 22),
        date(2025, 1, 1),
        date(2025, 12, 25),
        date(2026, 4, 22),  # "오늘"
        date(2030, 6, 15),
        date(2050, 1, 1),
        date(2080, 6, 15),
        date(2100, 12, 31),
    ]

    sajupy_pillars = load_sajupy_csv_day_pillar()

    print(f"{'date':<12} {'lunar-python':<6} {'sajupy':<6} {'diff_days'}")
    print("-" * 50)

    # STEM/BRANCH로부터 순번 계산
    GAPJA = [STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)]

    mismatches_days = []
    for d in samples:
        try:
            lp_pillar = lunar_python_day_pillar(d)
        except Exception as e:
            lp_pillar = f"ERR:{e}"
            continue
        sp_pillar = sajupy_pillars.get(d, "N/A")

        try:
            lp_idx = GAPJA.index(lp_pillar)
            sp_idx = GAPJA.index(sp_pillar)
            diff = (sp_idx - lp_idx) % 60
            if diff > 30:
                diff -= 60
            diff_str = f"{diff:+d}"
            mismatches_days.append(diff)
        except ValueError:
            diff_str = "?"

        marker = " " if lp_pillar == sp_pillar else " ← 불일치"
        print(f"{d}  {lp_pillar}   {sp_pillar}   {diff_str}{marker}")

    if mismatches_days:
        from statistics import mean, stdev
        print(f"\n평균 오프셋(sajupy - lunar_python): {mean(mismatches_days):+.1f}일")
        if len(mismatches_days) > 1:
            print(f"표준편차: {stdev(mismatches_days):.2f}")
        # 최빈값 계산
        from collections import Counter
        mode_offset = Counter(mismatches_days).most_common(1)[0]
        print(f"최빈 오프셋: {mode_offset[0]:+d}일 ({mode_offset[1]}/{len(mismatches_days)}건)")


if __name__ == "__main__":
    main()
