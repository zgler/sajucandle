"""
사주캔들 (SajuCandle) — 사주 엔진 프로토타입 v0.1
=================================================
만세력 변환 → 명식(命式) 계산 → 4축 점수 산출 → 시진 점수 → 진입 추천 등급

사용법:
    from saju_engine import SajuEngine
    engine = SajuEngine()
    bazi = engine.calc_bazi(1990, 3, 15, hour=14)
    score = engine.calc_daily_score(bazi, date(2026, 4, 15), asset_class="swing")
    print(score)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional
from lunar_python import Solar


# ─────────────────────────────────────────────
# 1. 기초 데이터 — 천간, 지지, 오행, 관계 테이블
# ─────────────────────────────────────────────

TIANGAN = list("甲乙丙丁戊己庚辛壬癸")    # 천간 10개
DIZHI   = list("子丑寅卯辰巳午未申酉戌亥")  # 지지 12개

class WuXing(str, Enum):
    MU   = "木"  # 목
    HUO  = "火"  # 화
    TU   = "土"  # 토
    JIN  = "金"  # 금
    SHUI = "水"  # 수

# 천간 → 오행
TIANGAN_WUXING = {
    "甲": WuXing.MU,  "乙": WuXing.MU,
    "丙": WuXing.HUO, "丁": WuXing.HUO,
    "戊": WuXing.TU,  "己": WuXing.TU,
    "庚": WuXing.JIN, "辛": WuXing.JIN,
    "壬": WuXing.SHUI,"癸": WuXing.SHUI,
}

# 지지 → 오행 (정기 기준)
DIZHI_WUXING = {
    "子": WuXing.SHUI,"丑": WuXing.TU,
    "寅": WuXing.MU,  "卯": WuXing.MU,
    "辰": WuXing.TU,  "巳": WuXing.HUO,
    "午": WuXing.HUO, "未": WuXing.TU,
    "申": WuXing.JIN, "酉": WuXing.JIN,
    "戌": WuXing.TU,  "亥": WuXing.SHUI,
}

# 천간 음양 (짝수 인덱스 = 양, 홀수 = 음)
TIANGAN_YINYANG = {g: ("양" if i % 2 == 0 else "음") for i, g in enumerate(TIANGAN)}

# 오행 생극 관계
SHENG = {  # A 생 B (A가 B를 낳음)
    WuXing.MU: WuXing.HUO, WuXing.HUO: WuXing.TU,
    WuXing.TU: WuXing.JIN, WuXing.JIN: WuXing.SHUI,
    WuXing.SHUI: WuXing.MU,
}
KE = {  # A 극 B (A가 B를 이김)
    WuXing.MU: WuXing.TU, WuXing.TU: WuXing.SHUI,
    WuXing.SHUI: WuXing.HUO, WuXing.HUO: WuXing.JIN,
    WuXing.JIN: WuXing.MU,
}

# 천간합 (天干合): 甲己, 乙庚, 丙辛, 丁壬, 戊癸
TIANGAN_HE = {
    "甲": "己", "己": "甲",
    "乙": "庚", "庚": "乙",
    "丙": "辛", "辛": "丙",
    "丁": "壬", "壬": "丁",
    "戊": "癸", "癸": "戊",
}

# 지지 육합 (六合)
DIZHI_LIUHE = {
    "子": "丑", "丑": "子",
    "寅": "亥", "亥": "寅",
    "卯": "戌", "戌": "卯",
    "辰": "酉", "酉": "辰",
    "巳": "申", "申": "巳",
    "午": "未", "未": "午",
}

# 지지 육충 (六沖)
DIZHI_CHONG = {
    "子": "午", "午": "子",
    "丑": "未", "未": "丑",
    "寅": "申", "申": "寅",
    "卯": "酉", "酉": "卯",
    "辰": "戌", "戌": "辰",
    "巳": "亥", "亥": "巳",
}

# 지지 삼합 (三合) — 각 지지가 참여하는 삼합 세트
DIZHI_SANHE = {
    "申": ("申", "子", "辰"),  # 수국
    "子": ("申", "子", "辰"),
    "辰": ("申", "子", "辰"),
    "寅": ("寅", "午", "戌"),  # 화국
    "午": ("寅", "午", "戌"),
    "戌": ("寅", "午", "戌"),
    "巳": ("巳", "酉", "丑"),  # 금국
    "酉": ("巳", "酉", "丑"),
    "丑": ("巳", "酉", "丑"),
    "亥": ("亥", "卯", "未"),  # 목국
    "卯": ("亥", "卯", "未"),
    "未": ("亥", "卯", "未"),
}

# 지지 형(刑) — 간략화
DIZHI_XING = {
    "寅": "巳", "巳": "申", "申": "寅",  # 무례지형
    "丑": "戌", "戌": "未", "未": "丑",  # 무은지형
    "子": "卯", "卯": "子",              # 무례지형
    "辰": "辰", "午": "午", "酉": "酉", "亥": "亥",  # 자형
}

# 지지 해(害)
DIZHI_HAI = {
    "子": "未", "未": "子",
    "丑": "午", "午": "丑",
    "寅": "巳", "巳": "寅",
    "卯": "辰", "辰": "卯",
    "申": "亥", "亥": "申",
    "酉": "戌", "戌": "酉",
}

# 시진 매핑 (시간 → 지지)
HOUR_TO_SHICHEN = {
    23: "子", 0: "子", 1: "丑", 2: "丑",
    3: "寅", 4: "寅", 5: "卯", 6: "卯",
    7: "辰", 8: "辰", 9: "巳", 10: "巳",
    11: "午", 12: "午", 13: "未", 14: "未",
    15: "申", 16: "申", 17: "酉", 18: "酉",
    19: "戌", 20: "戌", 21: "亥", 22: "亥",
}

SHICHEN_TIME_RANGES = {
    "子": "23:00~01:00", "丑": "01:00~03:00",
    "寅": "03:00~05:00", "卯": "05:00~07:00",
    "辰": "07:00~09:00", "巳": "09:00~11:00",
    "午": "11:00~13:00", "未": "13:00~15:00",
    "申": "15:00~17:00", "酉": "17:00~19:00",
    "戌": "19:00~21:00", "亥": "21:00~23:00",
}


# ─────────────────────────────────────────────
# 2. 십성(十星) 계산
# ─────────────────────────────────────────────

class TenGod(str, Enum):
    BIJIAN   = "비견"   # 比肩
    JIECAI   = "겁재"   # 劫財
    SHISHEN  = "식신"   # 食神
    SHANGGUAN= "상관"   # 傷官
    PIANCAI  = "편재"   # 偏財
    ZHENGCAI = "정재"   # 正財
    PIANGUAN = "편관"   # 偏官 (七殺)
    ZHENGGUAN= "정관"   # 正官
    PIANYIN  = "편인"   # 偏印
    ZHENGYIN = "정인"   # 正印


def calc_ten_god(day_master: str, target: str) -> TenGod:
    """일간(日干) 기준으로 대상 천간의 십성을 계산"""
    dm_wx = TIANGAN_WUXING[day_master]
    tg_wx = TIANGAN_WUXING[target]
    dm_yy = TIANGAN_YINYANG[day_master]
    tg_yy = TIANGAN_YINYANG[target]
    same_yy = (dm_yy == tg_yy)

    if dm_wx == tg_wx:
        return TenGod.BIJIAN if same_yy else TenGod.JIECAI
    elif SHENG[dm_wx] == tg_wx:  # 내가 생하는 것
        return TenGod.SHISHEN if same_yy else TenGod.SHANGGUAN
    elif KE[dm_wx] == tg_wx:     # 내가 극하는 것
        return TenGod.PIANCAI if same_yy else TenGod.ZHENGCAI
    elif KE[tg_wx] == dm_wx:     # 나를 극하는 것
        return TenGod.PIANGUAN if same_yy else TenGod.ZHENGGUAN
    elif SHENG[tg_wx] == dm_wx:  # 나를 생하는 것
        return TenGod.PIANYIN if same_yy else TenGod.ZHENGYIN
    return TenGod.BIJIAN  # fallback


def calc_ten_god_for_branch(day_master: str, branch: str) -> TenGod:
    """지지의 정기(正氣) 기준으로 십성 계산 (간략화)"""
    branch_wx = DIZHI_WUXING[branch]
    dummy_gan = next(g for g, wx in TIANGAN_WUXING.items() if wx == branch_wx)
    return calc_ten_god(day_master, dummy_gan)


# ─────────────────────────────────────────────
# 3. 데이터 모델
# ─────────────────────────────────────────────

@dataclass
class BaziChart:
    """사용자 명식 (사주 팔자)"""
    birth_solar: str
    birth_lunar: str

    year_gan: str
    year_zhi: str
    month_gan: str
    month_zhi: str
    day_gan: str       # 일간 = 본인
    day_zhi: str
    hour_gan: Optional[str] = None
    hour_zhi: Optional[str] = None

    # 파생 속성
    wuxing_dist: dict = field(default_factory=dict)    # 오행 분포
    ten_gods: dict = field(default_factory=dict)       # 각 기둥의 십성
    yongsin: Optional[WuXing] = None                   # 용신
    day_master_strength: str = "중"                     # 신강/신약/중

    def summary(self) -> str:
        pillars = f"{self.year_gan}{self.year_zhi} {self.month_gan}{self.month_zhi} {self.day_gan}{self.day_zhi}"
        if self.hour_gan:
            pillars += f" {self.hour_gan}{self.hour_zhi}"
        return (
            f"사주: {pillars}\n"
            f"일간: {self.day_gan} ({TIANGAN_WUXING[self.day_gan].value})\n"
            f"오행 분포: {self.wuxing_dist}\n"
            f"일간 강약: {self.day_master_strength}\n"
            f"용신: {self.yongsin.value if self.yongsin else '미정'}\n"
        )


@dataclass
class ScoreCard:
    """일일 사주 점수"""
    target_date: date
    iljin: str                    # 당일 일진 (예: "庚申")
    asset_class: str

    wealth_score: int             # 재물운 0~100
    decision_score: int           # 결단운 0~100
    volatility_score: int         # 충돌운 0~100
    flow_score: int               # 합운 0~100
    composite_score: int          # 종합 0~100
    signal_grade: str             # 신호 등급

    wealth_reason: str = ""
    decision_reason: str = ""
    volatility_reason: str = ""
    flow_reason: str = ""

    best_hours: list = field(default_factory=list)  # 추천 시진

    def summary(self) -> str:
        return (
            f"── {self.target_date} ({self.iljin}) ── [{self.asset_class}]\n"
            f"재물운: {self.wealth_score:>3}  | {self.wealth_reason}\n"
            f"결단운: {self.decision_score:>3}  | {self.decision_reason}\n"
            f"충돌운: {self.volatility_score:>3}  | {self.volatility_reason}\n"
            f"합  운: {self.flow_score:>3}  | {self.flow_reason}\n"
            f"────────────────────────────────────\n"
            f"종합:   {self.composite_score:>3}  | {self.signal_grade}\n"
            f"추천 시진: {', '.join(f'{h[0]}시 {h[1]}' for h in self.best_hours)}\n"
        )


# ─────────────────────────────────────────────
# 4. 사주 엔진 (메인 클래스)
# ─────────────────────────────────────────────

# 자산군별 4축 가중치
ASSET_WEIGHTS = {
    "scalp":  {"wealth": 0.30, "decision": 0.25, "volatility": 0.25,  "flow": 0.20},
    "swing":  {"wealth": 0.35, "decision": 0.30, "volatility": 0.10,  "flow": 0.25},
    "long":   {"wealth": 0.30, "decision": 0.25, "volatility": -0.10, "flow": 0.35},
    "default":{"wealth": 0.30, "decision": 0.30, "volatility": 0.15,  "flow": 0.25},
}


class SajuEngine:

    def calc_bazi(
        self,
        year: int,
        month: int,
        day: int,
        hour: Optional[int] = None,
        is_lunar: bool = False,
    ) -> BaziChart:
        """생년월일시 → 명식(BaziChart) 계산"""

        if is_lunar:
            from lunar_python import Lunar
            lunar = Lunar.fromYmd(year, month, day)
            solar = lunar.getSolar()
        else:
            solar = Solar.fromYmd(year, month, day)
            lunar = solar.getLunar()

        ec = lunar.getEightChar()

        chart = BaziChart(
            birth_solar=str(solar),
            birth_lunar=str(lunar),
            year_gan=ec.getYearGan(),
            year_zhi=ec.getYearZhi(),
            month_gan=ec.getMonthGan(),
            month_zhi=ec.getMonthZhi(),
            day_gan=ec.getDayGan(),
            day_zhi=ec.getDayZhi(),
        )

        # 시주 계산 (hour가 주어진 경우)
        if hour is not None:
            shichen_zhi = HOUR_TO_SHICHEN.get(hour, "子")
            chart.hour_zhi = shichen_zhi
            # 시간 천간은 일간 기준으로 계산 (오호둔시법 간략화)
            chart.hour_gan = self._calc_hour_gan(chart.day_gan, shichen_zhi)

        # 오행 분포 계산
        chart.wuxing_dist = self._calc_wuxing_distribution(chart)

        # 십성 계산
        chart.ten_gods = self._calc_ten_gods(chart)

        # 일간 강약 판단
        chart.day_master_strength = self._judge_strength(chart)

        # 용신 결정 (간략화)
        chart.yongsin = self._determine_yongsin(chart)

        return chart

    def calc_daily_score(
        self,
        bazi: BaziChart,
        target_date: date,
        asset_class: str = "default",
    ) -> ScoreCard:
        """명식 + 날짜 → 일일 4축 점수 + 종합 점수 + 신호등급"""

        # 당일 일진 추출
        solar = Solar.fromYmd(target_date.year, target_date.month, target_date.day)
        lunar = solar.getLunar()
        ec = lunar.getEightChar()
        iljin_gan = ec.getDayGan()
        iljin_zhi = ec.getDayZhi()
        iljin = f"{iljin_gan}{iljin_zhi}"

        # 일진의 십성 (사용자 일간 기준)
        iljin_ten_god = calc_ten_god(bazi.day_gan, iljin_gan)
        iljin_branch_ten_god = calc_ten_god_for_branch(bazi.day_gan, iljin_zhi)

        # ── 축 1: 재물운 ──
        wealth, w_reason = self._calc_wealth(bazi, iljin_gan, iljin_zhi, iljin_ten_god, iljin_branch_ten_god)

        # ── 축 2: 결단운 ──
        decision, d_reason = self._calc_decision(bazi, iljin_gan, iljin_zhi, iljin_ten_god)

        # ── 축 3: 충돌운 ──
        volatility, v_reason = self._calc_volatility(bazi, iljin_zhi)

        # ── 축 4: 합운 ──
        flow, f_reason = self._calc_flow(bazi, iljin_gan, iljin_zhi)

        # ── 종합 점수 ──
        weights = ASSET_WEIGHTS.get(asset_class, ASSET_WEIGHTS["default"])
        composite = int(
            wealth * weights["wealth"]
            + decision * weights["decision"]
            + volatility * weights["volatility"]
            + flow * weights["flow"]
        )
        composite = max(0, min(100, composite))

        # ── 결단운 게이트 ──
        grade = self._determine_grade(composite, decision)

        # ── 시진 점수 ──
        best_hours = self._calc_best_hours(bazi, iljin_gan, iljin_zhi, target_date)

        return ScoreCard(
            target_date=target_date,
            iljin=iljin,
            asset_class=asset_class,
            wealth_score=wealth,
            decision_score=decision,
            volatility_score=volatility,
            flow_score=flow,
            composite_score=composite,
            signal_grade=grade,
            wealth_reason=w_reason,
            decision_reason=d_reason,
            volatility_reason=v_reason,
            flow_reason=f_reason,
            best_hours=best_hours,
        )

    # ─────────────────────────────────────────
    # 내부 메서드: 명식 계산
    # ─────────────────────────────────────────

    def _calc_hour_gan(self, day_gan: str, hour_zhi: str) -> str:
        """오호둔시법(五虎遁時法)으로 시간 천간 계산"""
        base_map = {"甲": 0, "己": 0, "乙": 2, "庚": 2,
                    "丙": 4, "辛": 4, "丁": 6, "壬": 6,
                    "戊": 8, "癸": 8}
        base = base_map.get(day_gan, 0)
        zhi_idx = DIZHI.index(hour_zhi)
        gan_idx = (base + zhi_idx) % 10
        return TIANGAN[gan_idx]

    def _calc_wuxing_distribution(self, chart: BaziChart) -> dict:
        dist = {wx: 0 for wx in WuXing}
        elements = [
            chart.year_gan, chart.year_zhi,
            chart.month_gan, chart.month_zhi,
            chart.day_gan, chart.day_zhi,
        ]
        if chart.hour_gan:
            elements.extend([chart.hour_gan, chart.hour_zhi])

        for e in elements:
            wx = TIANGAN_WUXING.get(e) or DIZHI_WUXING.get(e)
            if wx:
                dist[wx] += 1
        return {k.value: v for k, v in dist.items()}

    def _calc_ten_gods(self, chart: BaziChart) -> dict:
        dm = chart.day_gan
        gods = {
            "year_gan": calc_ten_god(dm, chart.year_gan),
            "month_gan": calc_ten_god(dm, chart.month_gan),
            "year_zhi": calc_ten_god_for_branch(dm, chart.year_zhi),
            "month_zhi": calc_ten_god_for_branch(dm, chart.month_zhi),
            "day_zhi": calc_ten_god_for_branch(dm, chart.day_zhi),
        }
        if chart.hour_gan:
            gods["hour_gan"] = calc_ten_god(dm, chart.hour_gan)
            gods["hour_zhi"] = calc_ten_god_for_branch(dm, chart.hour_zhi)
        return gods

    def _judge_strength(self, chart: BaziChart) -> str:
        """일간 강약 판단 (간략화)"""
        dm_wx = TIANGAN_WUXING[chart.day_gan]
        supporting = 0  # 비견·겁재·인성

        for pos, god in chart.ten_gods.items():
            if god in (TenGod.BIJIAN, TenGod.JIECAI, TenGod.PIANYIN, TenGod.ZHENGYIN):
                supporting += 1

        # 월지가 일간을 생하거나 같은 오행이면 추가
        month_wx = DIZHI_WUXING[chart.month_zhi]
        if month_wx == dm_wx or SHENG[month_wx] == dm_wx:
            supporting += 1.5

        if supporting >= 4:
            return "신강"
        elif supporting <= 1.5:
            return "신약"
        return "중"

    def _determine_yongsin(self, chart: BaziChart) -> WuXing:
        """용신 결정 (MVP 간략화: 신강이면 설기/재성, 신약이면 인성/비겁)"""
        dm_wx = TIANGAN_WUXING[chart.day_gan]

        if chart.day_master_strength == "신강":
            # 강한 일간 → 설기(食傷)가 용신: 내가 생하는 오행
            return SHENG[dm_wx]
        elif chart.day_master_strength == "신약":
            # 약한 일간 → 인성이 용신: 나를 생하는 오행
            for wx, target in SHENG.items():
                if target == dm_wx:
                    return wx
        # 중립 → 재성이 용신: 내가 극하는 오행
        return KE[dm_wx]

    # ─────────────────────────────────────────
    # 내부 메서드: 4축 점수 산출
    # ─────────────────────────────────────────

    def _calc_wealth(self, bazi, iljin_gan, iljin_zhi, iljin_tg, iljin_btg):
        """축 1: 재물운"""
        score = 50
        reasons = []

        if iljin_tg == TenGod.ZHENGCAI:
            score += 25
            reasons.append(f"일진 {iljin_gan}이 정재(正財)")
        elif iljin_tg == TenGod.PIANCAI:
            score += 20
            reasons.append(f"일진 {iljin_gan}이 편재(偏財)")
        elif iljin_btg == TenGod.ZHENGCAI:
            score += 15
            reasons.append(f"일진 지지 {iljin_zhi}가 정재")
        elif iljin_btg == TenGod.PIANCAI:
            score += 12
            reasons.append(f"일진 지지 {iljin_zhi}가 편재")

        # 일진 지지와 명식 재성 지지의 합/충
        bazi_branches = [bazi.year_zhi, bazi.month_zhi, bazi.day_zhi]
        if bazi.hour_zhi:
            bazi_branches.append(bazi.hour_zhi)

        for bz in bazi_branches:
            god = calc_ten_god_for_branch(bazi.day_gan, bz)
            if god in (TenGod.PIANCAI, TenGod.ZHENGCAI):
                if DIZHI_LIUHE.get(iljin_zhi) == bz:
                    score += 15
                    reasons.append(f"{iljin_zhi}와 {bz} 육합 (재성 강화)")
                if DIZHI_CHONG.get(iljin_zhi) == bz:
                    score -= 20
                    reasons.append(f"{iljin_zhi}와 {bz} 충 (재성 충격)")

        # 용신이 재성이고 일진이 용신을 생하면
        iljin_wx = TIANGAN_WUXING[iljin_gan]
        if bazi.yongsin and SHENG.get(iljin_wx) == bazi.yongsin:
            dm_wx = TIANGAN_WUXING[bazi.day_gan]
            yongsin_is_cai = (bazi.yongsin == KE[dm_wx])
            if yongsin_is_cai:
                score += 15
                reasons.append("일진이 용신(재성)을 생함")

        score = max(0, min(100, score))
        reason = "; ".join(reasons) if reasons else "특별한 재물 신호 없음"
        return score, reason

    def _calc_decision(self, bazi, iljin_gan, iljin_zhi, iljin_tg):
        """축 2: 결단운"""
        score = 50
        reasons = []

        # 일진이 일간을 보강하는 경우
        if iljin_tg in (TenGod.BIJIAN, TenGod.JIECAI, TenGod.PIANYIN, TenGod.ZHENGYIN):
            score += 20
            reasons.append(f"일진 {iljin_gan}이 {iljin_tg.value} — 일간 보강")

        # 일진이 편관(칠살)이고 신약이면 감점
        if iljin_tg == TenGod.PIANGUAN and bazi.day_master_strength == "신약":
            score -= 25
            reasons.append("칠살(七殺) + 신약 — 판단력 약화")
        elif iljin_tg == TenGod.PIANGUAN:
            score -= 10
            reasons.append("일진이 편관 — 약간의 압박감")

        # 일지와 일진 지지의 관계
        if DIZHI_LIUHE.get(iljin_zhi) == bazi.day_zhi:
            score += 15
            reasons.append(f"{iljin_zhi}와 일지 {bazi.day_zhi} 육합 (안정)")
        elif DIZHI_SANHE.get(iljin_zhi) and bazi.day_zhi in DIZHI_SANHE[iljin_zhi]:
            score += 12
            reasons.append(f"{iljin_zhi}와 일지 {bazi.day_zhi} 삼합 관계")

        if DIZHI_XING.get(iljin_zhi) == bazi.day_zhi:
            score -= 15
            reasons.append(f"{iljin_zhi}와 일지 {bazi.day_zhi} 형(刑) — 혼란")
        if DIZHI_HAI.get(iljin_zhi) == bazi.day_zhi:
            score -= 12
            reasons.append(f"{iljin_zhi}와 일지 {bazi.day_zhi} 해(害)")

        score = max(0, min(100, score))
        reason = "; ".join(reasons) if reasons else "평범한 결단력의 날"
        return score, reason

    def _calc_volatility(self, bazi, iljin_zhi):
        """축 3: 충돌운 (변동성)"""
        score = 50
        reasons = []

        bazi_branches = [bazi.year_zhi, bazi.month_zhi, bazi.day_zhi]
        if bazi.hour_zhi:
            bazi_branches.append(bazi.hour_zhi)

        chong_count = 0
        xing_count = 0

        for bz in bazi_branches:
            if DIZHI_CHONG.get(iljin_zhi) == bz:
                chong_count += 1
            if DIZHI_XING.get(iljin_zhi) == bz:
                xing_count += 1

        if chong_count > 0:
            score += chong_count * 15
            reasons.append(f"명식과 충(沖) {chong_count}건")
        if xing_count > 0:
            score += xing_count * 10
            reasons.append(f"명식과 형(刑) {xing_count}건")

        # 간략화: 충돌운은 지지 위주로 계산
        if chong_count == 0 and xing_count == 0:
            reasons.append("충·형이 없는 평온한 날")

        score = max(0, min(100, score))
        reason = "; ".join(reasons) if reasons else "보통 수준의 변동성"
        return score, reason

    def _calc_flow(self, bazi, iljin_gan, iljin_zhi):
        """축 4: 합운 (흐름·추세 동조)"""
        score = 50
        reasons = []

        # 천간합
        if TIANGAN_HE.get(iljin_gan) == bazi.day_gan:
            score += 25
            reasons.append(f"{iljin_gan}과 일간 {bazi.day_gan} 천간합(天干合)")

        # 일지와 육합
        if DIZHI_LIUHE.get(iljin_zhi) == bazi.day_zhi:
            score += 15
            reasons.append(f"{iljin_zhi}와 일지 {bazi.day_zhi} 육합")

        # 삼합 구성
        bazi_branches = {bazi.year_zhi, bazi.month_zhi, bazi.day_zhi}
        if bazi.hour_zhi:
            bazi_branches.add(bazi.hour_zhi)

        if iljin_zhi in DIZHI_SANHE:
            sanhe_set = set(DIZHI_SANHE[iljin_zhi])
            overlap = bazi_branches & sanhe_set
            if len(overlap) >= 2:
                score += 20
                reasons.append(f"{iljin_zhi} 삼합 2자 이상 구성")
            elif len(overlap) == 1:
                score += 8
                reasons.append(f"{iljin_zhi} 삼합 반합 구성")

        # 용신과 일진 오행 일치
        iljin_wx = TIANGAN_WUXING[iljin_gan]
        if bazi.yongsin and iljin_wx == bazi.yongsin:
            score += 15
            reasons.append(f"일진 오행 {iljin_wx.value}이 용신과 일치")

        score = max(0, min(100, score))
        reason = "; ".join(reasons) if reasons else "특별한 합 신호 없음"
        return score, reason

    def _determine_grade(self, composite: int, decision: int) -> str:
        """신호등급 결정 (결단운 게이트 포함)"""
        if composite >= 85 and decision >= 60:
            grade = "🔥 강한 진입"
        elif composite >= 70:
            grade = "👍 진입각"
        elif composite >= 50:
            grade = "😐 관망"
        elif composite >= 30:
            grade = "🛑 보류"
        else:
            grade = "❄️ 회피"

        # 결단운 게이트: 40 미만이면 한 등급 하향
        if decision < 40:
            downgrade = {
                "🔥 강한 진입": "👍 진입각",
                "👍 진입각": "😐 관망",
                "😐 관망": "🛑 보류",
                "🛑 보류": "❄️ 회피",
                "❄️ 회피": "❄️ 회피",
            }
            grade = downgrade[grade]
        return grade

    def _calc_best_hours(self, bazi, iljin_gan, iljin_zhi, target_date) -> list:
        """12시진 각각의 보정 점수를 계산해 상위 2~3개 추천"""
        results = []
        dm = bazi.day_gan
        dm_wx = TIANGAN_WUXING[dm]

        for zhi in DIZHI:
            multiplier = 1.0
            zhi_wx = DIZHI_WUXING[zhi]

            # 시진 지지가 일간을 생하면
            if SHENG.get(zhi_wx) == dm_wx:
                multiplier *= 1.15

            # 시진 지지가 재성이면
            zhi_god = calc_ten_god_for_branch(dm, zhi)
            if zhi_god in (TenGod.PIANCAI, TenGod.ZHENGCAI):
                multiplier *= 1.20

            # 시진 지지가 일지와 합이면
            if DIZHI_LIUHE.get(zhi) == bazi.day_zhi:
                multiplier *= 1.10

            # 시진 지지가 일지와 충이면
            if DIZHI_CHONG.get(zhi) == bazi.day_zhi:
                multiplier *= 0.80

            results.append((zhi, multiplier))

        # 상위 3개
        results.sort(key=lambda x: x[1], reverse=True)
        best = []
        for zhi, mult in results[:3]:
            if mult >= 1.0:
                time_range = SHICHEN_TIME_RANGES[zhi]
                best.append((zhi, time_range, round(mult, 2)))
        return best


# ─────────────────────────────────────────────
# 5. CLI 데모
# ─────────────────────────────────────────────

def demo():
    engine = SajuEngine()

    print("=" * 50)
    print("사주캔들 엔진 프로토타입 v0.1")
    print("=" * 50)

    # 예시 사용자: 1990년 3월 15일 14시 (양력)
    bazi = engine.calc_bazi(1990, 3, 15, hour=14)
    print("\n[ 명식 계산 결과 ]")
    print(bazi.summary())
    print(f"십성: {bazi.ten_gods}")
    print()

    # 오늘 점수 (스윙 트레이딩)
    today = date.today()
    score_swing = engine.calc_daily_score(bazi, today, asset_class="swing")
    print("[ 오늘의 일일 점수 — 스윙 ]")
    print(score_swing.summary())

    # 단타 모드
    score_scalp = engine.calc_daily_score(bazi, today, asset_class="scalp")
    print("[ 오늘의 일일 점수 — 단타 ]")
    print(score_scalp.summary())

    # 장기 모드
    score_long = engine.calc_daily_score(bazi, today, asset_class="long")
    print("[ 오늘의 일일 점수 — 장기 ]")
    print(score_long.summary())

    # 향후 7일 길일 캘린더
    print("[ 향후 7일 길일 캘린더 — 스윙 ]")
    from datetime import timedelta
    for i in range(7):
        d = today + timedelta(days=i)
        sc = engine.calc_daily_score(bazi, d, asset_class="swing")
        bar = "█" * (sc.composite_score // 5)
        print(f"  {d} ({sc.iljin}) | {sc.composite_score:>3} {bar} {sc.signal_grade}")


if __name__ == "__main__":
    demo()
