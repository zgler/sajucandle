"""relations + tengod + shinsal 통합 스모크 테스트.

케이스:
- 1990-10-10 14:30 서울 (남자) — 종합 사주 분석
- 2026-04-23 12:00 (오늘 일진) × 1990 종목 일주 궁합
- 삼합·충 엣지 사례
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sajucandle.manseryeok.core import SajuCalculator
from sajucandle.saju.relations import (
    pillar_compat_score,
    samhap_detection,
    element_balance,
)
from sajucandle.saju.tengod import tengod_distribution, ten_god_for_stem
from sajucandle.saju.shinsal import find_shinsal, shinsal_total_score

calc = SajuCalculator()

# ---------------------------------------------------------------
# 케이스 1: 1990-10-10 14:30 서울 (남자) 종합 분석
# ---------------------------------------------------------------
saju = calc.calculate_saju(
    year=1990, month=10, day=10, hour=14, minute=30,
    city="Seoul", use_solar_time=True,
)
print("=" * 60)
print("케이스 1: 1990-10-10 14:30 서울 (남자)")
print("=" * 60)
print(f"사주: 연={saju['year_pillar']} 월={saju['month_pillar']}"
      f" 일={saju['day_pillar']} 시={saju['hour_pillar']}\n")

# 오행 균형
pillars = [saju['year_pillar'], saju['month_pillar'],
           saju['day_pillar'], saju['hour_pillar']]
balance = element_balance(pillars)
print(f"[오행] 분포: {balance['counts']}")
print(f"       균형점수: {balance['balance_score']}/10, 주류={balance['dominant']}, 부재={balance['missing']}")

# 삼합 탐지
branches = [saju['year_branch'], saju['month_branch'],
            saju['day_branch'], saju['hour_branch']]
samhap = samhap_detection(branches)
print(f"[삼합] {samhap}")

# 십신 분포
tg = tengod_distribution(saju)
print(f"\n[십신] 일간={tg['day_stem']}")
for role in ["year", "month", "day", "hour"]:
    sk = f"{role}_stem_tg"
    bk = f"{role}_branch_tg"
    if sk in tg or bk in tg:
        print(f"  {role}: 간={tg.get(sk, '-'):<4}  지={tg.get(bk, '-')}")
print(f"  그룹별: {tg['group_counts']}  → 주류: {tg['dominant_group']}")

# 신살
ss = find_shinsal(saju)
print(f"\n[신살] {len(ss)}건")
for s in ss:
    print(f"  {s['name']:<10} ({s['type']}) 점수={s['score']:+d}  위치={s.get('where','')}")
print(f"  합산 (보정 ±10): {shinsal_total_score(ss):+d}점")

# ---------------------------------------------------------------
# 케이스 2: 오늘(2026-04-23) 일진 × 위 사주의 일주 궁합
# ---------------------------------------------------------------
today_saju = calc.calculate_saju(year=2026, month=4, day=23, hour=12, minute=0, use_solar_time=False)
today_ilji = today_saju['day_pillar']
my_ilju = saju['day_pillar']

print("\n" + "=" * 60)
print(f"케이스 2: 오늘 일진({today_ilji}) × 종목 일주({my_ilju}) 궁합")
print("=" * 60)
score = pillar_compat_score(my_ilju, today_ilji)
print(f"종합 점수: {score['total']:+d}")
print(f"천간 관계: {score['stem_rels']}")
print(f"지지 관계: {score['branch_rels']}")
print(f"긍정: {[r['type'] + ' ' + r.get('detail','') for r in score['pros']]}")
print(f"부정: {[r['type'] + ' ' + r.get('detail','') for r in score['cons']]}")

# ---------------------------------------------------------------
# 케이스 3: 엣지 케이스 모음
# ---------------------------------------------------------------
print("\n" + "=" * 60)
print("케이스 3: 관계 엣지 테스트")
print("=" * 60)
edge_cases = [
    ("甲子", "庚午"),   # 천간 충 + 지지 충
    ("甲子", "己丑"),   # 천간 합 + 지지 합 (子丑合)
    ("寅申", "寅申"),   # 동일 (자기 vs 자기)
    ("丙午", "丙午"),   # 양인 포함 동일
    ("甲寅", "乙卯"),   # 같은 오행 (木)
    ("壬子", "癸亥"),   # 같은 오행 水
]
for a, b in edge_cases:
    r = pillar_compat_score(a, b)
    print(f"{a} × {b}: {r['total']:+3d}점  |  "
          f"천간 {[x['type'] for x in r['stem_rels']]}  "
          f"지지 {[x['type'] for x in r['branch_rels']]}")

# ---------------------------------------------------------------
# 상세 JSON 저장
# ---------------------------------------------------------------
out = {
    "case1_saju": saju,
    "case1_balance": balance,
    "case1_tengod": tg,
    "case1_shinsal": ss,
    "case2_ilji_compat": score,
}
out_file = Path(__file__).parent / "smoke_output_scoring.json"
with out_file.open("w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2, default=str)
print(f"\n상세 JSON: {out_file}")
