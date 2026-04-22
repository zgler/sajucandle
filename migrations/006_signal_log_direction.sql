-- Phase 2: signal_log에 signal_direction 컬럼 추가 (숏 대칭 관찰용).
-- 실행: Supabase Studio → SQL Editor → Run.
-- 로컬: psql $DATABASE_URL -f migrations/006_signal_log_direction.sql
-- 로컬 테스트 DB: psql $TEST_DATABASE_URL -f migrations/006_signal_log_direction.sql
--
-- 레거시 row(Phase 0~1)는 signal_direction=NULL 유지.
-- 신규 row(Phase 2+)는 LONG/SHORT/NEUTRAL 중 하나.

ALTER TABLE signal_log
    ADD COLUMN IF NOT EXISTS signal_direction TEXT
        CHECK (signal_direction IN ('LONG', 'SHORT', 'NEUTRAL'));

CREATE INDEX IF NOT EXISTS idx_signal_log_direction
    ON signal_log(signal_direction, sent_at DESC)
    WHERE signal_direction IS NOT NULL;
