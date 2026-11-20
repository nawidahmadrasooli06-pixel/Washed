# -*- coding: utf-8 -*-
"""نرمال‌سازی و تشخیص جواب."""
import re
import unicodedata

_MAP = str.maketrans({
    "ي": "ی", "ى": "ی", "ې": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "ە": "ه",
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ؤ": "و", "ئ": "ی",
})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def unify(text: str) -> str:
    """یکسان‌سازی حروف و ارقام (نیم‌فاصله حفظ می‌شود)."""
    text = unicodedata.normalize("NFKC", text or "")
    return text.translate(_MAP).translate(_DIGITS)


def normalize(text: str) -> str:
    """کلید مقایسه: بدون فاصله/نیم‌فاصله/اعراب/علائم، حروف عربی→فارسی، انگلیسی کوچک."""
    text = unify(text).casefold()
    return "".join(ch for ch in text if ch.isalnum() and ch != "\u0640")


def clean_display(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def looks_like_answer(text: str) -> bool:
    """آیا این پیام می‌تواند یک جواب بازی باشد؟ (نه گپ طولانی/لینک/فرمان)"""
    t = clean_display(text)
    if not t or len(t) > 30 or t.startswith("/") or "http" in t.lower() or "@" in t:
        return False
    if len(t.split(" ")) > 4:
        return False
    return any(ch.isalpha() for ch in t)
