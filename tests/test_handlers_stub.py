# -*- coding: utf-8 -*-
"""تست لایه‌ی handlers با «تلگرام جعلی» (نه تلگرام واقعی!) برای پیدا کردن خطاهای ظاهری."""
import asyncio, sys, types, unittest
from helpers import World, OWNER, GROUP

# --- ماژول‌های جعلی telegram (فقط برای تست، اگر نصب نیست)
tg = types.ModuleType("telegram")
class Update: ALL_TYPES = None
tg.Update = Update
class _B:
    def __init__(self, label, callback_data=None): self.label, self.data = label, callback_data
class _M:
    def __init__(self, rows): self.rows = rows
tg.InlineKeyboardButton, tg.InlineKeyboardMarkup = _B, _M
const = types.ModuleType("telegram.constants")
class ChatType: PRIVATE, GROUP, SUPERGROUP = "private", "group", "supergroup"
const.ChatType = ChatType
err = types.ModuleType("telegram.error")
class TelegramError(Exception): pass
class BadRequest(TelegramError): pass
class RetryAfter(TelegramError):
    retry_after = 1
err.TelegramError, err.BadRequest, err.RetryAfter = TelegramError, BadRequest, RetryAfter
ext = types.ModuleType("telegram.ext")
class ContextTypes: DEFAULT_TYPE = None
ext.ContextTypes = ContextTypes
for name, mod in (("telegram", tg), ("telegram.constants", const), ("telegram.error", err), ("telegram.ext", ext)):
    sys.modules.setdefault(name, mod)
import handlers  # noqa


class FakeBot:
    def __init__(self): self.sent, self.edits, self.pins, self.next = [], [], [], 500
    async def send_message(self, chat_id, text, **kw):
        self.next += 1; self.sent.append((chat_id, text, self.next)); return types.SimpleNamespace(message_id=self.next)
    async def edit_message_text(self, chat_id, message_id, text, **kw):
        self.edits.append((chat_id, message_id, text))
    async def pin_chat_message(self, chat_id, message_id, **kw): self.pins.append(message_id)


class T(unittest.TestCase):
    def test_banner_created_pinned_then_edited(self):
        w = World(); w.start()
        r = handlers.Runner(w.ctrl, w.db, OWNER); bot = FakeBot()
        asyncio.run(r.update_banner(bot))
        self.assertEqual(len(bot.sent), 1); self.assertEqual(len(bot.pins), 1)
        asyncio.run(r.update_banner(bot))
        self.assertEqual(len(bot.sent), 1); self.assertEqual(len(bot.edits), 1)       # همان پیام ویرایش شد
        self.assertEqual(w.db.get("banner_msg_id"), bot.sent[0][2])

    def test_dispatch_full_round(self):
        w = World(); w.start()
        r = handlers.Runner(w.ctrl, w.db, OWNER); bot = FakeBot()
        async def go():
            await r.dispatch(bot, w.group("نوید", "گربه"), GROUP)
            for _ in range(20):
                await r.dispatch(bot, w.tick(1), OWNER)
        asyncio.run(go())
        self.assertTrue(any("برنده" in s[1] for s in bot.sent))
        self.assertTrue(bot.edits)                                                      # شمارش با ویرایش یک پیام

    def test_missing_banner_asks_owner(self):
        w = World(); w.start(); w.db.set("banner_msg_id", 999)
        r = handlers.Runner(w.ctrl, w.db, OWNER); bot = FakeBot()
        async def bad_edit(chat_id, message_id, text, **kw): raise BadRequest("Message to edit not found")
        bot.edit_message_text = bad_edit
        asyncio.run(r.update_banner(bot))
        self.assertIsNone(w.db.get("banner_msg_id")); self.assertEqual(bot.sent[-1][0], OWNER)


if __name__ == "__main__":
    unittest.main()
