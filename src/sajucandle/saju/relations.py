"""천간/지지 간 관계 (合·沖·刑·破·害) 및 오행 상생상극.

PRD §4-4 수치값(초기 prior)을 기준으로 관계 점수 산출.
실제 가중치는 백테스트 Null Test 결과로 조정된다.
"""

from __future__ import annotations

from typing import Dict, List

from .constants import (
    BRANCH_ELEMENT,
    ELEMENT_GENERATES,
    ELEMENT_OVERCOMES,
    STEM_ELEMENT,
)


# ==========================================================================
# 초기 가중치 (PRD §4-4) — 백테스트로 튜닝 예정
# ==========================================================================

SCORE_SAMHAP = 25     # 삼합 성립 (3자 전부)
SCORE_YUKHAP = 15     # 육합
SCORE_BANHAP = 10     # 반합 (삼합 중 2자)
SCORE_STEM_HAP = 12   # 천간 합 (甲己/乙庚/丙辛/丁壬/戊癸)
SCORE_GENERATE = 12   # 오행 상생
SCORE_SAME_ELEMENT = 5  # 같은 오행

SCORE_BRANCH_CHONG = -18  # 지지 충
SCORE_STEM_CHONG = -12    # 천간 충
SCORE_HYUNG = -10         # 형
SCORE_PA = -6             # 파
SCORE_HAE = -5            # 해
SCORE_OVERCOME = -12      # 상극


# ==========================================================================
# 지지 관계 테이블
# ==========================================================================

# 지지 삼합: 3자 조합 → 오행
SAMHAP_TRIOS = [
    (("申", "子", "辰"), "水"),
    (("寅", "午", "戌"), "火"),
    (("巳", "酉", "丑"), "金"),
    (("亥", "卯", "未"), "木"),
]

# 삼합의 모든 pair → 반합
_BANHAP_PAIRS: Dict[frozenset, str] = {}
for trio, elem in SAMHAP_TRIOS:
    for i in range(3):
        for j in range(i + 1, 3):
            _BANHAP_PAIRS[frozenset({trio[i], trio[j]})] = elem

# 지지 육합: 2자 → 오행
YUKHAP_PAIRS = {
    frozenset({"子", "丑"}): "土",
    frozenset({"寅", "亥"}): "木",
    frozenset({"卯", "戌"}): "火",
    frozenset({"辰", "酉"}): "金",
    frozenset({"巳", "申"}): "水",
    frozenset({"午", "未"}): "火土",  # 관행 혼재
}

# 지지 충 (정충)
BRANCH_CHONG_PAIRS = {
    frozenset({"子", "午"}),
    frozenset({"丑", "未"}),
    frozenset({"寅", "申"}),
    frozenset({"卯", "酉"}),
    frozenset({"辰", "戌"}),
    frozenset({"巳", "亥"}),
}

# 지지 형 (3자 또는 2자)
HYUNG_TRIOS = [
    ("寅", "巳", "申"),  # 지세지형
    ("丑", "戌", "未"),  # 무은지형
]
HYUNG_PAIRS = [
    frozenset({"子", "卯"}),  # 무례지형
]
HYUNG_SELF = {"辰", "午", "酉", "亥"}  # 자형 (같은 지지 둘)

# 파
PA_PAIRS = {
    frozenset({"子", "酉"}),
    frozenset({"丑", "辰"}),
    frozenset({"寅", "亥"}),  # 육합과 겹침
    frozenset({"卯", "午"}),
    frozenset({"巳", "申"}),  # 육합과 겹침
    frozenset({"未", "戌"}),
}

# 해
HAE_PAIRS = {
    frozenset({"子", "未"}),
    frozenset({"丑", "午"}),
    frozenset({"寅", "巳"}),
    frozenset({"卯", "辰"}),
    frozenset({"申", "亥"}),
    frozenset({"酉", "戌"}),
}


# ==========================================================================
# 천간 관계
# ==========================================================================

# 천간 오합
STEM_HAP_PAIRS = {
    frozenset({"甲", "己"}): "土",
    frozenset({"乙", "庚"}): "金",
    frozenset({"丙", "辛"}): "水",
    frozenset({"丁", "壬"}): "木",
    frozenset({"戊", "癸"}): "火",
}

