import type { UserData, ReportResponse } from "./types";

export const REPORT_CACHE_PREFIX = "saju_report_";

export function buildReportId(user: UserData): string {
  const h = user.hour !== undefined ? String(user.hour).padStart(2, "0") : "00";
  const y = new Date().getFullYear();
  return `rpt_${user.year}${String(user.month).padStart(2, "0")}${String(user.day).padStart(2, "0")}${h}${user.gender}_${y}`;
}

export function loadCachedReport(reportId: string): ReportResponse | null {
  try {
    const raw = localStorage.getItem(REPORT_CACHE_PREFIX + reportId);
    if (!raw) return null;
    return JSON.parse(raw) as ReportResponse;
  } catch {
    return null;
  }
}

export function saveCachedReport(report: ReportResponse): void {
  try {
    localStorage.setItem(REPORT_CACHE_PREFIX + report.report_id, JSON.stringify(report));
  } catch {
    // storage full or unavailable
  }
}
