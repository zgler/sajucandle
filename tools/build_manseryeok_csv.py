"""
새로운 만세력 CSV 생성.

입력:
  - sajupy 원본 CSV: 일주·월주·음양력 (day_pillar은 내부 일관성 검증됨, 앵커 오프셋은 별도 결정)
  - skyfield 정확 절기: UTC·KST·Seoul LMT 3가지

출력 CSV 구조:
  year, month, day,
  day_pillar,  (기존 sajupy값 - 앵커 오프셋 교정 후)
  year_pillar, month_pillar, lunar_year, lunar_month, lunar_day, is_leap_month,
  solar_term_hanja, solar_term_korean,
  term_time_kst,       (YYYYMMDDHHMM - 실제 KST 기준, 분단위 정확)
  term_time_seoul_lmt, (YYYYMMDDHHMM - 서울 태양시 기준, 참고용)
  term_time_utc        (YYYYMMDDHHMM - UTC)

주의사항:
- day_pillar 앵커 오프셋은 추후 네이버/원광 만세력 크로스체크로 확정 후 적용
- 본 스크립트는 우선 sajupy 값 그대로 사용 + 오프셋 변수만 인자로 받을 수 있게

월주 재계산:
- 월주는 절기 경계로 결정. KST 기준 절기 시각을 기준으로 각 날짜의 월주 재계산 필요.
- 단, "날짜 단위" CSV에선 월주가 그 날의 00:00 시점 값을 저장할지, 아니면 여러 값이 필요할지 설계 선택.
- 원본 sajupy CSV는 날짜당 month_pillar 1개 → 00:00 기준으로 설계된 것으로 추정.
- 우리는 이 관행 유지하되, 로직이 사용할 때 절기 시각을 비교해서 분 단위로 정확히 결정.

연주 재계산:
- 연주는 입춘(立春) 경계로 결정. KST 기준 입춘 시각으로 재계산.

실행:
    python tools/build_manseryeok_csv.py [--day-offset N]

--day-offset: sajupy 일주 앵커 오프셋 (기본 0). 예: -1 → 모든 일주를 하루 앞당김.
"""

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
SAJUPY_CSV = ROOT / ".venv" / "Lib" / "site-packages" / "sajupy" / "calendar_data.csv"
SKYFIELD_JSON = ROOT / "data" / "solar_terms" / "solar_terms_1900_2100.json"
OUT_CSV = ROOT / "data" / "manseryeok" / "calendar_data_v1.csv"

STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 60갑자
GAPJA = [STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)]

# 월지 순서 (인월=1월, 묘월=2월, ...) — 입춘부터 시작
# 지지: 寅 卯 辰 巳 午 未 申 酉 戌 亥 子 丑
MONTH_BRANCH_ORDER = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]

# 월주 결정용 12절 — 각 절이 시작되면 해당 월로 진입
MONTHLY_TERMS_ORDERED = [
    ("立春", "寅"),  # 1월 (寅)
    ("驚蟄", "卯"),
    ("清明", "辰"),
    ("立夏", "巳"),
    ("芒種", "午"),
    ("小暑", "未"),
    ("立秋", "申"),
    ("白露", "酉"),
    ("寒露", "戌"),
    ("立冬", "亥"),
    ("大雪", "子"),
    ("小寒", "丑"),
]

# 연간 천간 기준: 입춘 기준
# 60년 주기로 순환, 1984(甲子) 기준으로 forward 계산 가능


def load_skyfield_terms() -> dict:
    """skyfield 절기 데이터 로드. key=(year, hanja), value=datetimes."""
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


def load_sajupy_daily() -> list:
    """sajupy 일자별 로우 로드. year·month·day·day_pillar·lunar_*·solar_term만 유지."""
    rows = []
    with SAJUPY_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                rows.append({
                    "year": int(r["year"]),
                    "month": int(r["month"]),
                    "day": int(r["day"]),
                    "day_pillar": r.get("day_pillar", "").strip(),
                    "lunar_year": int(r["lunar_year"]) if r.get("lunar_year") else None,
                    "lunar_month": int(r["lunar_month"]) if r.get("lunar_month") else None,
                    "lunar_day": int(r["lunar_day"]) if r.get("lunar_day") else None,
                })
            except (KeyError, ValueError):
                continue
    return rows


