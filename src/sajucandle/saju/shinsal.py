"""신살(神煞) 계산.

투자 맥락에서 활용할 주요 신살 12종:

길신(吉神):
- 천을귀인(天乙貴人): 일간 기준 특정 지지
- 삼기(三奇): 천간 甲戊庚·乙丙丁·壬癸辛 조합
- 천덕귀인(天德貴人): 월지 기준 특정 천간
- 월덕귀인(月德貴人): 월지 기준 특정 천간
- 문창귀인(文昌貴人): 일간 기준
- 금여(金輿): 일간 기준

흉신(凶神):
- 도화살(桃花殺): 년지·일지 기준
- 역마살(驛馬殺): 년지·일지 기준
- 화개살(華蓋殺): 년지·일지 기준
- 백호살(白虎殺): 특정 갑자 조합
- 괴강살(魁罡殺): 특정 일주·시주
- 양인살(羊刃殺): 일간 기준

각 신살의 가중치는 PRD §4-3 초기 prior (±2~5점).
"""

from __future__ import annotations

from typing import Dict, List


# 가중치 (±2~5점)
SCORE_CHEONEUL = +5     # 천을귀인
SCORE_SAMGI = +4
SCORE_CHEONDEOK = +3
SCORE_WOLDEOK = +3
SCORE_MUNCHANG = +3
SCORE_GEUMYEO = +2
SCORE_DOHWA = -2
SCORE_YEONGMA = +2    # 역마는 활동성 → 투자 맥락에선 가산
SCORE_HWAGAE = -2
SCORE_BAEKHO = -4
SCORE_GOEGANG = -3
SCORE_YANGIN = -3


# ======================================================================
# 길신
# ======================================================================

# 천을귀인: 일간 → 귀인 지지들
CHEONEUL_TABLE = {
    "甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
    "乙": ("子", "申"), "己": ("子", "申"),
    "丙": ("亥", "酉"), "丁": ("亥", "酉"),
    "辛": ("寅", "午"),
    "壬": ("巳", "卯"), "癸": ("巳", "卯"),
}

# 천덕귀인: 월지 → 천덕(천간 또는 지지)
CHEONDEOK_TABLE = {
    "寅": "丁", "卯": "申", "辰": "壬", "巳": "辛", "午": "亥", "未": "甲",
    "申": "癸", "酉": "寅", "戌": "丙", "亥": "乙", "子": "巳", "丑": "庚",
}

# 월덕귀인: 월지(삼합) → 월덕 천간
WOLDEOK_TABLE = {
    # 해묘미(木국): 甲
    "亥": "甲", "卯": "甲", "未": "甲",
    # 인오술(火국): 丙
    "寅": "丙", "午": "丙", "戌": "丙",
    # 사유축(金국): 庚
    "巳": "庚", "酉": "庚", "丑": "庚",
    # 신자진(水국): 壬
    "申": "壬", "子": "壬", "辰": "壬",
}

# 문창귀인: 일간 → 문창 지지
MUNCHANG_TABLE = {
    "甲": "巳", "乙": "午", "丙": "申", "丁": "酉", "戊": "申",
    "己": "酉", "庚": "亥", "辛": "子", "壬": "寅", "癸": "卯",
}

# 금여: 일간 → 금여 지지
GEUMYEO_TABLE = {
    "甲": "辰", "乙": "巳", "丙": "未", "丁": "申", "戊": "未",
    "己": "申", "庚": "戌", "辛": "亥", "壬": "丑", "癸": "寅",
}


# ======================================================================
# 흉신
# ======================================================================

# 도화살: 년지·일지의 지지 → 도화 지지
DOHWA_TABLE = {
    # 인오술 → 卯
    "寅": "卯", "午": "卯", "戌": "卯",
    # 신자진 → 酉
    "申": "酉", "子": "酉", "辰": "酉",
    # 해묘미 → 子
    "亥": "子", "卯": "子", "未": "子",
    # 사유축 → 午
    "巳": "午", "酉": "午", "丑": "午",
}

# 역마살: 년지·일지 → 역마 지지
YEONGMA_TABLE = {
    "寅": "申", "午": "申", "戌": "申",
    "申": "寅", "子": "寅", "辰": "寅",
    "亥": "巳", "卯": "巳", "未": "巳",
    "巳": "亥", "酉": "亥", "丑": "亥",
}

# 화개살: 년지·일지 → 화개 지지
HWAGAE_TABLE = {
    "寅": "戌", "午": "戌", "戌": "戌",
    "申": "辰", "子": "辰", "辰": "辰",
    "亥": "未", "卯": "未", "未": "未",
    "巳": "丑", "酉": "丑", "丑": "丑",
}

# 백호살: 갑진·을미·병술·정축·무진·임술·계축
BAEKHO_PILLARS = {"甲辰", "乙未", "丙戌", "丁丑", "戊辰", "壬戌", "癸丑"}

# 괴강살: 경진·경술·임진·임술·무술
GOEGANG_PILLARS = {"庚辰", "庚戌", "壬辰", "壬戌", "戊戌"}

