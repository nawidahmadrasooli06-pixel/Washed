# -*- coding: utf-8 -*-
"""تبدیل متن فارسی فرمان‌های مالک به (نام فرمان، آرگومان‌ها). مستقل از تلگرام."""
import re
import unicodedata

Z = r"[\s\u200c]*"


def _w(*parts):
    return Z.join(parts)


_LIGHT = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})
_DIG = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _clean(text):
    t = unicodedata.normalize("NFC", text or "").translate(_LIGHT)
    t = t.replace("\u200f", "").replace("\u200e", "")
    t = re.sub(r"[ \t\u00a0]+", " ", t).strip()
    return t.rstrip(".!؟?،")


_P = [
    ("start_game", rf"{_w('شروع','بازی')}(?:{Z}جدید)?"),
    ("stop_game", _w("توقف", "بازی")),
    ("resume_game", _w("ادامه", "بازی")),
    ("end_game", _w("پایان", "بازی")),
    ("status_game", _w("وضعیت", "بازی")),
    ("timer_start", rf"{_w('شروع','تایمر')}(?:\s+(\d+))?"),
    ("timer_stop", _w("توقف", "تایمر")),
    ("timer_resume", _w("ادامه", "تایمر")),
    ("players_status", _w("وضعیت", "بازیکنان")),
    ("player_add", rf"{_w('افزودن','بازیکن')}\s+(.+?)(?:\s+به\s+بازی)?(?:\s+با\s+(\d+)\s+قلب)?"),
    ("player_remove", r"حذف\s+(.+?)\s+از\s+بازی"),
    ("heart_sub", rf"{_w('کم','کردن')}\s+(?:(\d+)\s+|یک\s+)?قلب\s+از\s+(.+)"),
    ("heart_add", rf"{_w('اضافه','کردن')}\s+(?:(\d+)\s+|یک\s+)?قلب\s+(?:به|از)\s+(.+)"),
    ("heart_set", r"تنظیم\s+قلب\s+(.+?)\s+روی\s+(\d+)"),
    ("topic_add", rf"{_w('افزودن','موضوع')}(?:{Z}جدید)?\s*[:：]\s*(.+)"),
    ("topic_del", rf"{_w('حذف','موضوع')}\s*[:：]\s*(.+)"),
    ("topic_change", rf"{_w('تغییر','موضوع')}\s*[:：]\s*(.+)"),
    ("topics_list", _w("فهرست", "موضوعات")),
    ("prize_set", rf"(?:تغییر|ویرایش){Z}جایزه(?:\s*(\d+))?\s*[:：]\s*(.+)"),
    ("prize_del", rf"حذف{Z}جایزه\s*(\d+)"),
    ("winners_count", rf"{_w('تعداد','برندگان')}(?:\s*[:：]?\s*(\d+))?"),
    ("prizes_count", rf"{_w('تعداد','جایزه','ها')}(?:\s*[:：]?\s*(\d+))?"),
    ("announce", _w("اعلام", "برندگان")),
    ("banner_edit", _w("ویرایش", "بنر")),
    ("banner_show", _w("نمایش", "بنر")),
    ("banner_update", _w("به", "روزرسانی", "بنر")),
    ("banner_ok", _w("ت[أا]یید", "بنر")),
    ("banner_reset", _w("بنر", "پیش", "فرض")),
    ("help", rf"راهنما(?:ی{Z}(بازی|بازیکنان|تایمر|قلب{Z}ها|موضوعات|جایزه{Z}ها|بنر))?"),
    ("cleanup", _w("پاک", "سازی", "بازیکنان")),
    ("confirm_yes", r"(?:ت[أا]یید|بله|آره|اره)"),
    ("confirm_no", r"(?:لغو|نه|خیر)"),
    ("group_id", rf"(?:{_w('شناسه','گروه')}|{_w('ثبت','گروه')})"),
    ("link", r"ربط(?:\s+(.+))?"),
    ("pick", r"انتخاب\s+(.+)"),
    ("verdict", r"(?:(.+?)\s+)?(قبول|رد)"),
    # آخرین‌ها (عمومی‌تر)
    ("bank_add", r"افزودن\s+(.+)\s+به\s+(.+)"),
    ("bank_del", r"حذف\s+(.+)\s+از\s+(.+)"),
]
_COMPILED = [(n, re.compile(p, re.S)) for n, p in _P]

# اگر متن با این کلمه‌ها شروع شود ولی هیچ الگویی نخورد، «فرمان اشتباه» حساب می‌شود
HINT_VERBS = ("افزودن", "حذف", "کم", "اضافه", "تنظیم", "شروع", "توقف", "ادامه", "پایان", "وضعیت", "راهنما",
              "تغییر", "ویرایش", "نمایش", "پاک", "تعداد", "اعلام", "فهرست", "انتخاب", "ربط")


def parse(text):
    """خروجی: (cmd, args) | ('invalid', verb) | None"""
    t = _clean(text)
    if not t:
        return None
    for name, rx in _COMPILED:
        m = rx.fullmatch(t)
        if m:
            return name, tuple(g.strip() if isinstance(g, str) else g for g in m.groups())
    first = t.split(" ")[0]
    if first in HINT_VERBS:
        return "invalid", (first,)
    return None
