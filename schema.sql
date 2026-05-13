-- schema.sql
-- SQLite schema for the Discord economy bot.
-- Run automatically on startup via db.py.

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,   -- Discord user snowflake
    wallet      INTEGER NOT NULL DEFAULT 0,
    bank        INTEGER NOT NULL DEFAULT 0,
    last_daily  TEXT,                  -- ISO-8601 datetime string, nullable
    xp          INTEGER NOT NULL DEFAULT 0,
    level       INTEGER NOT NULL DEFAULT 1
);

-- Optional audit/transaction log (handy for debugging)
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      INTEGER NOT NULL,      -- positive = credit, negative = debit
    reason      TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