# 천간 충 (甲庚, 乙辛, 丙壬, 丁癸) — 戊己 중앙이라 충 없음
STEM_CHONG_PAIRS = {
    frozenset({"甲", "庚"}),
    frozenset({"乙", "辛"}),
    frozenset({"丙", "壬"}),
    frozenset({"丁", "癸"}),
}


# ==========================================================================
# 분석 함수
# ==========================================================================

def analyze_branch_pair(a: str, b: str) -> List[Dict]:
    """두 지지 사이의 모든 관계를 리스트로 반환. 하나의 쌍에 복수 관계 가능 (예: 寅亥 합+파)."""
    rels: List[Dict] = []
    if not a or not b:
        return rels
    pair = frozenset({a, b})

    if a == b and a in HYUNG_SELF:
        rels.append({"type": "자형(自刑)", "score": SCORE_HYUNG, "detail": f"{a}{a}"})

    if pair in YUKHAP_PAIRS:
        rels.append({
            "type": "육합(六合)",
            "score": SCORE_YUKHAP,
            "element": YUKHAP_PAIRS[pair],
            "detail": f"{a}·{b} 육합",
        })
    if pair in _BANHAP_PAIRS:
        rels.append({
            "type": "반합(半合)",
            "score": SCORE_BANHAP,
            "element": _BANHAP_PAIRS[pair],
            "detail": f"{a}·{b} 반합",
        })
    if pair in BRANCH_CHONG_PAIRS:
        rels.append({"type": "충(沖)", "score": SCORE_BRANCH_CHONG, "detail": f"{a}·{b} 충"})
    if pair in {frozenset(set(t[:2]) | set(t[1:])) for t in HYUNG_TRIOS} or pair in HYUNG_PAIRS:
        # 寅巳, 巳申, 寅申, 丑戌, 戌未, 丑未, 子卯 중
        rels.append({"type": "형(刑)", "score": SCORE_HYUNG, "detail": f"{a}·{b} 형"})
    if pair in PA_PAIRS:
        rels.append({"type": "파(破)", "score": SCORE_PA, "detail": f"{a}·{b} 파"})
    if pair in HAE_PAIRS:
        rels.append({"type": "해(害)", "score": SCORE_HAE, "detail": f"{a}·{b} 해"})

    # 오행 관계 (보조 가중)
    ea, eb = BRANCH_ELEMENT.get(a, ""), BRANCH_ELEMENT.get(b, "")
    if ea and eb and not rels:
        if ea == eb:
            rels.append({"type": "오행동(同)", "score": SCORE_SAME_ELEMENT,
                         "detail": f"{ea} 공유"})
        elif ELEMENT_GENERATES.get(ea) == eb:
            rels.append({"type": "상생", "score": SCORE_GENERATE,
                         "detail": f"{ea}→{eb}"})
        elif ELEMENT_GENERATES.get(eb) == ea:
            rels.append({"type": "상생", "score": SCORE_GENERATE,
                         "detail": f"{eb}→{ea}"})
        elif ELEMENT_OVERCOMES.get(ea) == eb:
            rels.append({"type": "상극", "score": SCORE_OVERCOME,
                         "detail": f"{ea}剋{eb}"})
        elif ELEMENT_OVERCOMES.get(eb) == ea:
            rels.append({"type": "상극", "score": SCORE_OVERCOME,
                         "detail": f"{eb}剋{ea}"})
    return rels


