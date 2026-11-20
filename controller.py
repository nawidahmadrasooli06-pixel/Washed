# -*- coding: utf-8 -*-
"""کنترلر: تبدیل پیام‌ها/دکمه‌ها به عملیات بازی و پیام‌های خروجی. مستقل از تلگرام (قابل تست)."""
import json
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

import banner as bn
import commands
from answers import normalize, clean_display, looks_like_answer
from texts import PANEL, HELP, HELP_ORDER, fa


@dataclass
class Msg:
    user_id: int
    chat_id: int
    chat_type: str            # 'private' | 'group'
    text: str
    message_id: int = 0
    reply_to_id: Optional[int] = None
    reply_to_user: Optional[int] = None
    name: str = ""
    full_name: str = ""
    username: str = ""


@dataclass
class Out:
    kind: str = "send"        # send | edit | banner | countdown | toast
    text: str = ""
    chat: str = "here"        # here | group | owner
    kb: Optional[list] = None  # [[(label, callback_data), ...], ...]
    reply_to: Optional[int] = None
    final: bool = False       # countdown: پیام پایانی (شناسه‌ی پیام شمارش بعد از این فراموش می‌شود)


def kb_rows(buttons, per_row=2):
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


BACK = [("🔙 بازگشت به پنل", "menu:main")]


