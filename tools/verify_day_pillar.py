"""
sajupy CSV의 day_pillar(일주) 정확성 검증.

일주는 60갑자 순환으로 결정적이다. 임의 기준일 하나만 정확하면 전후 모든 일주가 강제됨.

검증 방법:
1. sajupy CSV에서 무작위 샘플 추출
2. "일주는 60일 주기로 순환"이라는 제약과 일치하는지 확인
3. 별도 기준일(예: 2024-02-10 = 癸卯)과 매일 간격 × 60 계산으로 크로스체크
4. 결과가 일관되면 day_pillar는 신뢰 가능

일주 기준점(앵커):
- 공개된 만세력상 2024-02-10 (설날)의 일주: 癸卯
- 또는 sajupy 자체 첫 날(1900-01-01) = 甲戌 을 앵커로 forward 계산

알고리즘:
- 60갑자 배열 정의
- 앵커 날짜의 갑자 인덱스 찾기
- 대상 날짜의 Julian Day Number 차이로 인덱스 이동
- 계산된 갑자가 CSV의 day_pillar과 일치하는지 확인
"""

import csv
import sys
from pathlib import Path
from datetime import datetime, date, timedelta

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
SAJUPY_CSV = ROOT / ".venv" / "Lib" / "site-packages" / "sajupy" / "calendar_data.csv"

# 천간 (10)
STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
# 지지 (12)
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 60갑자 순환
def gapja_cycle():
    """0~59 인덱스로 60갑자 생성. 0=甲子, 1=乙丑, ..., 59=癸亥"""
    cycle = []
    for i in range(60):
        cycle.append(STEMS[i % 10] + BRANCHES[i % 12])
    return cycle

GAPJA = gapja_cycle()


def compute_day_pillar(target: date, anchor_date: date, anchor_pillar: str) -> str:
    """앵커 기준 60갑자 순환 계산."""
    try:
        anchor_idx = GAPJA.index(anchor_pillar)
    except ValueError:
        raise ValueError(f"Unknown gapja: {anchor_pillar}")
    diff_days = (target - anchor_date).days
    idx = (anchor_idx + diff_days) % 60
    return GAPJA[idx]


def load_day_pillars_from_csv():
    """sajupy CSV에서 일자별 day_pillar 추출."""
    pillars = {}
    with SAJUPY_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                y = int(row["year"])
                m = int(row["month"])
                d = int(row["day"])
            except (KeyError, ValueError):
                continue
            pillar = row.get("day_pillar", "").strip()
            if not pillar:
                continue
            pillars[date(y, m, d)] = pillar
    return pillars


def main():
    pillars = load_day_pillars_from_csv()
    print(f"sajupy CSV에서 총 {len(pillars)}일의 일주 로드")

    # 정렬된 날짜 리스트
    sorted_dates = sorted(pillars.keys())
    first_date = sorted_dates[0]
    first_pillar = pillars[first_date]
    print(f"첫 날짜: {first_date} = {first_pillar}")
    print(f"마지막 날짜: {sorted_dates[-1]} = {pillars[sorted_dates[-1]]}")

    # 첫 날을 앵커로 잡고, 이후 모든 날이 순환 일치하는지 검증
    print("\n[검증 1] 60갑자 순환 일관성 (내부 일관성)")
    mismatch_count = 0
    mismatches = []
    for d in sorted_dates:
        expected = compute_day_pillar(d, first_date, first_pillar)
        actual = pillars[d]
        if expected != actual:
            mismatch_count += 1
            if len(mismatches) < 10:
                mismatches.append((d, actual, expected))
    print(f"  총 {len(pillars)}일 중 불일치: {mismatch_count}건")
    if mismatches:
        print("  불일치 샘플:")
        for d, a, e in mismatches:
            print(f"    {d}: CSV={a}, 계산={e}")

    # 별도 앵커로 크로스체크: 2024-02-10 설날 = 癸卯 (공개 만세력 기준)
    # 혹은 2020-01-01 = 甲午 (다수 만세력 확인) — 네이버 만세력 등에서 재확인 필요
    print("\n[검증 2] 공개 만세력 기준 앵커 크로스체크")
    # 여러 공개 기준일 체크
    known_anchors = [
        # (날짜, 사주 기대값, 출처)
        (date(2024, 2, 10), "癸卯", "설날, 다수 공개 만세력"),
        (date(2024, 1, 1), None, "sajupy CSV 자체"),
        (date(2000, 1, 1), None, "밀레니엄"),
        (date(1900, 1, 1), None, "sajupy CSV 시작"),
    ]

    for anchor_date_val, expected, source in known_anchors:
        csv_pillar = pillars.get(anchor_date_val)
        if csv_pillar is None:
            continue
        marker = ""
        if expected and csv_pillar != expected:
            marker = f"  ❌ 예상: {expected}"
        elif expected and csv_pillar == expected:
            marker = f"  ✓ 일치"
        print(f"  {anchor_date_val}: CSV={csv_pillar} ({source}){marker}")

    # 최종 판정
    print("\n[최종 판정]")
    if mismatch_count == 0:
        print("  ✓ sajupy CSV의 day_pillar은 내부 일관성 통과")
        print("  → 공개 만세력 기준 앵커 1~2개만 수동 크로스체크 후 채택 가능")
    else:
        print(f"  ✗ {mismatch_count}건 불일치 — day_pillar 자체가 오류")


if __name__ == "__main__":
    main()