# 양인살: 일간(양간) → 양인 지지
YANGIN_TABLE = {
    "甲": "卯",
    "丙": "午",
    "戊": "午",
    "庚": "酉",
    "壬": "子",
}

# 삼기: 갑무경 / 을병정 / 임계신 — 3자 모두 있어야 성립
SAMGI_GROUPS = [
    {"甲", "戊", "庚"},
    {"乙", "丙", "丁"},
    {"壬", "癸", "辛"},
]


def find_shinsal(saju: Dict) -> List[Dict]:
    """4주 간지로부터 성립하는 모든 신살을 리스트로 반환.

    입력: SajuCalculator.calculate_saju() 결과.
    """
    if not saju:
        return []
    day_stem = saju.get("day_stem", "")
    month_branch = saju.get("month_branch", "")
    year_branch = saju.get("year_branch", "")
    day_branch = saju.get("day_branch", "")
    hour_branch = saju.get("hour_branch", "")
    all_branches = [year_branch, month_branch, day_branch, hour_branch]
    all_stems = [saju.get("year_stem", ""), saju.get("month_stem", ""),
                 day_stem, saju.get("hour_stem", "")]

    findings: List[Dict] = []

    # 천을귀인
    cheoneul = CHEONEUL_TABLE.get(day_stem, ())
    for b in all_branches:
        if b in cheoneul:
            findings.append({"name": "천을귀인", "score": SCORE_CHEONEUL,
                             "where": b, "type": "길"})

    # 천덕귀인: 월지 → 특정 천간 or 지지
    cheondeok = CHEONDEOK_TABLE.get(month_branch, "")
    if cheondeok and (cheondeok in all_stems or cheondeok in all_branches):
        findings.append({"name": "천덕귀인", "score": SCORE_CHEONDEOK,
                         "where": cheondeok, "type": "길"})

    # 월덕귀인: 월지 → 천간
    woldeok = WOLDEOK_TABLE.get(month_branch, "")
    if woldeok in all_stems:
        findings.append({"name": "월덕귀인", "score": SCORE_WOLDEOK,
                         "where": woldeok, "type": "길"})

    # 문창귀인
    munchang = MUNCHANG_TABLE.get(day_stem, "")
    if munchang in all_branches:
        findings.append({"name": "문창귀인", "score": SCORE_MUNCHANG,
                         "where": munchang, "type": "길"})

    # 금여
    geumyeo = GEUMYEO_TABLE.get(day_stem, "")
    if geumyeo in all_branches:
        findings.append({"name": "금여", "score": SCORE_GEUMYEO,
                         "where": geumyeo, "type": "길"})

    # 삼기
    stem_set = set(all_stems)
    for group in SAMGI_GROUPS:
        if group.issubset(stem_set):
            findings.append({"name": f"삼기({''.join(sorted(group))})",
                             "score": SCORE_SAMGI, "type": "길"})

    # 도화
    for b in [year_branch, day_branch]:
        dohwa = DOHWA_TABLE.get(b, "")
        if dohwa and dohwa in all_branches:
            findings.append({"name": "도화살", "score": SCORE_DOHWA,
                             "where": dohwa, "type": "흉"})
            break  # 중복 방지

    # 역마
    for b in [year_branch, day_branch]:
        yeongma = YEONGMA_TABLE.get(b, "")
        if yeongma and yeongma in all_branches:
            findings.append({"name": "역마살", "score": SCORE_YEONGMA,
                             "where": yeongma, "type": "중립"})
            break

    # 화개
    for b in [year_branch, day_branch]:
        hwagae = HWAGAE_TABLE.get(b, "")
        if hwagae and hwagae in all_branches:
            findings.append({"name": "화개살", "score": SCORE_HWAGAE,
                             "where": hwagae, "type": "흉"})
            break

    # 백호살
    for p in [saju.get("year_pillar"), saju.get("month_pillar"),
              saju.get("day_pillar"), saju.get("hour_pillar")]:
        if p in BAEKHO_PILLARS:
            findings.append({"name": "백호살", "score": SCORE_BAEKHO,
                             "where": p, "type": "흉"})

    # 괴강살
    for p in [saju.get("year_pillar"), saju.get("month_pillar"),
              saju.get("day_pillar"), saju.get("hour_pillar")]:
        if p in GOEGANG_PILLARS:
            findings.append({"name": "괴강살", "score": SCORE_GOEGANG,
                             "where": p, "type": "흉"})

    # 양인살 (일간이 양간인 경우만)
    yangin = YANGIN_TABLE.get(day_stem, "")
    if yangin and yangin in all_branches:
        findings.append({"name": "양인살", "score": SCORE_YANGIN,
                         "where": yangin, "type": "흉"})

    return findings


def shinsal_total_score(findings: List[Dict]) -> int:
    """신살 종합 점수 합산. PRD 사주 점수 100점 중 '신살 보정' 10점에 들어감."""
    if not findings:
        return 0
    # -10 ~ +10 범위로 클립
    total = sum(f["score"] for f in findings)
    return max(-10, min(10, total))
