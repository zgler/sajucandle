-- Phase 1: signal_log에 run_id 컬럼 추가 (백테스트 run 구분용).
-- 실행: Supabase Studio → SQL Editor → Run.
-- 로컬: psql $DATABASE_URL -f migrations/005_signal_log_run_id.sql
-- 로컬 테스트 DB: psql $TEST_DATABASE_URL -f migrations/005_signal_log_run_id.sql

ALTER TABLE signal_log
    ADD COLUMN IF NOT EXISTS run_id TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_log_run_id
    ON signal_log(run_id, ticker, target_date)
    WHERE run_id IS NOT NULL;
