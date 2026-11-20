# -*- coding: utf-8 -*-
"""نقطه‌ی شروع ربات «آخرین واژه»."""
import asyncio
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import config
from controller import Controller
from database import Database
from game_engine import Engine
from topics import Bank

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("lastword")


def build_core(db_path=None):
    db = Database(db_path or config.DB_PATH)
    bank = Bank(db)
    bank.seed()
    engine = Engine(db, bank)
    ctrl = Controller(db, engine, bank, config.OWNER_ID, config.GROUP_CHAT_ID)
    return db, bank, engine, ctrl


def start_health_server(port):
    """سرور کوچک برای Render (Web Service به یک پورت باز نیاز دارد)."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

        def log_message(self, *a):
            pass
    srv = HTTPServer(("0.0.0.0", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def main():
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN تنظیم نشده است (در Render → Environment).")
    from telegram import Update
    from telegram.ext import Application, CallbackQueryHandler, ChatMemberHandler, MessageHandler, filters
    from handlers import Runner

    db, bank, engine, ctrl = build_core()
    runner = Runner(ctrl, db, config.OWNER_ID)
    start_health_server(config.PORT)

    async def post_init(app):
        app.bot_data["ticker"] = asyncio.create_task(runner.ticker(app.bot))
        log.info("ربات بالا آمد؛ وضعیت بازی از دیتابیس بازیابی شد: %s", engine.status)

    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CallbackQueryHandler(runner.on_callback))
    app.add_handler(ChatMemberHandler(runner.on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT, runner.on_message))
    app.add_error_handler(runner.on_error)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
