import type { ProfileResponse, DailyFortuneResponse, YearlyFortuneResponse, ReportResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export async function fetchProfile(params: {
  year: number;
  month: number;
  day: number;
  hour?: number;
  minute?: number;
  gender: "M" | "F";
}): Promise<ProfileResponse> {
  const res = await fetch(`${API_BASE}/api/saju/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`fetchProfile failed: ${res.status} ${text}`);
  }
  return res.json();
}

export async function fetchDailyFortune(params: {
  year: number;
  month: number;
  day: number;
  hour?: number;
  gender: "M" | "F";
  date?: string;
}): Promise<DailyFortuneResponse> {
  const query = new URLSearchParams();
  query.set("year", String(params.year));
  query.set("month", String(params.month));
  query.set("day", String(params.day));
  if (params.hour !== undefined) query.set("hour", String(params.hour));
  query.set("gender", params.gender);
  if (params.date) query.set("date", params.date);

  const res = await fetch(`${API_BASE}/api/saju/daily?${query.toString()}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`fetchDailyFortune failed: ${res.status} ${text}`);
  }
  return res.json();
}

export async function fetchYearlyFortune(params: {
  year: number;
  month: number;
  day: number;
  hour?: number;
  gender: "M" | "F";
}): Promise<YearlyFortuneResponse> {
  const query = new URLSearchParams();
  query.set("year", String(params.year));
  query.set("month", String(params.month));
  query.set("day", String(params.day));
  if (params.hour !== undefined) query.set("hour", String(params.hour));
  query.set("gender", params.gender);

  const res = await fetch(`${API_BASE}/api/saju/yearly?${query.toString()}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`fetchYearlyFortune failed: ${res.status} ${text}`);
  }
  return res.json();
}

export async function fetchReport(params: {
  year: number;
  month: number;
  day: number;
  hour?: number;
  gender: "M" | "F";
}): Promise<ReportResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 300000);

  try {
    const res = await fetch(`${API_BASE}/api/saju/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
      signal: controller.signal,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`fetchReport failed: ${res.status} ${text}`);
    }
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}
