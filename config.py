# -*- coding: utf-8 -*-
"""تنظیمات از Environment Variables (هیچ رازی داخل کد نیست)."""
import os


def _int(name, default=None):
    v = os.environ.get(name, "").strip()
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        raise SystemExit(f"متغیر {name} باید عدد باشد.")


BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OWNER_ID = _int("OWNER_ID", 8659480577)
GROUP_CHAT_ID = _int("GROUP_CHAT_ID")
DB_PATH = os.environ.get("DB_PATH", "bot_data/last_word.db")
PORT = _int("PORT", 10000)
