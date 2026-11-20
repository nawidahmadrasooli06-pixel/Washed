# -*- coding: utf-8 -*-
"""تبدیل دکمه‌های کنترلر به دکمه‌های شیشه‌ای تلگرام."""


def to_markup(kb):
    if not kb:
        return None
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data) for label, data in row] for row in kb])
