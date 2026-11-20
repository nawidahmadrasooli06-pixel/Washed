# -*- coding: utf-8 -*-
"""دیتابیس SQLite دائمی با مهاجرت نسخه‌ای."""
import json
import os
import sqlite3

SCHEMA_V1 = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE topics(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, norm TEXT UNIQUE, builtin INTEGER DEFAULT 0);
CREATE TABLE answers(id INTEGER PRIMARY KEY AUTOINCREMENT, topic_id INTEGER, canonical TEXT, UNIQUE(topic_id, canonical));
CREATE TABLE forms(id INTEGER PRIMARY KEY AUTOINCREMENT, answer_id INTEGER, topic_id INTEGER, text TEXT, norm TEXT, UNIQUE(topic_id, norm));
CREATE INDEX idx_forms_lookup ON forms(topic_id, norm);
CREATE TABLE players(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, norm TEXT, hearts INTEGER, initial_hearts INTEGER,
  active INTEGER DEFAULT 1, removed INTEGER DEFAULT 0, tg_user_id INTEGER, elim_order INTEGER, added_at REAL);
CREATE TABLE history(id INTEGER PRIMARY KEY AUTOINCREMENT, round_no INTEGER, answer_id INTEGER, raw TEXT, player_id INTEGER,
  status TEXT, chat_id INTEGER, message_id INTEGER, ts REAL);
CREATE TABLE pending(id INTEGER PRIMARY KEY AUTOINCREMENT, topic_id INTEGER, raw TEXT, norm TEXT, player_id INTEGER,
  chat_id INTEGER, message_id INTEGER, ts REAL, status TEXT DEFAULT 'open');
CREATE TABLE rounds(id INTEGER PRIMARY KEY AUTOINCREMENT, round_no INTEGER, winner_id INTEGER, victim_id INTEGER, ts REAL);
CREATE TABLE heart_log(id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER, delta INTEGER, hearts_after INTEGER, reason TEXT, ts REAL);
CREATE TABLE prizes(rank INTEGER PRIMARY KEY, name TEXT);
"""
LATEST = 1


class Database:
    def __init__(self, path=":memory:"):
        if path != ":memory:":
            d = os.path.dirname(os.path.abspath(path))
            os.makedirs(d, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.migrate()

    def migrate(self):
        v = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if v < 1:
            self.conn.executescript(SCHEMA_V1)
            self.conn.execute("PRAGMA user_version=1")
            self.conn.commit()

    # --- کمکی‌های SQL
    def q(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def one(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    def ex(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    # --- تنظیمات (JSON)
    def get(self, key, default=None):
        r = self.one("SELECT value FROM meta WHERE key=?", (key,))
        if r is None:
            return default
        try:
            return json.loads(r["value"])
        except Exception:
            return default

    def set(self, key, value):
        self.ex("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)))

    def delete(self, key):
        self.ex("DELETE FROM meta WHERE key=?", (key,))

    def backup(self, dest):
        """پشتیبان‌گیری از دیتابیس در فایل دیگر."""
        out = sqlite3.connect(dest)
        with out:
            self.conn.backup(out)
        out.close()
