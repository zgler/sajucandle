-- Week 7: user_watchlist 테이블.
-- 실행: Supabase Studio → SQL Editor → Run.
-- 로컬: psql $DATABASE_URL -f migrations/002_watchlist.sql
-- 로컬 테스트 DB: psql $TEST_DATABASE_URL -f migrations/002_watchlist.sql

CREATE TABLE IF NOT EXISTS user_watchlist (
    telegram_chat_id BIGINT NOT NULL
        REFERENCES user_bazi(telegram_chat_id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (telegram_chat_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_user_watchlist_chat_id
    ON user_watchlist(telegram_chat_id);
