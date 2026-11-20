# -*- coding: utf-8 -*-
"""ساخت متن بنر اصلی بازی."""

DEFAULT_HEADER = ("🏛 گروه چتکده هراتی‌ها\n"
                  "🎮 آخرین واژه\n"
                  "🌵 تیم کاکتوس\n"
                  "👑 مالک ربات: Cactuc ⎊ نــــوید")
LINE = "━━━━━━━━━━━━━━"


def hearts_str(n):
    return "❤️" * n if n <= 7 else f"❤️×{n}"


def status_line(engine):
    s = engine.status
    if s == "idle":
        return "⚪ بازی فعلاً شروع نشده"
    if s == "finished":
        return "🏁 بازی تمام شد"
    base = f"دور {engine.round_no}"
    if engine.tiebreak:
        base = "🔥 دور تعیین تکلیف"
    if s == "paused":
        return f"⏸ بازی متوقف است — {base}"
    if engine.phase == "picking":
        w = engine.winner_player()
        return f"🎯 برنده دور: {w['name'] if w else '—'} — در انتظار انتخاب"
    ts = engine.timer_state
    if ts == "paused":
        return f"⏳ تایمر متوقف است — {base}"
    return f"🟢 در حال بازی — {base} — تایمر {engine.timer_len} ثانیه"


def render(db, engine):
    header = db.get("banner_header") or DEFAULT_HEADER
    lines = [header, LINE]
    topic = engine.topic_name()
    lines.append(f"📚 موضوع: {topic or '—'}")
    players = engine.players
    if engine.status == "finished":
        ranking = db.get("ranking") or []
        lines.append("")
        lines.append("🏆 رتبه‌بندی نهایی:")
        for r in ranking:
            lines.append(f"{r['rank']}. {r['name']} — {hearts_str(r['hearts']) if r['hearts'] else '💀'}")
    else:
        act = players.active()
        lines.append("")
        lines.append(f"👥 بازیکنان فعال ({len(act)}):")
        if not act:
            lines.append("—")
        for i, p in enumerate(act, 1):
            lines.append(f"{i}. {p['name']} {hearts_str(p['hearts'])}")
        out = players.eliminated()
        if out:
            lines.append("")
            lines.append("💀 حذف‌شده‌ها: " + "، ".join(p["name"] for p in out))
    prizes = engine.prizes.lines()
    if prizes:
        lines.append("")
        lines.append("🎁 جایزه‌ها:")
        lines.extend(prizes)
    lines.append(LINE)
    lines.append(status_line(engine))
    return "\n".join(lines)
