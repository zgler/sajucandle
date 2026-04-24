"""대운·세운·월운·일진 스모크 테스트."""

import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.manseryeok.core import SajuCalculator
from sajucandle.saju.daeun import compute_daeun
from sajucandle.saju.sewoon import compute_sewoon_wolwoon_ilji

calc = SajuCalculator()

# 테스트 케이스: 1990-10-10 14:30 서울 출생 남자
# (공개 만세력과 수동 비교 가능한 시간)
birth = datetime(1990, 10, 10, 14, 30)
saju = calc.calculate_saju(
    year=birth.year, month=birth.month, day=birth.day,
    hour=birth.hour, minute=birth.minute,
    city="Seoul", use_solar_time=True,
)
print(f"[사주] 1990-10-10 14:30 서울 (남자)")
print(f"  연주: {saju['year_pillar']} / 월주: {saju['month_pillar']}"
      f" / 일주: {saju['day_pillar']} / 시주: {saju['hour_pillar']}\n")

for gender_label, g in [("남자", "M"), ("여자", "F")]:
    daeun = compute_daeun(
        calendar_data=calc.data,
        birth_dt=birth,
        year_pillar=saju['year_pillar'],
        month_pillar=saju['month_pillar'],
        gender=g,
    )
    print(f"[대운] {gender_label} ({daeun['direction']}, 시작 {daeun['start_age_years']}세)")
    for d in daeun['daeun'][:10]:
        print(f"  {d['index']:2d}번째  {d['pillar']}  {d['start_age']:5.1f}세~{d['end_age']:5.1f}세"
              f"  ({d['start_date']} ~ {d['end_date']})")
    print()

# 세운/월운/일진
print("[오늘의 운]")
for dt_str in ["2026-04-23 12:00", "2024-02-04 17:00", "2024-02-04 17:28"]:
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    r = compute_sewoon_wolwoon_ilji(calc, dt)
    print(f"  {r['date']}  세운={r['sewoon']}  월운={r['wolwoon']}  일진={r['ilji']}  시주={r['시주']}")