def compute_year_pillar(target_date: date, ipchun_by_year: dict) -> str:
    """CSV 행 기준 연주 — "당일 = 새해 기준" 관행.

    target_date가 입춘 당일이면 이미 새해 간지로 처리. 이전 날짜면 전년 간지.
    (sajupy 원 로직의 _get_month_pillar_considering_term이 절기 시각 이전 출생자는
    런타임에 전월/전년으로 되돌려준다. CSV는 "절기 이후 기준" 값을 저장한다.)
    """
    year = target_date.year
    ipchun_dt = ipchun_by_year.get(year)
    if ipchun_dt is None:
        prev_ipchun = ipchun_by_year.get(year - 1)
        if prev_ipchun is None:
            return ""
        effective_year = year - 1 if target_date >= prev_ipchun.date() else year - 2
    else:
        # target_date == ipchun_dt.date() 인 당일도 당년 간지로 (절기 이후 기준)
        effective_year = year if target_date >= ipchun_dt.date() else year - 1

    idx = (effective_year - 1984) % 60
    return GAPJA[idx]


def compute_month_pillar(target_date: date, year_pillar: str, monthly_term_dates: dict) -> str:
    """target_date 00:00 시점의 월주.

    monthly_term_dates[(year, hanja)] = KST datetime
    연간 천간 + 월지로 월주 결정 (년상기월법, 年上起月法).
    """
    # target_date가 어느 월지에 속하는지 결정
    # 각 연도의 12절 시각 리스트를 시간순 정렬
    year = target_date.year
    # 이전 연도의 小寒부터 시작해 소한/대한/입춘/... 순으로 나열
    terms_in_window = []
    for y_offset in [-1, 0, 1]:
        for hanja, branch in MONTHLY_TERMS_ORDERED:
            key = (year + y_offset, hanja)
            dt = monthly_term_dates.get(key)
            if dt:
                terms_in_window.append((dt, hanja, branch))
    terms_in_window.sort(key=lambda x: x[0])

    # "당일 = 새 월 기준" 관행: target_date >= 절기 당일이면 해당 월지로 진입한 것으로 저장
    # (실제 시각이 절기 시각 이전이어도 CSV는 당일을 새 월로 기록.
    #  런타임에서 `_get_month_pillar_considering_term`이 출생시각 < 절기시각이면 전월로 되돌림.)
    current_branch = None
    for dt, hanja, branch in terms_in_window:
        if dt.date() <= target_date:
            current_branch = branch
        else:
            break

    if current_branch is None:
        return ""

    # 월간(月干) 계산: 년상기월법
    # 甲·己年 → 丙寅부터 시작
    # 乙·庚年 → 戊寅
    # 丙·辛年 → 庚寅
    # 丁·壬年 → 壬寅
    # 戊·癸年 → 甲寅
    if not year_pillar:
        return ""
    year_stem = year_pillar[0]
    start_month_stem_by_year_stem = {
        "甲": "丙", "己": "丙",
        "乙": "戊", "庚": "戊",
        "丙": "庚", "辛": "庚",
        "丁": "壬", "壬": "壬",
        "戊": "甲", "癸": "甲",
    }
    first_stem_for_year = start_month_stem_by_year_stem.get(year_stem)
    if first_stem_for_year is None:
        return ""
    # 월지 순서에서 current_branch의 인덱스
    month_idx = MONTH_BRANCH_ORDER.index(current_branch)
    # 월간: 첫 월간(寅월)에서 month_idx만큼 진행
    start_stem_idx = STEMS.index(first_stem_for_year)
    month_stem_idx = (start_stem_idx + month_idx) % 10
    return STEMS[month_stem_idx] + current_branch


