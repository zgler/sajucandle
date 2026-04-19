-- Week 9: signal_log에 TradeSetup 컬럼 추가.
-- 실행: Supabase Studio → SQL Editor → Run.
-- 로컬: psql $DATABASE_URL -f migrations/004_signal_log_tradesetup.sql
-- 로컬 테스트 DB: psql $TEST_DATABASE_URL -f migrations/004_signal_log_tradesetup.sql

ALTER TABLE signal_log
    ADD COLUMN IF NOT EXISTS stop_loss  NUMERIC(18,8),
    ADD COLUMN IF NOT EXISTS take_profit_1 NUMERIC(18,8),
    ADD COLUMN IF NOT EXISTS take_profit_2 NUMERIC(18,8),
    ADD COLUMN IF NOT EXISTS risk_pct   NUMERIC(6,3),
    ADD COLUMN IF NOT EXISTS rr_tp1     NUMERIC(6,3),
    ADD COLUMN IF NOT EXISTS rr_tp2     NUMERIC(6,3),
    ADD COLUMN IF NOT EXISTS sl_basis   TEXT,
    ADD COLUMN IF NOT EXISTS tp1_basis  TEXT,
    ADD COLUMN IF NOT EXISTS tp2_basis  TEXT;