def analyze_stem_pair(a: str, b: str) -> List[Dict]:
    """두 천간 간 관계."""
    rels: List[Dict] = []
    if not a or not b:
        return rels
    pair = frozenset({a, b})

    if pair in STEM_HAP_PAIRS:
        rels.append({"type": "천간합", "score": SCORE_STEM_HAP,
                     "element": STEM_HAP_PAIRS[pair],
                     "detail": f"{a}·{b} 합화 {STEM_HAP_PAIRS[pair]}"})
    if pair in STEM_CHONG_PAIRS:
        rels.append({"type": "천간충", "score": SCORE_STEM_CHONG,
                     "detail": f"{a}·{b} 충"})

    # 오행 관계 (보조)
    ea, eb = STEM_ELEMENT.get(a, ""), STEM_ELEMENT.get(b, "")
    if ea and eb and not rels:
        if ea == eb:
            rels.append({"type": "천간 오행동", "score": SCORE_SAME_ELEMENT,
                         "detail": f"{ea} 공유"})
        elif ELEMENT_GENERATES.get(ea) == eb:
            rels.append({"type": "천간 상생", "score": SCORE_GENERATE,
                         "detail": f"{ea}→{eb}"})
        elif ELEMENT_GENERATES.get(eb) == ea:
            rels.append({"type": "천간 상생", "score": SCORE_GENERATE,
                         "detail": f"{eb}→{ea}"})
        elif ELEMENT_OVERCOMES.get(ea) == eb:
            rels.append({"type": "천간 상극", "score": SCORE_OVERCOME,
                         "detail": f"{ea}剋{eb}"})
        elif ELEMENT_OVERCOMES.get(eb) == ea:
            rels.append({"type": "천간 상극", "score": SCORE_OVERCOME,
                         "detail": f"{eb}剋{ea}"})
    return rels


def pillar_compat_score(pillar_a: str, pillar_b: str) -> Dict:
    """두 간지(천간+지지) 사이의 종합 궁합 점수.

    사용 예: 종목 일주 × 오늘 일진, 종목 일주 × 월운 등.
    """
    if not pillar_a or not pillar_b or len(pillar_a) != 2 or len(pillar_b) != 2:
        return {"total": 0, "stem_rels": [], "branch_rels": [], "error": "invalid pillar"}

    stem_rels = analyze_stem_pair(pillar_a[0], pillar_b[0])
    branch_rels = analyze_branch_pair(pillar_a[1], pillar_b[1])

    total = sum(r["score"] for r in stem_rels) + sum(r["score"] for r in branch_rels)

    pros = [r for r in (stem_rels + branch_rels) if r["score"] > 0]
    cons = [r for r in (stem_rels + branch_rels) if r["score"] < 0]

    return {
        "total": total,
        "stem_rels": stem_rels,
        "branch_rels": branch_rels,
        "pros": pros,
        "cons": cons,
        "pillar_a": pillar_a,
        "pillar_b": pillar_b,
    }


def samhap_detection(branches: List[str]) -> List[Dict]:
    """주어진 지지 리스트에서 삼합 성립 여부 탐지 (연월일시 4자 등)."""
    found = []
    branch_set = set(branches)
    for trio, elem in SAMHAP_TRIOS:
        if set(trio).issubset(branch_set):
            found.append({
                "type": "삼합(三合)",
                "score": SCORE_SAMHAP,
                "element": elem,
                "detail": "".join(trio) + f" 삼합 → {elem}",
            })
    return found


def element_balance(pillars: List[str]) -> Dict:
    """주어진 간지 리스트의 오행 분포와 균형도.

    Returns
    -------
    {
       "counts": {"木": 2, "火": 1, ...},
       "balance_score": 0~10,  # 균등 분포일수록 높음
       "dominant": "木",
       "missing": ["金"]
    }
    """
    counts = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
    for p in pillars:
        if not p or len(p) != 2:
            continue
        s_el = STEM_ELEMENT.get(p[0], "")
        b_el = BRANCH_ELEMENT.get(p[1], "")
        if s_el:
            counts[s_el] += 1
        if b_el:
            counts[b_el] += 1

    total = sum(counts.values())
    if total == 0:
        return {"counts": counts, "balance_score": 0, "dominant": "", "missing": list(counts)}

    # 균등도 점수: 표준편차 역수 기반 0~10
    mean = total / 5
    variance = sum((v - mean) ** 2 for v in counts.values()) / 5
    std = variance ** 0.5
    # 완전 균등이면 std=0 → 10점, std가 mean에 가까울수록 0점
    balance = max(0, 10 - (std / max(mean, 1)) * 10)

    dominant = max(counts, key=counts.get)
    missing = [k for k, v in counts.items() if v == 0]

    return {
        "counts": counts,
        "total": total,
        "balance_score": round(balance, 1),
        "dominant": dominant,
        "missing": missing,
    }
