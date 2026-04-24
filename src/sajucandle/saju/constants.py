"""사주 계산 공용 상수 및 기초 매핑."""

# 천간 (10干)
STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

# 지지 (12支)
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 60갑자
GAPJA = [STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)]


def gapja_index(pillar: str) -> int:
    """갑자 인덱스. 없으면 -1."""
    try:
        return GAPJA.index(pillar)
    except ValueError:
        return -1


# 천간 오행
STEM_ELEMENT = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# 지지 오행
BRANCH_ELEMENT = {
    "寅": "木", "卯": "木",
    "巳": "火", "午": "火",
    "辰": "土", "戌": "土", "丑": "土", "未": "土",
    "申": "金", "酉": "金",
    "亥": "水", "子": "水",
}

# 천간 음양
STEM_YIN_YANG = {
    "甲": "陽", "丙": "陽", "戊": "陽", "庚": "陽", "壬": "陽",
    "乙": "陰", "丁": "陰", "己": "陰", "辛": "陰", "癸": "陰",
}

# 지지 음양
BRANCH_YIN_YANG = {
    "子": "陽", "寅": "陽", "辰": "陽", "午": "陽", "申": "陽", "戌": "陽",
    "丑": "陰", "卯": "陰", "巳": "陰", "未": "陰", "酉": "陰", "亥": "陰",
}

# 지지 → 월지 순서 (입춘부터 1월 寅)
# 寅=1월 卯=2월 辰=3월 巳=4월 午=5월 未=6월
# 申=7월 酉=8월 戌=9월 亥=10월 子=11월 丑=12월
BRANCH_TO_MONTH_ORDER = {
    "寅": 1, "卯": 2, "辰": 3, "巳": 4, "午": 5, "未": 6,
    "申": 7, "酉": 8, "戌": 9, "亥": 10, "子": 11, "丑": 12,
}
MONTH_ORDER_TO_BRANCH = {v: k for k, v in BRANCH_TO_MONTH_ORDER.items()}


def is_yang_stem(stem: str) -> bool:
    return STEM_YIN_YANG.get(stem) == "陽"


def is_yang_year(year_pillar: str) -> bool:
    """연주의 천간이 양이면 True."""
    if not year_pillar:
        return False
    return is_yang_stem(year_pillar[0])


def element_of_stem(stem: str) -> str:
    return STEM_ELEMENT.get(stem, "")


def element_of_branch(branch: str) -> str:
    return BRANCH_ELEMENT.get(branch, "")


# 상생 관계 (A가 B를 생함): {A: B}
ELEMENT_GENERATES = {
    "木": "火",
    "火": "土",
    "土": "金",
    "金": "水",
    "水": "木",
}

# 상극 관계 (A가 B를 극함): {A: B}
ELEMENT_OVERCOMES = {
    "木": "土",
    "土": "水",
    "水": "火",
    "火": "金",
    "金": "木",
}


def element_relation(a: str, b: str) -> str:
    """두 오행의 관계. "同", "生(A→B)", "生(B→A)", "剋(A→B)", "剋(B→A)", ""."""
    if not a or not b:
        return ""
    if a == b:
        return "同"
    if ELEMENT_GENERATES.get(a) == b:
        return "生(A→B)"
    if ELEMENT_GENERATES.get(b) == a:
        return "生(B→A)"
    if ELEMENT_OVERCOMES.get(a) == b:
        return "剋(A→B)"
    if ELEMENT_OVERCOMES.get(b) == a:
        return "剋(B→A)"
    return ""
