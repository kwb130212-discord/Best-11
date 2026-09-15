# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
import os
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "team.db")
SETTINGS_COLUMNS = {
    "management_role_id": "INTEGER", "auth_role_id": "INTEGER", "grant_role_id": "INTEGER",
    "ticket_role_id": "INTEGER", "unverified_role_id": "INTEGER", "verified_role_id": "INTEGER",
    "ticket_category_id": "INTEGER", "log_channel_id": "INTEGER", "verification_image_url": "TEXT",
    "verification_code": "TEXT", "updated_at": "TEXT",
}


def connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS guild_settings (guild_id INTEGER PRIMARY KEY, welcome_channel_id INTEGER, log_channel_id INTEGER)")
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(guild_settings)")}
        for name, sql_type in SETTINGS_COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE guild_settings ADD COLUMN {name} {sql_type}")
        conn.execute("""CREATE TABLE IF NOT EXISTS captcha_state (
            guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, code TEXT NOT NULL, expires_at REAL NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS ticket_state (
            channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, owner_id INTEGER NOT NULL, opened_at TEXT NOT NULL
        )""")
        conn.commit()


def get_settings(guild_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)).fetchone()


def update_settings(guild_id: int, **values: Any) -> None:
    values = {k: v for k, v in values.items() if k in SETTINGS_COLUMNS}
    if not values:
        return
    values["updated_at"] = datetime.now(timezone.utc).isoformat()
    fields = ", ".join(f"{k}=?" for k in values)
    with connect() as conn:
        conn.execute("INSERT INTO guild_settings(guild_id) VALUES(?) ON CONFLICT(guild_id) DO NOTHING", (guild_id,))
        conn.execute(f"UPDATE guild_settings SET {fields} WHERE guild_id=?", (*values.values(), guild_id))
        conn.commit()
