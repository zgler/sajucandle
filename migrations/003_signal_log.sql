-- Week 8 Phase 1: signal_log 테이블 (시그널 발송 기록 + MFE/MAE 추적).
-- 실행: Supabase Studio → SQL Editor → Run.
-- 로컬: psql $DATABASE_URL -f migrations/003_signal_log.sql
-- 로컬 테스트 DB: psql $TEST_DATABASE_URL -f migrations/003_signal_log.sql

CREATE TABLE IF NOT EXISTS signal_log (
    id              BIGSERIAL PRIMARY KEY,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          TEXT NOT NULL,
    telegram_chat_id BIGINT,

    ticker          TEXT NOT NULL,
    target_date     DATE NOT NULL,
    entry_price     NUMERIC(18,8) NOT NULL,

    saju_score      INT NOT NULL,
    analysis_score  INT NOT NULL,
    structure_state TEXT NOT NULL,
    alignment_bias  TEXT NOT NULL,
    rsi_1h          NUMERIC(5,2),
    volume_ratio_1d NUMERIC(6,3),

    composite_score INT NOT NULL,
    signal_grade    TEXT NOT NULL,

    mfe_7d_pct      NUMERIC(6,3),
    mae_7d_pct      NUMERIC(6,3),
    close_24h       NUMERIC(18,8),
    close_7d        NUMERIC(18,8),
    last_tracked_at TIMESTAMPTZ,
    tracking_done   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_signal_log_ticker_sent_at
    ON signal_log(ticker, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_log_tracking
    ON signal_log(tracking_done, sent_at)
    WHERE tracking_done = FALSE;
