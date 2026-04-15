-- Week 3 초기 스키마.
-- 실행: Supabase Studio → SQL Editor → Run.
-- 로컬: psql $DATABASE_URL -f migrations/001_init.sql

CREATE TABLE IF NOT EXISTS users (
    telegram_chat_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_bazi (
    telegram_chat_id BIGINT PRIMARY KEY
        REFERENCES users(telegram_chat_id) ON DELETE CASCADE,
    birth_year  INT NOT NULL CHECK (birth_year BETWEEN 1900 AND 2100),
    birth_month INT NOT NULL CHECK (birth_month BETWEEN 1 AND 12),
    birth_day   INT NOT NULL CHECK (birth_day BETWEEN 1 AND 31),
    birth_hour  INT NOT NULL CHECK (birth_hour BETWEEN 0 AND 23),
    birth_minute INT NOT NULL DEFAULT 0 CHECK (birth_minute BETWEEN 0 AND 59),
    asset_class_pref TEXT NOT NULL DEFAULT 'swing'
        CHECK (asset_class_pref IN ('swing', 'scalp', 'long', 'default')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_touch ON users;
CREATE TRIGGER users_touch BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS user_bazi_touch ON user_bazi;
CREATE TRIGGER user_bazi_touch BEFORE UPDATE ON user_bazi
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
