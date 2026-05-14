export interface OhlcvBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SajuFilter {
  passed: boolean | null;    // null = 판정 불가
  threshold: number;
}

export interface SignalMarker {
  date: string;
  signal: string;
}

export interface ChartOhlcvResponse {
  symbol: string;
  name: string;
  asset_class: string;
  current_price: number;
  price_change_pct: number;
  saju_filter: SajuFilter;
  current_signal: string | null;   // null = 미지원 종목
  ohlcv: OhlcvBar[];
  signal_markers: SignalMarker[];
}

export interface QuantScoreDetail {
  total: number;
  breakdown: Record<string, number>;
}

export interface TaDetail {
  supertrend: { direction: string; value: number };
  rsi: number;
  macd: { histogram: number; status: string };
  ma_alignment: boolean;
  volume_trend: number;
}

export interface SignalHistoryItem {
  month: string;
  signal: string;
  quant_score: number;
}

export interface ChartAnalysisResponse {
  symbol: string;
  quant_scores: {
    ta_score: QuantScoreDetail;
    macro_score: QuantScoreDetail;
    fa_score?: QuantScoreDetail;
    onchain_score?: QuantScoreDetail;
  };
  signal_history: SignalHistoryItem[];
  ta_detail: TaDetail;
  rank: { position: number; total_passed: number };
}
