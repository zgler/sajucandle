import type { ProfileResponse, DailyFortuneResponse, YearlyFortuneResponse, ReportResponse, PaymentConfirmResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

/* ── 공통 fetch 래퍼 ─────────────────────────────── */

async function api<T>(
  url: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const { timeoutMs, ...fetchInit } = init ?? {};

  let controller: AbortController | undefined;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  if (timeoutMs) {
    controller = new AbortController();
    timeout = setTimeout(() => controller!.abort(), timeoutMs);
    fetchInit.signal = controller.signal;
  }

  try {
    const res = await fetch(url, fetchInit);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`API error: ${res.status} ${text}`);
    }
    return res.json();
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

function postJson(body: unknown, timeoutMs?: number) {
  return {
    method: "POST" as const,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs,
  };
}

/* ── API 함수 ─────────────────────────────────────── */

export function fetchProfile(params: {
  year: number;
  month: number;
  day: number;
  hour?: number;
  minute?: number;
  gender: "M" | "F";
}): Promise<ProfileResponse> {
  return api(`${API_BASE}/api/saju/profile`, postJson(params));
}

export function fetchDailyFortune(params: {
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

  return api(`${API_BASE}/api/saju/daily?${query.toString()}`);
}

export function fetchYearlyFortune(params: {
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

  return api(`${API_BASE}/api/saju/yearly?${query.toString()}`);
}

export function fetchReport(params: {
  year: number;
  month: number;
  day: number;
  hour?: number;
  gender: "M" | "F";
  tier?: "standard" | "premium";
}): Promise<ReportResponse> {
  return api(`${API_BASE}/api/saju/report`, postJson(params, 300000));
}

export function confirmPayment(params: {
  payment_key: string;
  order_id: string;
  amount: number;
  year: number;
  month: number;
  day: number;
  hour?: number;
  gender: "M" | "F";
  tier: "standard" | "premium";
}): Promise<PaymentConfirmResponse> {
  return api(`${API_BASE}/api/payments/confirm`, postJson(params, 300000));
}
