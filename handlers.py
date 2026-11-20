# -*- coding: utf-8 -*-
"""لایه‌ی تلگرام: دریافت پیام/دکمه، ارسال خروجی‌های کنترلر، بنر پین‌شده و حلقه‌ی تایمر."""
import asyncio
import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.error import BadRequest, RetryAfter, TelegramError
from telegram.ext import ContextTypes

import banner as banner_mod
from controller import Msg
from keyboards import to_markup

log = logging.getLogger("lastword")


class Runner:
    def __init__(self, ctrl, db, owner_id):
        self.ctrl, self.db, self.owner_id = ctrl, db, int(owner_id)
        self.lock = asyncio.Lock()

    # ---------- ارسال خروجی‌ها
    def _chat(self, target, origin):
        if target == "here":
            return origin
        if target == "group":
            return self.ctrl.group_id
        return self.owner_id

    async def dispatch(self, bot, outs, origin_chat, cb_message_id=None, query=None):
        toast = None
        for o in outs:
            try:
                if o.kind == "toast":
                    toast = o.text
                elif o.kind == "banner":
                    await self.update_banner(bot, force_new=o.final)
                elif o.kind == "countdown":
                    await self.countdown(bot, o)
                elif o.kind == "edit":
                    if cb_message_id is None:
                        continue
                    try:
                        await bot.edit_message_text(chat_id=origin_chat, message_id=cb_message_id, text=o.text,
                                                    reply_markup=to_markup(o.kb))
                    except BadRequest as e:
                        if "not modified" not in str(e).lower():
                            raise
                elif o.kind == "send":
                    chat = self._chat(o.chat, origin_chat)
                    if chat is None:
                        continue
                    await bot.send_message(chat_id=chat, text=o.text, reply_markup=to_markup(o.kb),
                                           reply_to_message_id=o.reply_to if (o.reply_to and chat == origin_chat) else None,
                                           allow_sending_without_reply=True)
            except RetryAfter as e:
                log.warning("flood wait %s", e.retry_after)
            except TelegramError as e:
                log.error("send error: %s", e)
        if query is not None:
            try:
                await query.answer(toast)
            except TelegramError:
                pass

    async def countdown(self, bot, o):
        gid = self.ctrl.group_id
        if gid is None:
            return
        mid = self.db.get("countdown_msg_id")
        if mid:
            try:
                await bot.edit_message_text(chat_id=gid, message_id=mid, text=o.text)
                if o.final:
                    self.db.delete("countdown_msg_id")
                return
            except BadRequest as e:
                if "not modified" in str(e).lower():
                    return
                self.db.delete("countdown_msg_id")      # پیام حذف شده؛ پیام تازه می‌سازیم
        m = await bot.send_message(chat_id=gid, text=o.text)
        if not o.final:
            self.db.set("countdown_msg_id", m.message_id)

    async def update_banner(self, bot, force_new=False):
        gid = self.ctrl.group_id
        if gid is None:
            return
        text = banner_mod.render(self.db, self.ctrl.eng)
        mid = None if force_new else self.db.get("banner_msg_id")
        if mid:
            try:
                await bot.edit_message_text(chat_id=gid, message_id=mid, text=text)
                return
            except BadRequest as e:
                msg = str(e).lower()
                if "not modified" in msg:
                    return
                if "not found" in msg or "can't be edited" in msg or "message to edit" in msg:
                    self.db.delete("banner_msg_id")
                    await bot.send_message(chat_id=self.owner_id,
                                           text="⚠️ پیام بنر در گروه پیدا نشد (شاید حذف شده). بنر تازه بسازم و پین کنم؟",
                                           reply_markup=to_markup([[("✅ بله، بنر جدید", "bn:recreate")]]))
                    return
                raise
        m = await bot.send_message(chat_id=gid, text=text)
        self.db.set("banner_msg_id", m.message_id)
        try:
            await bot.pin_chat_message(chat_id=gid, message_id=m.message_id, disable_notification=True)
        except TelegramError as e:
            await bot.send_message(chat_id=self.owner_id,
                                   text=f"⚠️ بنر ساخته شد ولی پین نشد ({e}). به ربات دسترسی «پین کردن پیام» بده.")

    # ---------- هندلرها
    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        m, u, c = update.effective_message, update.effective_user, update.effective_chat
        if not m or not m.text or not u or u.is_bot or not c:
            return
        if c.type == ChatType.PRIVATE:
            ctype = "private"
        elif c.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            ctype = "group"
        else:
            return
        rt = m.reply_to_message
        msg = Msg(user_id=u.id, chat_id=c.id, chat_type=ctype, text=m.text, message_id=m.message_id,
                  reply_to_id=rt.message_id if rt else None,
                  reply_to_user=rt.from_user.id if rt and rt.from_user else None,
                  name=u.first_name or "", full_name=u.full_name or "", username=u.username or "")
        async with self.lock:
            outs = self.ctrl.on_text(msg)
            await self.dispatch(context.bot, outs, c.id)

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        if not q or not q.message:
            return
        async with self.lock:
            outs = self.ctrl.on_callback(q.from_user.id, q.message.chat_id, q.message.message_id, q.data or "")
            await self.dispatch(context.bot, outs, q.message.chat_id, q.message.message_id, q)

    async def on_my_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cm = update.my_chat_member
        if not cm or cm.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return
        if cm.new_chat_member.status in ("member", "administrator"):
            await context.bot.send_message(
                chat_id=self.owner_id,
                text=f"🤖 به گروه «{cm.chat.title}» اضافه شدم.\n🆔 شناسه‌ی عددی گروه: {cm.chat.id}\n"
                     "برای ثبت این گروه، داخل گروه بنویس: ثبت گروه")

    async def ticker(self, bot):
        """حلقه‌ی تایمر: هر ۰٫۵ ثانیه وضعیت ذخیره‌شده در دیتابیس را بررسی می‌کند (بعد از ری‌استارت هم ادامه می‌دهد)."""
        while True:
            await asyncio.sleep(0.5)
            try:
                async with self.lock:
                    outs = self.ctrl.on_tick()
                    if outs:
                        await self.dispatch(bot, outs, self.owner_id)
            except Exception:
                log.exception("ticker error")

    async def on_error(self, update, context):
        log.error("handler error", exc_info=context.error)