def build_term_lookup(skyfield_data: dict) -> dict:
    """(year, month, day) → (hanja, korean, kst, lmt, utc) 매핑. 날짜당 1개 절기만(첫 절기).

    절기는 KST 날짜 기준으로 저장.
    """
    lookup = {}
    for (year, hanja), dts in skyfield_data.items():
        kst_date = dts["kst"].date()
        key = (kst_date.year, kst_date.month, kst_date.day)
        # 하루에 2개 절기가 드물게 겹칠 수 있음 — 그런 경우 둘 다 저장
        if key not in lookup:
            lookup[key] = []
        # Korean name 매핑
        from_map = {
            "春分": "춘분", "清明": "청명", "穀雨": "곡우", "立夏": "입하",
            "小滿": "소만", "芒種": "망종", "夏至": "하지", "小暑": "소서",
            "大暑": "대서", "立秋": "입추", "處暑": "처서", "白露": "백로",
            "秋分": "추분", "寒露": "한로", "霜降": "상강", "立冬": "입동",
            "小雪": "소설", "大雪": "대설", "冬至": "동지", "小寒": "소한",
            "大寒": "대한", "立春": "입춘", "雨水": "우수", "驚蟄": "경칩",
        }
        lookup[key].append({
            "hanja": hanja,
            "korean": from_map.get(hanja, ""),
            "kst": dts["kst"],
            "lmt": dts["seoul_lmt"],
            "utc": dts["utc"],
        })
    return lookup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day-offset", type=int, default=0,
                        help="sajupy 일주 앵커 오프셋 (검증 후 적용)")
    args = parser.parse_args()
    offset = args.day_offset

    print("[LOAD] skyfield 절기 데이터")
    skyfield_data = load_skyfield_terms()
    print(f"  {len(skyfield_data)}건 로드")

    print("[LOAD] sajupy 일자별 데이터")
    daily_rows = load_sajupy_daily()
    print(f"  {len(daily_rows)}일 로드")

    # 입춘 연도별 KST 시각 매핑
    ipchun_by_year = {}
    for (y, h), dts in skyfield_data.items():
        if h == "立春":
            ipchun_by_year[y] = dts["kst"]
    print(f"  입춘: {len(ipchun_by_year)}년")

    # 12절의 (year, hanja) → KST 시각 매핑
    monthly_term_dates = {}
    monthly_set = {h for h, _ in MONTHLY_TERMS_ORDERED}
    for (y, h), dts in skyfield_data.items():
        if h in monthly_set:
            monthly_term_dates[(y, h)] = dts["kst"]

    # 날짜별 절기 룩업
    term_lookup = build_term_lookup(skyfield_data)

    # CSV 작성
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "year", "month", "day",
            "day_pillar", "month_pillar", "year_pillar",
            "lunar_year", "lunar_month", "lunar_day", "is_leap_month",
            "solar_term_hanja", "solar_term_korean",
            # term_time = KST 기준 (sajupy core.py 호환 컬럼)
            "term_time",
            # 참고용 추가 컬럼
            "term_time_seoul_lmt", "term_time_utc",
        ])

        # day_pillar 오프셋 교정용 앵커
        # sajupy 기준: 1900-01-01 = 甲戌 (인덱스 10)
        anchor_date = date(1900, 1, 1)
        anchor_pillar_sajupy = "甲戌"
        anchor_idx_sajupy = GAPJA.index(anchor_pillar_sajupy)
        # 오프셋 적용: 실제 앵커는 sajupy 값 + offset
        anchor_idx_corrected = (anchor_idx_sajupy + offset) % 60
        anchor_pillar_corrected = GAPJA[anchor_idx_corrected]

        written = 0
        for row in daily_rows:
            d = date(row["year"], row["month"], row["day"])
            diff = (d - anchor_date).days
            day_idx = (anchor_idx_corrected + diff) % 60
            day_pillar = GAPJA[day_idx]

            # 연주
            year_pillar = compute_year_pillar(d, ipchun_by_year)

            # 월주
            month_pillar = compute_month_pillar(d, year_pillar, monthly_term_dates)

            # 절기 (해당 날짜에 있으면)
            terms_today = term_lookup.get((d.year, d.month, d.day), [])
            # 하루에 여러 개면 첫 번째만 CSV에 (드문 케이스)
            term_hanja = ""
            term_korean = ""
            term_kst = ""
            term_lmt = ""
            term_utc = ""
            if terms_today:
                t = terms_today[0]
                term_hanja = t["hanja"]
                term_korean = t["korean"]
                term_kst = t["kst"].strftime("%Y%m%d%H%M")
                term_lmt = t["lmt"].strftime("%Y%m%d%H%M")
                term_utc = t["utc"].strftime("%Y%m%d%H%M")

            writer.writerow([
                d.year, d.month, d.day,
                day_pillar, month_pillar, year_pillar,
                row["lunar_year"], row["lunar_month"], row["lunar_day"],
                "",  # is_leap_month — sajupy CSV에는 없어 빈칸 (추후 음력 로직에서 처리)
                term_hanja, term_korean,
                term_kst, term_lmt, term_utc,
            ])
            written += 1
        print(f"[OK] {written}건 CSV 저장: {OUT_CSV}")


if __name__ == "__main__":
    main()
