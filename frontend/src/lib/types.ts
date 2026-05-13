export interface SajuPillars {
  year_stem: string;
  year_branch: string;
  month_stem: string;
  month_branch: string;
  day_stem: string;
  day_branch: string;
  hour_stem: string | null;
  hour_branch: string | null;
}

export interface ProfileResponse {
  pillars: SajuPillars;
  day_master: string;
  day_master_element: string;
  day_master_description: string;
  investor_type: string;
  element_distribution: Record<string, number>;
  strengths: string[];
  weaknesses: string[];
  risk_score: number;
}

export interface DailyScores {
  judgment: number;
  action: number;
  patience: number;
}

export interface DailyFortuneResponse {
  date: string;
  scores: DailyScores;
  coaching: string;
  caution: string;
  detail: string;
  shinsal_messages: string[];
  relation_messages: string[];
  iljin_stem: string;
  iljin_branch: string;
  iljin_element: string;
}

export interface YearlyFortuneResponse {
  year: number;
  sewoon_stem: string;
  sewoon_branch: string;
  sewoon_element: string;
  yearly_outlook: string;
  monthly_tips: string[];
  daeun_stem: string;
  daeun_branch: string;
  daeun_element: string;
  daeun_start_age: number;
  daeun_description: string;
}

export interface UserData {
  year: number;
  month: number;
  day: number;
  hour?: number;
  gender: "M" | "F";
  profile?: ProfileResponse;
}

export interface ReportSection {
  id: number;
  title: string;
  content: string;
  highlight: string;
  locked: boolean;
}

export interface ReportResponse {
  report_id: string;
  target_year: number;
  tier: string;
  sections: ReportSection[];
}
