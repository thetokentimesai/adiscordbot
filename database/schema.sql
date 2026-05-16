-- schema.sql
-- PostgreSQL schema for the Discord economy bot.
-- Run automatically on startup via db.py.

CREATE TABLE IF NOT EXISTS users (
    user_id        BIGINT PRIMARY KEY,        -- Discord user snowflake
    wallet         BIGINT NOT NULL DEFAULT 0 CHECK (wallet >= 0),  -- no debt allowed
    bank           BIGINT NOT NULL DEFAULT 0 CHECK (bank >= 0),
    last_daily     TEXT,                      -- ISO-8601 datetime string, nullable
    last_hourly    TEXT,
    last_work      TEXT,
    last_sidequest TEXT,
    last_weekly    TEXT,                      -- verified members only
    last_monthly   TEXT,                      -- verified members only
    xp             BIGINT NOT NULL DEFAULT 0,
    level          INTEGER NOT NULL DEFAULT 1
);

-- Audit/transaction log
CREATE TABLE IF NOT EXISTS transactions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    amount      BIGINT NOT NULL,           -- positive = credit, negative = debit
    reason      TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Migration: add new columns if upgrading from older schema
-- (db.py handles this automatically on startup via ALTER TABLE ... ADD COLUMN IF NOT EXISTS)