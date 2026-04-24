"""
sajupy CSV의 절기 시각 vs skyfield 정확 시각 오차 분포 측정.

목표:
1. sajupy CSV가 어느 시간대 기준인지 판별 (UTC / KST / Seoul LMT / 기타)
2. 일관된 오차가 있으면 보정 가능, 무작위면 사용 불가
3. 월주 결정에 영향을 주는 12절(節)만 우선 분석
"""

import csv
import json
import sys
import statistics
from pathlib import Path
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
SAJUPY_CSV = ROOT / ".venv" / "Lib" / "site-packages" / "sajupy" / "calendar_data.csv"
SKYFIELD_JSON = ROOT / "data" / "solar_terms" / "solar_terms_2020_2030.json"

# 월주를 바꾸는 12절
MONTHLY_TERMS = {
    "立春", "驚蟄", "清明", "立夏", "芒種", "小暑",
    "立秋", "白露", "寒露", "立冬", "大雪", "小寒",
}


def load_sajupy_terms(start_year: int, end_year: int):
    """sajupy CSV에서 절기 시각을 추출."""
    terms = {}
    with SAJUPY_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                year = int(row["year"])
            except (KeyError, ValueError):
                continue
            if year < start_year or year > end_year:
                continue
            term_hanja = row.get("solar_term_hanja", "").strip()
            term_time = row.get("term_time", "").strip()
            if not term_hanja or not term_time:
                continue
            # term_time 포맷: YYYYMMDDHHMM (12자리)
            try:
                s = term_time
                if len(s) == 12:
                    dt = datetime(
                        year=int(s[0:4]),
                        month=int(s[4:6]),
                        day=int(s[6:8]),
                        hour=int(s[8:10]),
                        minute=int(s[10:12]),
                    )
                    key = (year, term_hanja)
                    terms[key] = dt
            except ValueError:
                continue
    return terms


def load_skyfield_terms():
    with SKYFIELD_JSON.open(encoding="utf-8") as f:
        data = json.load(f)
    result = {}
    for t in data:
        key = (t["year"], t["term_hanja"])
        result[key] = {
            "utc": datetime.fromisoformat(t["utc"]),
            "kst": datetime.fromisoformat(t["kst"]),
            "seoul_lmt": datetime.fromisoformat(t["seoul_lmt"]),
        }
    return result


def diff_minutes(a: datetime, b: datetime) -> float:
    return (a - b).total_seconds() / 60.0


def main():
    sajupy = load_sajupy_terms(2020, 2030)
    skyfield_data = load_skyfield_terms()

    print(f"sajupy CSV 절기: {len(sajupy)}건")
    print(f"skyfield 절기: {len(skyfield_data)}건\n")

    # 각 기준 시간대와의 오차 수집
    diffs_vs_kst = []
    diffs_vs_lmt = []
    diffs_vs_utc = []
    monthly_diffs_vs_lmt = []
    detailed_rows = []

    for key, sajupy_dt in sajupy.items():
        year, hanja = key
        if key not in skyfield_data:
            continue
        sk = skyfield_data[key]
        d_kst = diff_minutes(sajupy_dt, sk["kst"])
        d_lmt = diff_minutes(sajupy_dt, sk["seoul_lmt"])
        d_utc = diff_minutes(sajupy_dt, sk["utc"])
        diffs_vs_kst.append(d_kst)
        diffs_vs_lmt.append(d_lmt)
        diffs_vs_utc.append(d_utc)
        if hanja in MONTHLY_TERMS:
            monthly_diffs_vs_lmt.append(d_lmt)
        detailed_rows.append({
            "year": year,
            "term": hanja,
            "is_monthly": hanja in MONTHLY_TERMS,
            "sajupy": sajupy_dt.strftime("%Y-%m-%d %H:%M"),
            "kst_true": sk["kst"].strftime("%Y-%m-%d %H:%M"),
            "lmt_true": sk["seoul_lmt"].strftime("%Y-%m-%d %H:%M"),
            "utc_true": sk["utc"].strftime("%Y-%m-%d %H:%M"),
            "diff_vs_kst_min": round(d_kst, 1),
            "diff_vs_lmt_min": round(d_lmt, 1),
            "diff_vs_utc_min": round(d_utc, 1),
        })

    def stats(label, values):
        if not values:
            print(f"  {label}: (no data)")
            return
        print(f"  {label}:")
        print(f"    평균 오차: {statistics.mean(values):+7.1f}분")
        print(f"    중앙값   : {statistics.median(values):+7.1f}분")
        print(f"    표준편차 : {statistics.stdev(values):7.1f}분" if len(values) > 1 else "")
        print(f"    최소     : {min(values):+7.1f}분")
        print(f"    최대     : {max(values):+7.1f}분")
        # abs 오차 5분 이내 비율
        within_5 = sum(1 for v in values if abs(v) <= 5) / len(values) * 100
        within_1 = sum(1 for v in values if abs(v) <= 1) / len(values) * 100
        print(f"    |오차|≤1분: {within_1:.1f}%")
        print(f"    |오차|≤5분: {within_5:.1f}%")

    print("=" * 60)
    print("sajupy CSV의 절기 시각 오차 분석 (2020~2030, 전체 24절기)")
    print("=" * 60)
    print(f"\n[1] sajupy - KST (실제 KST 대비)")
    stats("KST 기준", diffs_vs_kst)

    print(f"\n[2] sajupy - Seoul LMT (서울 지방 평균 태양시 대비)")
    stats("LMT 기준", diffs_vs_lmt)

    print(f"\n[3] sajupy - UTC 대비")
    stats("UTC 기준", diffs_vs_utc)

    print(f"\n[4] 월주 결정용 12절만 (2020~2030)")
    stats("월주 12절 vs LMT", monthly_diffs_vs_lmt)

    # 가장 큰 오차 상위 10개
    print("\n=" * 60)
    print("오차 절대값 상위 10 (LMT 기준)")
    print("=" * 60)
    sorted_rows = sorted(detailed_rows, key=lambda r: abs(r["diff_vs_lmt_min"]), reverse=True)
    for r in sorted_rows[:10]:
        print(f"  {r['year']} {r['term']:<4} | sajupy {r['sajupy']} | LMT {r['lmt_true']} | Δ {r['diff_vs_lmt_min']:+6.1f}분")

    # 상세 결과 저장
    out_file = ROOT / "data" / "solar_terms" / "comparison_2020_2030.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(detailed_rows, f, ensure_ascii=False, indent=2)
    print(f"\n상세 비교 결과 저장: {out_file}")


if __name__ == "__main__":
    main()