class Controller:
    def __init__(self, db, engine, bank, owner_id, group_chat_id=None):
        self.db, self.eng, self.bank = db, engine, bank
        self.owner_id = int(owner_id)
        self._env_group = int(group_chat_id) if group_chat_id else None

    # ------------------------------------------------------------ کمکی‌ها
    @property
    def group_id(self):
        return self._env_group or self.db.get("group_chat_id")

    def is_owner(self, uid):
        return int(uid) == self.owner_id

    def _say(self, msg, text, kb=None, also_group=False):
        outs = [Out("send", text, "here", kb, reply_to=msg.message_id if msg.chat_type != "private" else None)]
        if also_group and msg.chat_type == "private" and self.group_id:
            outs.append(Out("send", text, "group"))
        return outs

    def _banner(self):
        return Out("banner")

    def _need_game(self, msg):
        if self.eng.status in ("running", "paused"):
            return None
        return self._say(msg, "⚠️ الان بازی فعالی نداریم. از پنل خصوصی «شروع بازی جدید» را بزن.")

    def _player(self, msg, name):
        p, cands = self.eng.players.find(name)
        if p:
            return p, None
        if cands:
            names = "، ".join(c["name"] for c in cands)
            return None, self._say(msg, f"🤔 چند بازیکن با این نام هست: {names}\nنام کامل‌تر بنویس.")
        return None, self._say(msg, f"❌ بازیکنی با نام «{clean_display(name)}» پیدا نشد.\nبرای دیدن فهرست بنویس: وضعیت بازیکنان")

    def _topic(self, msg, name):
        t = self.bank.find_topic(name)
        if t:
            return t, None
        names = "، ".join(x["name"] for x in self.bank.list_topics())
        return None, self._say(msg, f"❌ موضوعی با نام «{clean_display(name)}» نیست.\nموضوع‌ها: {names}")

    def players_text(self):
        act, out = self.eng.players.active(), self.eng.players.eliminated()
        if not act and not out:
            return "هنوز بازیکنی ثبت نشده."
        lines = [f"👥 بازیکنان فعال ({fa(len(act))}):"]
        lines += [f"{fa(i)}. {p['name']} {bn.hearts_str(p['hearts'])}" for i, p in enumerate(act, 1)]
        if out:
            lines.append("")
            lines.append("💀 حذف‌شده‌ها: " + "، ".join(p["name"] for p in out))
        return "\n".join(lines)

    def status_text(self):
        s = self.eng.summary()
        names = {"idle": "شروع نشده", "running": "در حال اجرا", "paused": "متوقف", "finished": "تمام‌شده"}
        lines = [f"📊 وضعیت بازی: {names.get(s['status'], s['status'])}"]
        if s["topic"]:
            lines.append(f"📚 موضوع: {s['topic']}")
        if s["status"] in ("running", "paused"):
            lines.append(f"🔢 دور: {fa(s['round'])}" + (" (تعیین تکلیف)" if s["tiebreak"] else ""))
            if s["phase"] == "picking":
                w = self.eng.winner_player()
                lines.append(f"🎯 در انتظار انتخاب بازیکن توسط: {w['name'] if w else '—'}")
            ts = {"none": "شروع نشده", "running": "در حال شمارش", "paused": "متوقف"}[s["timer_state"]]
            rem = f" — {fa(int(s['remaining']))} ثانیه مانده" if s["remaining"] is not None else ""
            lines.append(f"⏱ تایمر: {fa(s['timer_len'])} ثانیه، {ts}{rem}")
            if s["last"]:
                lines.append(f"🗣 آخرین پاسخ‌دهنده‌ی معتبر: {s['last']}")
            if s["pending"]:
                lines.append(f"❓ جواب ناشناخته‌ی منتظر تصمیم: {fa(s['pending'])}")
        lines.append(f"👥 فعال: {fa(s['active'])} | 💀 حذف‌شده: {fa(s['eliminated'])}")
        return "\n".join(lines)

    def ranking_text(self, with_prizes=False):
        ranking = self.db.get("ranking") or []
        prizes = self.eng.prizes
        wc = prizes.winners_count()
        lines = ["🏁 رتبه‌بندی نهایی «آخرین واژه»"]
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for r in ranking:
            h = bn.hearts_str(r["hearts"]) if r["hearts"] else "💀"
            line = f"{medals.get(r['rank'], '▫️')} {fa(r['rank'])}. {r['name']} — {h}" + (" (مساوی)" if r.get("tie") else "")
            if with_prizes and r["rank"] <= wc:
                pz = prizes.prize_for(r["rank"])
                if pz:
                    line += f" — 🎁 {pz}"
            lines.append(line)
        return "\n".join(lines)

    def _event_outs(self, events):
        outs = []
        for e in events:
            if e["type"] == "finished":
                outs.append(Out("countdown", "🏁 بازی تمام شد", "group", final=True))
                outs.append(Out("send", self.ranking_text() + "\n\nبرای اعلام جایزه‌ها مالک بنویسد: اعلام برندگان", "group"))
                outs.append(Out("send", "🏁 بازی تمام شد. بعد از اعلام برندگان، برای بازی بعد «پاک‌سازی بازیکنان» را بزن.", "owner"))
            elif e["type"] == "tiebreak":
                a, b = e["players"]
                outs.append(Out("send", f"⚖️ دو بازیکن آخر ({a['name']} و {b['name']}) قلب مساوی دارند!\n"
                                        "🔥 دور تعیین تکلیف: برنده‌ی این دور، رتبه‌ی اول است.", "group"))
        return outs

    # ------------------------------------------------------------ پیام‌های متنی
    def on_text(self, msg: Msg, now=None) -> List[Out]:
        outs: List[Out] = []
        if msg.chat_type == "private":
            if not self.is_owner(msg.user_id):
                return [Out("send", "⛔ این ربات فقط برای مالک قابل مدیریت است. بازی در گروه انجام می‌شود.")]
            return self._private(msg)
        if self.group_id is not None and msg.chat_id != self.group_id:
            if not (self.is_owner(msg.user_id) and commands.parse(msg.text) and commands.parse(msg.text)[0] == "group_id"):
                return []
        # گروه
        outs += self.on_tick(now)
        parsed = commands.parse(msg.text)
        if parsed and parsed[0] != "verdict" or (parsed and parsed[0] == "verdict" and self.is_owner(msg.user_id)):
            if self.is_owner(msg.user_id):
                return outs + self._exec(parsed[0], parsed[1], msg)
            return outs                      # فرمان از غیرمالک: بی‌اثر و بی‌سروصدا
        return outs + self._answer(msg)

    def _private(self, msg):
        t = (msg.text or "").strip()
        if t in ("/start", "/panel", "/menu", "پنل"):
            return self._panel()
        if t in ("/id", "/chatid"):
            return self._say(msg, f"🆔 شناسه‌ی شما: {msg.user_id}\n🆔 شناسه‌ی گروه ثبت‌شده: {self.group_id or 'ثبت نشده'}")
        parsed = commands.parse(t)
        aw = self.db.get("await")
        wz = self.db.get("wizard")
        if parsed and parsed[0] in ("confirm_no",) and (aw or wz):
            self.db.delete("await"); self.db.delete("wizard")
            return self._say(msg, "❌ لغو شد.", [BACK])
        if aw and not (parsed and parsed[0] not in ("verdict",)):
            return self._handle_await(msg, aw)
        if wz and not (parsed and parsed[0] not in ("verdict",)):
            return self._wizard_text(msg, wz)
        if parsed:
            return self._exec(parsed[0], parsed[1], msg)
        return self._say(msg, "🤔 متوجه نشدم. پنل را باز می‌کنم:", None) + self._panel()

    def _panel(self):
        b = [("🎮 شروع بازی جدید", "menu:new"), ("📚 انتخاب موضوعات", "menu:topics"),
             ("👥 مدیریت بازیکنان", "menu:players"), ("❤️ مدیریت قلب‌ها", "menu:hearts"),
             ("⏱ تنظیم تایمر", "menu:timer"), ("🎁 مدیریت جایزه‌ها", "menu:prizes"),
             ("🖼 ویرایش بنر", "menu:banner"), ("📊 وضعیت بازی", "menu:status"),
             ("📖 راهنمای کامل", "menu:help"), ("🧹 پاک‌سازی بازیکنان", "menu:clear"),
             ("🏁 پایان بازی", "menu:end"), ("⚙️ تنظیمات بازی", "menu:settings")]
        return [Out("send", PANEL, "here", kb_rows(b))]

    # ------------------------------------------------------------ جواب‌های بازیکنان
    def _answer(self, msg):
        eng = self.eng
        if eng.status != "running" or eng.phase != "answering" or not looks_like_answer(msg.text):
            return []
        player = eng.players.match_sender(msg.user_id, [msg.name, msg.full_name, msg.username])
        if not player:
            return []
        res = eng.process_answer(player, msg.text, msg.chat_id, msg.message_id)
        k = res["kind"]
        if k == "valid":
            return [Out("countdown", f"✅ «{res['canonical']}» ثبت شد — {player['name']}\n⏳ شمارش تا چند لحظه‌ی دیگر شروع می‌شود…", "group")]
        if k == "dup":
            return [Out("send", f"♻️ «{res['canonical']}» قبلاً گفته شده — تکراری است.", "here", reply_to=msg.message_id)]
        if k == "rejected_before":
            return [Out("send", "❌ این جواب قبلاً توسط مالک رد شده است.", "here", reply_to=msg.message_id)]
        if k == "unknown":
            return [Out("send", f"❓ «{clean_display(msg.text)}» در بانک نیست؛ منتظر نظر مالک.\n"
                                f"(مالک: «{clean_display(msg.text)} قبول» یا «{clean_display(msg.text)} رد» یا ریپلای قبول/رد)", "here",
                        reply_to=msg.message_id),
                    Out("countdown", "⏸ تایمر تا تصمیم مالک درباره‌ی جواب ناشناخته متوقف شد.", "group")]
        return []

    # ------------------------------------------------------------ تایمر (هر ~۰٫۵ ثانیه)
    def on_tick(self, now=None) -> List[Out]:
        outs = []
        for e in self.eng.tick(now):
            if e["type"] == "countdown":
                sec = e["sec"]
                if sec <= 10 or sec % 5 == 0:
                    outs.append(Out("countdown", f"⏳ {fa(sec)}\n🗣 آخرین جواب: {self._last_line()}", "group"))
            elif e["type"] == "no_winner":
                outs.append(Out("countdown", "⏰ زمان تمام شد اما جواب معتبری ثبت نشده بود.", "group", final=True))
            elif e["type"] == "round_end":
                w = e["winner"]
                outs.append(Out("countdown", "⏰ زمان تمام شد!", "group", final=True))
                if e.get("final"):
                    outs.append(Out("send", f"🔥 {w['name']} دور تعیین تکلیف را برد و رتبه‌ی اول شد!", "group"))
                else:
                    b = [(f"{p['name']} {bn.hearts_str(p['hearts'])}", f"pick:{e['round_id']}:{p['id']}")
                         for p in self.eng.players.active() if p["id"] != w["id"]]
                    outs.append(Out("send", f"🏆 برنده‌ی دور {fa(self.eng.round_no)}: {w['name']}\n"
                                            f"🎯 {w['name']}، یکی را انتخاب کن تا یک قلب از او کم شود:\n"
                                            "(یا بنویس: انتخاب نام)", "group", kb_rows(b)))
                outs.append(self._banner())
            elif e["type"] == "finished":
                outs += self._event_outs([e])
                outs.append(self._banner())
        return outs

    def _last_line(self):
        h = self.eng._latest_valid()
        if not h:
            return "—"
        p = self.eng.players.get(h["player_id"])
        return f"{self.bank.canonical(h['answer_id'])} — {p['name']}"

    # ------------------------------------------------------------ اجرای فرمان‌ها
    def _exec(self, cmd, a, msg):
        fn = getattr(self, f"c_{cmd}", None)
        if fn is None:
            return self._say(msg, "🤔 این فرمان شناخته نشد. «راهنما» را بنویس.")
        return fn(msg, *a)

    def c_invalid(self, msg, verb):
        return self._say(msg, f"🤔 فرمان درست نوشته نشده («{verb} …»).\nنمونه‌ها را ببین:\n\n{HELP['کل']}")

    def c_help(self, msg, topic=None):
        if not topic:
            return self._say(msg, HELP["کل"])
        key = topic.replace("\u200c", "")
        for k, v in HELP.items():
            if k.replace("\u200c", "") == key:
                return self._say(msg, v)
        return self._say(msg, HELP["کل"])

    def c_group_id(self, msg):
        if msg.chat_type == "private":
            return self._say(msg, f"🆔 شناسه‌ی گروه ثبت‌شده: {self.group_id or 'هنوز ثبت نشده — داخل گروه بنویس: ثبت گروه'}")
        if not self.is_owner(msg.user_id):
            return []
        self.db.set("group_chat_id", msg.chat_id)
        return self._say(msg, f"✅ این گروه ثبت شد.\n🆔 شناسه‌ی عددی گروه: {msg.chat_id}\n"
                              "(برای دائمی شدن می‌توانی آن را در Render به‌عنوان GROUP_CHAT_ID هم بگذاری)")

    # --- بازی
    def c_start_game(self, msg):
        if msg.chat_type != "private":
            return self._say(msg, "🎮 شروع بازی از پیوی ربات انجام می‌شود (چون چند مرحله انتخاب دارد). به پیوی من برو و «شروع بازی» بزن.")
        return self._wizard_start(msg)

    def c_stop_game(self, msg):
        if self.eng.status != "running":
            return self._need_game(msg) or self._say(msg, "⏸ بازی همین الان هم متوقف است.")
        self.eng.pause_game()
        return self._say(msg, "⏸ بازی متوقف شد. جواب‌ها پردازش نمی‌شوند. برای ادامه: ادامه بازی", also_group=True) + [self._banner()]

    def c_resume_game(self, msg):
        if self.eng.status != "paused":
            return self._need_game(msg) or self._say(msg, "▶️ بازی متوقف نیست.")
        self.eng.resume_game()
        return self._say(msg, "▶️ بازی ادامه پیدا کرد.", also_group=True) + [self._banner()]

    def c_end_game(self, msg):
        if self.eng.status not in ("running", "paused"):
            return self._need_game(msg)
        return self._ask_confirm(msg, "end_game", {}, "🏁 مطمئنی بازی همین الان تمام شود؟")

    def c_status_game(self, msg):
        return self._say(msg, self.status_text())

    # --- تایمر
    def c_timer_start(self, msg, n=None):
        if not n:
            return self._say(msg, "⏱ عدد ثانیه را هم بنویس. مثال: شروع تایمر ۱۰")
        n = int(n)
        if n < 1 or n > 600:
            return self._say(msg, "⚠️ زمان تایمر باید بین ۱ تا ۶۰۰ ثانیه باشد.")
        self.eng.set_timer_len(n)
        extra = ""
        if self.eng.status == "running" and self.eng.timer_state == "running" and self.eng.restart_timer():
            extra = "\n🔄 شمارش دوباره با زمان جدید شروع شد."
        return self._say(msg, f"⏱ طول تایمر روی {fa(n)} ثانیه تنظیم شد.{extra}", also_group=True) + [self._banner()]

    def c_timer_stop(self, msg):
        if self.eng.status not in ("running", "paused"):
            return self._need_game(msg)
        if self.eng.pause_timer():
            return self._say(msg, "⏸ تایمر متوقف شد (بقیه‌ی بازی ادامه دارد). برای ادامه: ادامه تایمر", also_group=True) + [self._banner()]
        return self._say(msg, "⚠️ الان تایمری در حال شمارش نیست.")

    def c_timer_resume(self, msg):
        r = self.eng.resume_timer()
        text = {"ok": "▶️ تایمر از زمان باقی‌مانده ادامه پیدا کرد.",
                "game_paused": "⚠️ بازی متوقف است؛ اول «ادامه بازی».",
                "not_paused": "⚠️ تایمر متوقف نیست.",
                "pending_open": "⚠️ یک جواب ناشناخته منتظر تصمیم توست (قبول/رد)."}[r]
        return self._say(msg, text, also_group=(r == "ok")) + ([self._banner()] if r == "ok" else [])

    # --- بازیکنان
    def c_players_status(self, msg):
        return self._say(msg, self.players_text())

    def c_player_add(self, msg, name, hearts=None):
        if self.eng.status not in ("running", "paused"):
            return self._need_game(msg)
        h = int(hearts) if hearts else int(self.db.get("init_hearts", 3))
        if h < 1:
            return self._say(msg, "⚠️ تعداد قلب باید حداقل ۱ باشد.")
        st, p, events = self.eng.add_player(name, h)
        text = {"added": f"✅ {p['name'] if p else name} با {fa(h)} قلب به بازی اضافه شد." if p else "",
                "reactivated": f"🔁 {p['name'] if p else ''} دوباره به بازی برگشت با {fa(h)} قلب.",
                "duplicate": f"♻️ «{clean_display(name)}» از قبل در بازی هست.",
                "invalid": "⚠️ نام بازیکن معتبر نیست."}[st]
        return self._say(msg, text, also_group=st in ("added", "reactivated")) + self._event_outs(events) + [self._banner()]

    def c_player_remove(self, msg, name):
        if self.eng.status not in ("running", "paused"):
            return self._need_game(msg)
        p, err = self._player(msg, name)
        if err:
            return err
        events = self.eng.remove_player(p)
        return self._say(msg, f"🗑 {p['name']} از بازی حذف شد (از بنر هم پاک شد).", also_group=True) + self._event_outs(events) + [self._banner()]

    def c_link(self, msg, name=None):
        if not msg.reply_to_user:
            return self._say(msg, "🔗 این فرمان را به‌صورت ریپلای روی پیام خود بازیکن بزن. مثال: ربط نوید")
        if not name:
            return self._say(msg, "نام بازیکن را هم بنویس. مثال: ربط نوید")
        p, err = self._player(msg, name)
        if err:
            return err
        self.eng.players.link(p["id"], msg.reply_to_user)
        return self._say(msg, f"🔗 {p['name']} به این کاربر تلگرام وصل شد.")

    # --- قلب‌ها
    def _hearts(self, msg, name, delta=None, set_to=None):
        if self.eng.status not in ("running", "paused"):
            return self._need_game(msg)
        p, err = self._player(msg, name)
        if err:
            return err
        if not p["active"]:
            return self._say(msg, f"💀 {p['name']} حذف شده است. برای برگرداندن: افزودن بازیکن {p['name']} به بازی با ۳ قلب")
        res = self.eng.change_hearts(p, delta=delta, set_to=set_to)
        note = " (قلب منفی نمی‌شود؛ روی ۰ تنظیم شد)" if res["clamped"] else ""
        text = f"{'❤️' if not res['eliminated'] else '💀'} قلب‌های {p['name']}: {fa(res['hearts'])}{note}"
        if res["eliminated"]:
            text += f"\n💀 {p['name']} با صفر قلب از بازی حذف شد."
        return self._say(msg, text, also_group=True) + self._event_outs(res["events"]) + [self._banner()]

    def c_heart_sub(self, msg, n, name):
        return self._hearts(msg, name, delta=-(int(n) if n else 1))

    def c_heart_add(self, msg, n, name):
        return self._hearts(msg, name, delta=int(n) if n else 1)

    def c_heart_set(self, msg, name, n):
        return self._hearts(msg, name, set_to=int(n))

    def c_pick(self, msg, name):
        eng = self.eng
        if eng.status != "running" or eng.phase != "picking":
            return self._say(msg, "⚠️ الان نوبت انتخاب بازیکن نیست.")
        w = eng.winner_player()
        if not (self.is_owner(msg.user_id) or (w and w["tg_user_id"] == msg.user_id)):
            return []
        v, err = self._player(msg, name)
        if err:
            return err
        return self._do_pick(msg, self.db.get("current_round_id"), v["id"])

    def _do_pick(self, msg, round_id, victim_id):
        r = self.eng.pick(round_id, victim_id)
        if not r["ok"]:
            text = {"not_picking": "⚠️ این انتخاب دیگر معتبر نیست.", "bad_victim": "⚠️ این بازیکن قابل انتخاب نیست.",
                    "self": "⚠️ نمی‌توانی خودت را انتخاب کنی."}[r["error"]]
            return [Out("toast", text)] if msg is None else self._say(msg, text)
        v = r["victim"]
        text = f"🎯 انتخاب شد: {v['name']}\n{'💀' if r['eliminated'] else '❤️'} قلب‌های {v['name']}: {fa(r['hearts'])}"
        if r["eliminated"]:
            text += f"\n💀 {v['name']} حذف شد."
        outs = [Out("send", text, "group")] + self._event_outs(r["events"]) + [self._banner()]
        if r["events"] == [] and self.eng.status == "running":
            outs.append(Out("send", f"▶️ دور {fa(self.eng.round_no)} شروع شد. اولین جواب را بگویید!", "group"))
        return outs

    # --- موضوعات و بانک
    def c_topics_list(self, msg):
        lines = ["📚 موضوعات:"]
        for t in self.bank.list_topics():
            lines.append(f"• {t['name']} ({fa(t['n'])} جواب)" + ("" if t["builtin"] else " — اضافه‌شده"))
        cur = self.eng.topic_name()
        if cur and self.eng.status in ("running", "paused"):
            lines.append(f"\n📌 موضوع بازی فعلی: {cur}")
        return self._say(msg, "\n".join(lines))

    def c_topic_add(self, msg, name):
        name = clean_display(name)
        if not normalize(name):
            return self._say(msg, "⚠️ نام موضوع معتبر نیست.")
        tid = self.bank.add_topic(name)
        if tid is None:
            return self._say(msg, f"ℹ️ موضوع «{name}» از قبل وجود دارد.")
        return self._say(msg, f"✅ موضوع «{name}» اضافه شد. حالا واژه بده: افزودن واژه به {name}")

    def c_topic_del(self, msg, name):
        t, err = self._topic(msg, name)
        if err:
            return err
        if t["builtin"]:
            return self._say(msg, f"🔒 «{t['name']}» از ۱۰ موضوع اصلی است و دائمی؛ حذف نمی‌شود.")
        if self.eng.status in ("running", "paused") and self.eng.topic_id == t["id"]:
            return self._say(msg, "⚠️ این موضوع الان موضوع بازی است؛ حذف نمی‌شود.")
        return self._ask_confirm(msg, "topic_del", {"id": t["id"]}, f"🗑 موضوع «{t['name']}» با همه‌ی واژه‌هایش حذف شود؟")

    def c_topic_change(self, msg, name):
        if self.eng.status not in ("running", "paused"):
            return self._need_game(msg)
        t, err = self._topic(msg, name)
        if err:
            return err
        return self._ask_confirm(msg, "topic_change", {"id": t["id"]}, f"🔁 موضوع بازی وسط بازی به «{t['name']}» عوض شود؟")

    def c_bank_add(self, msg, word, topic):
        t, err = self._topic(msg, topic)
        if err:
            return err
        pend = self.eng.find_pending(word) if self.eng.topic_id == t["id"] else None
        if pend:
            return self._verdict_accept(msg, pend)
        aid, st = self.bank.add_answer(t["id"], word)
        if st == "empty":
            return self._say(msg, "⚠️ واژه خالی است.")
        text = {"new": f"✅ «{clean_display(word)}» به «{t['name']}» اضافه شد.",
                "exists": f"ℹ️ «{clean_display(word)}» از قبل در «{t['name']}» بود.",
                "merged": f"🔗 شکل‌های جدید به «{self.bank.canonical(aid)}» در «{t['name']}» اضافه شد."}[st]
        return self._say(msg, text)

    def c_bank_del(self, msg, word, topic):
        t, err = self._topic(msg, topic)
        if err:
            return err
        if self.bank.remove_answer(t["id"], word):
            return self._say(msg, f"🗑 «{clean_display(word)}» از «{t['name']}» حذف شد.")
        return self._say(msg, f"❌ «{clean_display(word)}» در «{t['name']}» پیدا نشد.")

    def c_verdict(self, msg, word, verdict):
        eng = self.eng
        pend = eng.find_pending(text=word, chat_id=msg.chat_id, message_id=msg.reply_to_id) if (word or msg.reply_to_id) else None
        if pend:
            if verdict == "قبول":
                return self._verdict_accept(msg, pend)
            r = eng.reject_pending(pend["id"])
            extra = "\n▶️ تایمر ادامه پیدا کرد." if r["resumed"] else ""
            return self._say(msg, f"❌ «{pend['raw']}» رد شد؛ در این دور حساب نمی‌شود.{extra}") 
        hist = eng.find_valid_history(text=word, message_id=msg.reply_to_id)
        if hist and verdict == "رد":
            r = eng.revoke(hist["id"])
            last = r["last"]
            extra = f"آخرین جواب معتبر قبلی: {self._last_line()}" if last else "جواب معتبری در این دور نمانده؛ تایمر متوقف شد."
            return self._say(msg, f"↩️ جواب «{hist['raw']}» لغو و از تاریخچه اصلاح شد.\n{extra}") + [self._banner()]
        if hist and verdict == "قبول":
            return self._say(msg, "ℹ️ این جواب قبلاً پذیرفته شده است.")
        if not word and not msg.reply_to_id:
            return self._say(msg, "کدام واژه؟ مثال: کنگاش قبول — یا ریپلای روی پیام بازیکن بنویس «قبول»")
        return self._say(msg, "❌ چنین جوابی در انتظار بررسی نیست.")

    def _verdict_accept(self, msg, pend):
        res = self.eng.accept_pending(pend["id"])
        text = f"✅ «{pend['raw']}» به بانک دائمی اضافه شد."
        outs = self._say(msg, text)
        if res and res["registered"]:
            outs.append(Out("countdown", f"✅ «{res['canonical']}» ثبت شد — {res['player']['name']}\n⏳ شمارش تا چند لحظه‌ی دیگر شروع می‌شود…", "group"))
        return outs

    # --- جایزه‌ها
    def c_prize_set(self, msg, rank, name):
        pz = self.eng.prizes
        if rank:
            pz.set(int(rank), name)
            r = int(rank)
        else:
            r = pz.append(name)
        w = pz.warning()
        return self._say(msg, f"🎁 جایزه‌ی رتبه {fa(r)}: {name.strip()}" + (f"\n{w}" if w else "")) + [self._banner()]

    def c_prize_del(self, msg, rank):
        ok = self.eng.prizes.delete(int(rank))
        return self._say(msg, f"🗑 جایزه‌ی رتبه {fa(rank)} حذف شد." if ok else "❌ چنین جایزه‌ای نیست.") + [self._banner()]

    def c_winners_count(self, msg, n=None):
        pz = self.eng.prizes
        if n is None:
            return self._say(msg, f"🏆 تعداد برندگان: {fa(pz.winners_count())}")
        pz.set_winners_count(int(n))
        w = pz.warning()
        return self._say(msg, f"🏆 تعداد برندگان: {fa(n)}" + (f"\n{w}" if w else ""))

    def c_prizes_count(self, msg, n=None):
        pz = self.eng.prizes
        if n is None:
            lines = pz.lines() or ["هنوز جایزه‌ای ثبت نشده."]
            return self._say(msg, f"🎁 تعداد جایزه‌ها: {fa(pz.count())}\n" + "\n".join(lines))
        n = int(n)
        for r in range(pz.count() + 1, n + 1):
            pz.set(r, "(هنوز تعیین نشده)")
        pz.set_count(n)
        w = pz.warning()
        return self._say(msg, f"🎁 تعداد جایزه‌ها: {fa(n)}\nبا «تغییر جایزه ۱: متن» نام هر جایزه را بنویس." + (f"\n{w}" if w else "")) + [self._banner()]

    def c_announce(self, msg):
        eng = self.eng
        w = eng.prizes.warning()
        if eng.status != "finished":
            return self._say(msg, "⚠️ بازی هنوز تمام نشده. برای پایان دستی: پایان بازی" + (f"\n{w}" if w else ""))
        outs = [Out("send", self.ranking_text(with_prizes=True), "group")]
        if w:
            outs.append(Out("send", w, "owner"))
        if msg.chat_type == "private":
            outs.append(Out("send", "✅ اعلام شد.", "here"))
        return outs

    # --- بنر
    def c_banner_edit(self, msg):
        if msg.chat_type != "private":
            return self._say(msg, "🖼 ویرایش بنر از پیوی ربات انجام می‌شود.")
        self.db.set("await", {"kind": "banner_text"})
        return self._say(msg, "🖼 متن جدید بالای بنر را بفرست (چند خط). برای لغو: لغو\n\nمتن فعلی:\n" + (self.db.get("banner_header") or bn.DEFAULT_HEADER))

    def c_banner_show(self, msg):
        draft = self.db.get("banner_draft")
        text = bn.render(self.db, self.eng) if not draft else self._render_with(draft)
        return self._say(msg, ("👁 پیش‌نمایش (پیش‌نویس):\n" if draft else "👁 بنر فعلی:\n") + text)

    def _render_with(self, header):
        old = self.db.get("banner_header")
        self.db.set("banner_header", header)
        try:
            return bn.render(self.db, self.eng)
        finally:
            if old is None:
                self.db.delete("banner_header")
            else:
                self.db.set("banner_header", old)

    def c_banner_ok(self, msg):
        draft = self.db.get("banner_draft")
        if not draft:
            return self._say(msg, "⚠️ پیش‌نویسی نیست. اول «ویرایش بنر».")
        self.db.set("banner_header", draft)
        self.db.delete("banner_draft")
        return self._say(msg, "✅ بنر تأیید شد و پیام پین‌شده به‌روز می‌شود.") + [self._banner()]

    def c_banner_update(self, msg):
        return self._say(msg, "🔄 بنر به‌روزرسانی شد.") + [self._banner()]

    def c_banner_reset(self, msg):
        self.db.delete("banner_header")
        self.db.delete("banner_draft")
        return self._say(msg, "♻️ متن بنر به حالت پیش‌فرض برگشت.") + [self._banner()]

    # --- پاک‌سازی
    def c_cleanup(self, msg):
        if self.eng.status in ("running", "paused"):
            return self._say(msg, "⚠️ بازی هنوز در جریان است. اول «پایان بازی».")
        return self._ask_confirm(msg, "cleanup1", {}, "🧹 همه‌ی بازیکن‌ها، قلب‌ها، تاریخچه و تایمر بازی قبلی پاک شود؟\n(موضوع‌ها و بانک واژه‌ها پاک نمی‌شوند)")

    # --- تأیید و لغو
    def _ask_confirm(self, msg, action, args, text):
        self.db.set("pending_confirm", {"action": action, "args": args})
        return [Out("send", text, "here", [[("✅ تأیید", "cf:yes"), ("❌ لغو", "cf:no")]],
                    reply_to=msg.message_id if msg.chat_type != "private" else None)]

    def c_confirm_yes(self, msg):
        return self._confirm(msg, True)

    def c_confirm_no(self, msg):
        return self._confirm(msg, False)

    def _confirm(self, msg, yes):
        pc = self.db.get("pending_confirm")
        if not pc:
            return self._say(msg, "ℹ️ چیزی برای تأیید نیست.")
        self.db.delete("pending_confirm")
        if not yes:
            return self._say(msg, "❌ لغو شد.")
        act, args, eng = pc["action"], pc["args"], self.eng
        if act == "end_game":
            if eng.status not in ("running", "paused"):
                return self._say(msg, "ℹ️ بازی فعالی نیست.")
            eng.finish(manual=True)
            return self._say(msg, "🏁 بازی تمام شد.") + self._event_outs([{"type": "finished"}]) + [self._banner()]
        if act == "topic_del":
            ok = self.bank.remove_topic(args["id"])
            return self._say(msg, "🗑 موضوع حذف شد." if ok else "⚠️ حذف نشد.")
        if act == "topic_change":
            eng.db.set("topic_id", args["id"])
            t = self.bank.get_topic(args["id"])
            return self._say(msg, f"🔁 موضوع بازی به «{t['name']}» تغییر کرد.", also_group=True) + [self._banner()]
        if act == "cleanup1":
            self.db.set("pending_confirm", {"action": "cleanup2", "args": {}})
            return [Out("send", "⚠️ تأیید دوم: واقعاً پاک شود؟ این کار برگشت ندارد.", "here", [[("🧹 بله، پاک کن", "cf:yes"), ("❌ لغو", "cf:no")]])]
        if act == "cleanup2":
            eng.clear()
            return self._say(msg, "🧹 پاک‌سازی انجام شد. موضوع‌ها و بانک واژه‌ها سالم ماندند. پنل برای بازی جدید آماده است.", also_group=False) \
                + [Out("send", "🧹 بازی قبلی پاک شد؛ منتظر بازی جدید باشید.", "group"), self._banner()]
        return self._say(msg, "ℹ️ چیزی برای تأیید نبود.")

    # ------------------------------------------------------------ ویزارد «شروع بازی جدید»
    def _wizard_start(self, msg):
        st = self.eng.status
        if st in ("running", "paused"):
            return self._say(msg, "⚠️ یک بازی در جریان است. اول «پایان بازی» را بزن.")
        if st == "finished":
            return self._say(msg, "⚠️ بازی قبلی هنوز پاک نشده. اول «پاک‌سازی بازیکنان» را بزن.", [[("🧹 پاک‌سازی بازیکنان", "menu:clear")]])
        self.db.set("wizard", {"step": "topic"})
        return self._wizard_topic_prompt()

    def _wizard_topic_prompt(self):
        b = [(t["name"], f"wz:t:{t['id']}") for t in self.bank.list_topics()]
        return [Out("send", "🎮 بازی جدید — مرحله ۱ از ۵\n📚 موضوع بازی را انتخاب کن:", "here", kb_rows(b) + [[("❌ لغو", "wz:cancel")]])]

    def _wizard_summary(self, wz):
        t = self.bank.get_topic(wz["topic_id"])
        names = wz["names"]
        lines = ["📋 خلاصه‌ی تنظیمات بازی:",
                 f"📚 موضوع: {t['name']}",
                 f"👥 بازیکنان ({fa(len(names))}):"]
        lines += [f"{fa(i)}. {n}" for i, n in enumerate(names, 1)]
        lines += [f"❤️ قلب هر بازیکن: {fa(wz['hearts'])}",
                  f"⏱ تایمر: {fa(self.eng.timer_len)} ثانیه (قابل تغییر)"]
        pz = self.eng.prizes.lines()
        lines.append(f"🎁 جایزه‌ها: {'' if pz else 'تنظیم نشده'}")
        lines += pz
        lines.append(f"🏆 تعداد برندگان: {fa(self.eng.prizes.winners_count())}")
        w = self.eng.prizes.warning()
        if w and (pz or self.eng.prizes.winners_count()):
            lines.append(w)
        return "\n".join(lines)

    def _wizard_text(self, msg, wz):
        step = wz["step"]
        t = (msg.text or "").strip()
        if step == "players":
            seen, names, dups = set(), [], []
            for line in t.splitlines():
                nm = clean_display(line)
                if not normalize(nm):
                    continue
                if normalize(nm) in seen:
                    dups.append(nm)
                    continue
                seen.add(normalize(nm)); names.append(nm)
            if len(names) < 3:
                return self._say(msg, "⚠️ حداقل ۳ بازیکن لازم است. هر نام را در یک خط بنویس و دوباره بفرست.")
            wz.update(names=names, step="hearts")
            self.db.set("wizard", wz)
            extra = f"\n♻️ نام‌های تکراری حذف شد: {'، '.join(dups)}" if dups else ""
            return self._say(msg, f"✅ {fa(len(names))} بازیکن ثبت شد.{extra}\n\n❤️ مرحله ۳ از ۵: هر بازیکن چند قلب داشته باشد؟ (یک عدد)")
        if step == "hearts":
            digits = t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
            if not digits.isdigit() or int(digits) < 1 or int(digits) > 99:
                return self._say(msg, "⚠️ فقط یک عدد درست بین ۱ تا ۹۹ بفرست (مثلاً ۳).")
            wz.update(hearts=int(digits), step="prizes")
            self.db.set("wizard", wz)
            return self._say(msg, "🎁 مرحله ۴ از ۵: جایزه‌ها (اختیاری)",
                             [[("🎁 تنظیم جایزه‌ها", "wz:prizes:set"), ("⏭ رد کردن", "wz:prizes:skip")]])
        if step == "prizes_text":
            names = [clean_display(x) for x in t.splitlines() if clean_display(x)]
            if not names:
                return self._say(msg, "⚠️ حداقل یک جایزه بنویس (هر جایزه در یک خط، به ترتیب رتبه).")
            self.eng.prizes.replace_all(names)
            wz["step"] = "confirm"
            self.db.set("wizard", wz)
            return self._wizard_confirm_out()
        return self._say(msg, "از دکمه‌های بالا استفاده کن یا «لغو» بنویس.")

    def _wizard_confirm_out(self):
        wz = self.db.get("wizard")
        return [Out("send", "✅ مرحله ۵ از ۵ — تأیید نهایی\n\n" + self._wizard_summary(wz), "here",
                    [[("✅ تأیید و شروع بازی", "wz:ok")], [("↩️ برگشت و اصلاح", "wz:back"), ("❌ لغو", "wz:cancel")]])]

    def _wizard_go(self):
        wz = self.db.get("wizard")
        if not wz or wz.get("step") != "confirm":
            return [Out("toast", "این مرحله دیگر معتبر نیست.")]
        res = self.eng.start_game(wz["topic_id"], wz["names"], wz["hearts"])
        if not res["ok"]:
            text = {"game_running": "یک بازی در جریان است.", "few_players": "حداقل ۳ بازیکن لازم است.",
                    "bad_hearts": "تعداد قلب نامعتبر است.", "no_topic": "موضوع پیدا نشد."}[res["error"]]
            return [Out("send", "⚠️ " + text, "here")]
        self.db.delete("wizard")
        t = self.eng.topic_name()
        outs = [Out("send", "🚀 بازی شروع شد! بنر در گروه ساخته/به‌روز می‌شود.", "here"), self._banner()]
        if self.group_id:
            outs.append(Out("send", f"🎮 بازی «آخرین واژه» شروع شد!\n📚 موضوع: {t}\n❤️ هر بازیکن {fa(wz['hearts'])} قلب\n"
                                    f"⏱ تایمر: {fa(self.eng.timer_len)} ثانیه\n\nاولین نفر جواب بدهد! 🌵", "group"))
        else:
            outs.append(Out("send", "⚠️ شناسه‌ی گروه ثبت نشده! داخل گروه بنویس «ثبت گروه» (یا GROUP_CHAT_ID را در Render بگذار).", "here"))
        return outs

    # ------------------------------------------------------------ ورودی‌های منتظرِ متن
    def _handle_await(self, msg, aw):
        kind, t = aw["kind"], (msg.text or "").strip()
        self.db.delete("await")
        if kind == "timer":
            d = t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
            if not d.isdigit():
                self.db.set("await", aw)
                return self._say(msg, "⚠️ فقط یک عدد (ثانیه) بفرست. یا «لغو».")
            return self.c_timer_start(msg, d)
        if kind == "players_add":
            outs = []
            for line in t.splitlines():
                if normalize(line):
                    outs += self.c_player_add(msg, line, None)
            return outs
        if kind == "topic_add":
            return self.c_topic_add(msg, t)
        if kind == "banner_text":
            if not t:
                self.db.set("await", aw)
                return self._say(msg, "⚠️ متن خالی است. دوباره بفرست یا «لغو».")
            self.db.set("banner_draft", t)
            return self._say(msg, "👁 پیش‌نمایش:\n\n" + self._render_with(t),
                             [[("✅ تأیید بنر", "bn:ok"), ("✏️ ویرایش دوباره", "bn:edit")]])
        if kind == "prizes":
            names = [clean_display(x) for x in t.splitlines() if clean_display(x)]
            if not names:
                self.db.set("await", aw)
                return self._say(msg, "⚠️ حداقل یک جایزه بنویس.")
            self.eng.prizes.replace_all(names)
            return self._say(msg, "🎁 جایزه‌ها ثبت شد:\n" + "\n".join(self.eng.prizes.lines())) + [self._banner()]
        return []

    # ------------------------------------------------------------ دکمه‌های شیشه‌ای
    def on_callback(self, user_id, chat_id, message_id, data, now=None) -> List[Out]:
        m = Msg(user_id, chat_id, "private", "", message_id)
        parts = data.split(":")
        if parts[0] == "pick":
            return self._cb_pick(user_id, chat_id, int(parts[1]), int(parts[2]), now)
        if not self.is_owner(user_id):
            return [Out("toast", "⛔ فقط مالک")]
        try:
            return self._cb(m, parts)
        except Exception as e:      # دکمه هرگز بی‌صدا شکست نخورد
            return [Out("toast", f"خطا: {e}")]

    def _cb_pick(self, user_id, chat_id, round_id, victim_id, now):
        eng = self.eng
        outs = self.on_tick(now)
        w = eng.winner_player()
        if eng.phase != "picking" or eng.db.get("current_round_id") != round_id:
            return outs + [Out("toast", "این انتخاب دیگر معتبر نیست.")]
        if not (self.is_owner(user_id) or (w and w["tg_user_id"] == user_id)):
            return outs + [Out("toast", "فقط برنده‌ی دور (یا مالک) می‌تواند انتخاب کند.")]
        res = self._do_pick(None, round_id, victim_id)
        return outs + res + [Out("toast", "انتخاب ثبت شد ✅")]

    def _edit(self, text, kb=None):
        return Out("edit", text, "here", kb)

    def _cb(self, m, p):
        eng, k = self.eng, p[0]
        if k == "cf":
            return self._confirm(m, p[1] == "yes")
        if k == "wz":
            return self._cb_wizard(m, p)
        if k == "menu":
            return self._cb_menu(m, p[1])
        if k == "td":
            if p[1] == "list":
                custom = [t for t in self.bank.list_topics() if not t["builtin"]]
                if not custom:
                    return [Out("toast", "موضوع اضافه‌شده‌ای برای حذف نیست (۱۰ موضوع اصلی دائمی‌اند).")]
                return [self._edit("🗑 کدام موضوع حذف شود؟", kb_rows([(t["name"], f"td:{t['id']}") for t in custom]) + [BACK])]
            t = self.bank.get_topic(int(p[1]))
            return self.c_topic_del(m, t["name"]) if t else [Out("toast", "پیدا نشد")]
        if k == "ta":
            self.db.set("await", {"kind": "topic_add"})
            return self._say(m, "➕ نام موضوع جدید را بفرست (یا لغو).")
        if k == "pa":
            self.db.set("await", {"kind": "players_add"})
            return self._say(m, "➕ نام بازیکن(ها) را بفرست؛ هر نام در یک خط (یا لغو).")
        if k == "pd":
            pl = eng.players.get(int(p[1]))
            return self.c_player_remove(m, pl["name"]) if pl else [Out("toast", "پیدا نشد")]
        if k == "hp":
            pl = eng.players.get(int(p[1]))
            if not pl:
                return [Out("toast", "پیدا نشد")]
            d = int(p[2])
            if d == 0:
                return [Out("toast", f"{pl['name']}: {pl['hearts']} قلب")]
            outs = self._hearts(m, pl["name"], delta=d)
            return outs + [self._edit(*self._hearts_menu())]
        if k == "tm":
            if p[1] == "custom":
                self.db.set("await", {"kind": "timer"})
                return self._say(m, "⏱ طول تایمر را به ثانیه بفرست (مثلاً ۱۵).")
            if p[1] == "stop":
                return self.c_timer_stop(m)
            if p[1] == "resume":
                return self.c_timer_resume(m)
            return self.c_timer_start(m, p[1])
        if k == "pz":
            if p[1] == "set":
                self.db.set("await", {"kind": "prizes"})
                return self._say(m, "🎁 جایزه‌ها را بفرست؛ هر جایزه در یک خط، به ترتیب رتبه ۱، ۲، ۳…\nمثال:\n۱۰۰۰ افغانی\nکارت شارژ\nیک تبریک گرم")
            if p[1] == "preview":
                return self._say(m, "👁 جایزه‌ها:\n" + ("\n".join(eng.prizes.lines()) or "ثبت نشده") + f"\n🏆 تعداد برندگان: {fa(eng.prizes.winners_count())}" +
                                 (f"\n{eng.prizes.warning()}" if eng.prizes.warning() else ""))
            return self.c_announce(m)
        if k == "bn":
            if p[1] == "recreate":
                return [Out("banner", final=True)]
            return {"edit": self.c_banner_edit, "show": self.c_banner_show, "ok": self.c_banner_ok,
                    "update": self.c_banner_update, "reset": self.c_banner_reset}[p[1]](m)
        if k == "set":
            if p[1] == "stop":
                return self.c_stop_game(m)
            if p[1] == "resume":
                return self.c_resume_game(m)
            if p[1] == "gid":
                return self.c_group_id(m)
        if k == "hl":
            return self._say(m, HELP.get(p[1], HELP["کل"]))
        return [Out("toast", "؟")]

    def _hearts_menu(self):
        act = self.eng.players.active()
        if not act:
            return "❤️ بازیکن فعالی نیست.", [BACK]
        rows = [[(f"{p['name']} {fa(p['hearts'])}❤️", f"hp:{p['id']}:0"), ("➖", f"hp:{p['id']}:-1"), ("➕", f"hp:{p['id']}:1")] for p in act]
        return "❤️ مدیریت قلب‌ها — با ➖ و ➕ قلب بازیکن را عوض کن:", rows + [BACK]

    def _cb_menu(self, m, name):
        eng = self.eng
        if name == "main":
            return [self._edit(PANEL, self._panel()[0].kb)]
        if name == "new":
            return self._wizard_start(m)
        if name == "topics":
            lines = ["📚 موضوعات:"]
            for t in self.bank.list_topics():
                lines.append(f"• {t['name']} ({fa(t['n'])})")
            return [self._edit("\n".join(lines), [[("➕ افزودن موضوع", "ta"), ("🗑 حذف موضوع", "td:list")], BACK])]
        if name == "players":
            act = eng.players.active()
            rows = [[(f"🗑 {p['name']}", f"pd:{p['id']}")] for p in act]
            return [self._edit(self.players_text() + "\n\nبا 🗑 بازیکن را از بازی حذف کن.", rows + [[("➕ افزودن بازیکن", "pa")], BACK])]
        if name == "hearts":
            return [self._edit(*self._hearts_menu())]
        if name == "timer":
            s = eng.summary()
            b = [(f"{fa(n)} ثانیه", f"tm:{n}") for n in (5, 10, 15, 20, 30)] + [("✏️ عدد دلخواه", "tm:custom")]
            return [self._edit(f"⏱ طول تایمر فعلی: {fa(s['timer_len'])} ثانیه (+۳ ثانیه مکث قبل از شمارش)",
                               kb_rows(b, 3) + [[("⏸ توقف تایمر", "tm:stop"), ("▶️ ادامه تایمر", "tm:resume")], BACK])]
        if name == "prizes":
            lines = eng.prizes.lines() or ["هنوز جایزه‌ای ثبت نشده."]
            return [self._edit("🎁 جایزه‌ها:\n" + "\n".join(lines) + f"\n🏆 تعداد برندگان: {fa(eng.prizes.winners_count())}",
                               [[("✏️ تنظیم جایزه‌ها", "pz:set"), ("👁 پیش‌نمایش", "pz:preview")], [("🏆 اعلام برندگان", "pz:announce")], BACK])]
        if name == "banner":
            return [self._edit("🖼 مدیریت بنر پین‌شده", [[("✏️ ویرایش بنر", "bn:edit"), ("👁 نمایش پیش‌نمایش", "bn:show")],
                                                          [("✅ تأیید بنر", "bn:ok"), ("🔄 به‌روزرسانی بنر", "bn:update")],
                                                          [("♻️ بنر پیش‌فرض", "bn:reset")], BACK])]
        if name == "status":
            return [self._edit(self.status_text(), [[("🔄 تازه‌سازی", "menu:status")], BACK])]
        if name == "help":
            b = [(k, f"hl:{k}") for k in HELP_ORDER]
            return [self._edit(HELP["کل"], kb_rows(b, 3) + [BACK])]
        if name == "clear":
            return self.c_cleanup(m)
        if name == "end":
            return self.c_end_game(m)
        if name == "settings":
            return [self._edit(f"⚙️ تنظیمات بازی\n⏱ تایمر فعلی: {fa(eng.timer_len)} ثانیه\n🆔 گروه: {self.group_id or 'ثبت نشده'}",
                               [[("⏸ توقف بازی", "set:stop"), ("▶️ ادامه بازی", "set:resume")],
                                [("⏱ تنظیم تایمر", "menu:timer"), ("🆔 شناسه گروه", "set:gid")], BACK])]
        return [Out("toast", "؟")]

    def _cb_wizard(self, m, p):
        wz = self.db.get("wizard")
        if p[1] == "cancel":
            self.db.delete("wizard")
            return [self._edit("❌ ساخت بازی لغو شد.", [BACK])]
        if p[1] == "t":
            if self.eng.status in ("running", "paused"):
                return [Out("toast", "بازی در جریان است.")]
            self.db.set("wizard", {"step": "players", "topic_id": int(p[2])})
            t = self.bank.get_topic(int(p[2]))
            return [self._edit(f"✅ موضوع: {t['name']}\n\n👥 مرحله ۲ از ۵: نام بازیکن‌ها را در یک پیام بفرست؛ هر نام در یک خط (حداقل ۳ نفر).\nمثال:\nنوید\nرحیم\nآرش")]
        if not wz:
            return [Out("toast", "ساخت بازی فعال نیست.")]
        if p[1] == "prizes":
            if wz["step"] != "prizes":
                return [Out("toast", "این مرحله گذشته.")]
            if p[2] == "set":
                wz["step"] = "prizes_text"
                self.db.set("wizard", wz)
                return [self._edit("🎁 جایزه‌ها را بفرست؛ هر جایزه در یک خط، به ترتیب رتبه ۱، ۲، ۳…")]
            wz["step"] = "confirm"
            self.db.set("wizard", wz)
            return self._wizard_confirm_out()
        if p[1] == "back":
            self.db.set("wizard", {"step": "topic"})
            return self._wizard_topic_prompt()
        if p[1] == "ok":
            return self._wizard_go()
        return [Out("toast", "؟")]
