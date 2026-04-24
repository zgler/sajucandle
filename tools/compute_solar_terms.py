"""
skyfield로 24절기의 정확한 UTC·KST·서울태양시 시각을 계산한다.

24절기는 태양의 황경(ecliptic longitude)이 15°의 배수에 도달하는 순간.
- 춘분(0°) → 청명(15°) → 곡우(30°) → ... → 우수(330°) → 다시 춘분(360°=0°)

시작 기준: 춘분(0°). 월주 결정용 "절"은 12개(寅월=입춘 315°, 卯월=경칩 345° ...).
하지만 일단 24절기 모두 계산하고 sajupy CSV와 비교한다.
"""

import json
import numpy as np
from pathlib import Path
from datetime import timedelta, timezone, datetime
from skyfield.api import load
from skyfield import almanac
from skyfield.almanac import ecliptic_frame, find_discrete

OUT_DIR = Path(__file__).parent.parent / "data" / "solar_terms"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 24절기 이름 (황경 0°부터 15° 간격)
TERM_NAMES = [
    ("春分", "춘분"),   # 0°
    ("清明", "청명"),   # 15°
    ("穀雨", "곡우"),   # 30°
    ("立夏", "입하"),   # 45°
    ("小滿", "소만"),   # 60°
    ("芒種", "망종"),   # 75°
    ("夏至", "하지"),   # 90°
    ("小暑", "소서"),   # 105°
    ("大暑", "대서"),   # 120°
    ("立秋", "입추"),   # 135°
    ("處暑", "처서"),   # 150°
    ("白露", "백로"),   # 165°
    ("秋分", "추분"),   # 180°
    ("寒露", "한로"),   # 195°
    ("霜降", "상강"),   # 210°
    ("立冬", "입동"),   # 225°
    ("小雪", "소설"),   # 240°
    ("大雪", "대설"),   # 255°
    ("冬至", "동지"),   # 270°
    ("小寒", "소한"),   # 285°
    ("大寒", "대한"),   # 300°
    ("立春", "입춘"),   # 315°
    ("雨水", "우수"),   # 330°
    ("驚蟄", "경칩"),   # 345°
]

# 월주를 바꾸는 12절 (절기 중 홀수 번째, 엄밀히는 315°부터 12개 "節")
# 입춘(315°), 경칩(345°), 청명(15°), 입하(45°), 망종(75°), 소서(105°),
# 입추(135°), 백로(165°), 한로(195°), 입동(225°), 대설(255°), 소한(285°)
MONTHLY_TERMS_HANJA = {
    "立春", "驚蟄", "清明", "立夏", "芒種", "小暑",
    "立秋", "白露", "寒露", "立冬", "大雪", "小寒",
}

# Seoul 평균 태양시 오프셋: 126.9783°E → 표준 135°E로부터 -(135-126.9783)*4 = -32.0868분
# UTC 기준 오프셋: UTC+(126.9783/15) = UTC+8:27:55.99
SEOUL_LMT_OFFSET_MINUTES = 126.9783 / 15 * 60  # = 507.93분 = 8시간 27분 55.9초
KST_OFFSET_MINUTES = 9 * 60  # 540분


def compute_solar_terms(start_year: int, end_year: int):
    """주어진 연도 범위의 24절기 정확 UTC 시각을 계산한다."""
    # DE421은 1899-07 ~ 2053-10만 커버. 1900~2100 전체는 DE440 필요.
    eph = load('de440s.bsp')  # small DE440 변형 (약 32MB, 1849~2150 커버)
    ts = load.timescale()
    earth = eph['earth']
    sun = eph['sun']

    t0 = ts.utc(start_year - 1, 12, 15)
    t1 = ts.utc(end_year + 1, 1, 15)

    def solar_longitude_deg(t):
        """태양 겉보기 황경 (0~360도). 춘분점 기준."""
        astrometric = earth.at(t).observe(sun).apparent()
        _, lon, _ = astrometric.frame_latlon(ecliptic_frame)
        return lon.degrees

    def step_fn(t):
        """태양 황경을 15°씩 24구간으로 나눈 bucket 번호 반환.
        0 = 0~15° (春分~清明 사이), 1 = 15~30° (清明~穀雨), ..."""
        lon = solar_longitude_deg(t)
        return (np.floor(lon / 15).astype(int)) % 24

    step_fn.step_days = 1.0

    times, values = find_discrete(t0, t1, step_fn)

    results = []
    for t, v in zip(times, values):
        # v는 0~23, 이 값이 해당하는 절기는 TERM_NAMES[v]
        # 황경이 15*v 도에 도달한 순간 → TERM_NAMES[v]의 시작
        dt_utc = t.utc_datetime()
        dt_kst = dt_utc + timedelta(minutes=KST_OFFSET_MINUTES)
        dt_lmt = dt_utc + timedelta(minutes=SEOUL_LMT_OFFSET_MINUTES)

        hanja, korean = TERM_NAMES[int(v)]
        results.append({
            "year": int(dt_kst.year),
            "term_hanja": hanja,
            "term_korean": korean,
            "is_monthly_term": hanja in MONTHLY_TERMS_HANJA,
            "longitude_deg": int(15 * v),
            "utc": dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "kst": dt_kst.strftime("%Y-%m-%d %H:%M:%S"),
            "seoul_lmt": dt_lmt.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return results


if __name__ == "__main__":
    import sys, argparse
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1900)
    parser.add_argument("--end", type=int, default=2100)
    args = parser.parse_args()
    start_year, end_year = args.start, args.end
    print(f"[RUN] {start_year}~{end_year} 24절기 계산 시작...")
    terms = compute_solar_terms(start_year, end_year)

    out_file = OUT_DIR / f"solar_terms_{start_year}_{end_year}.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(terms, f, ensure_ascii=False, indent=2)

    print(f"[OK] {len(terms)}건 저장: {out_file}")

    # 2024 입춘만 출력 (검증용)
    ipchun_2024 = [t for t in terms if t["term_hanja"] == "立春" and t["year"] == 2024]
    if ipchun_2024:
        print("\n[CHECK] 2024 立春 정확 시각:")
        for key, val in ipchun_2024[0].items():
            print(f"  {key}: {val}")
