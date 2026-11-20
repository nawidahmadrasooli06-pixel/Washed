# -*- coding: utf-8 -*-
"""بازیکنان و قلب‌ها."""
import time
from answers import normalize, clean_display


class Players:
    def __init__(self, db, clock=time.time):
        self.db = db
        self.clock = clock

    def get(self, pid):
        return self.db.one("SELECT * FROM players WHERE id=?", (pid,))

    def visible(self):
        return self.db.q("SELECT * FROM players WHERE removed=0 ORDER BY id")

    def active(self):
        return self.db.q("SELECT * FROM players WHERE active=1 AND removed=0 ORDER BY id")

    def eliminated(self):
        return self.db.q("SELECT * FROM players WHERE active=0 AND removed=0 ORDER BY elim_order")

    def find(self, name):
        """جستجوی بازیکن با نام. خروجی: (بازیکن|None، فهرست گزینه‌ها)"""
        n = normalize(name)
        if not n:
            return None, []
        rows = self.visible()
        exact = [r for r in rows if r["norm"] == n]
        if len(exact) == 1:
            return exact[0], []
        part = [r for r in rows if n in r["norm"] or (len(r["norm"]) >= 3 and r["norm"] in n)]
        if len(part) == 1:
            return part[0], []
        return None, (exact or part)

    def _next_elim(self):
        r = self.db.one("SELECT COALESCE(MAX(elim_order),0)+1 AS n FROM players")
        return r["n"]

    def add(self, name, hearts):
        """خروجی: (status, player)  status: added|duplicate|reactivated|invalid"""
        name = clean_display(name)
        n = normalize(name)
        if not n:
            return "invalid", None
        row = self.db.one("SELECT * FROM players WHERE norm=? AND removed=0", (n,))
        if row and row["active"]:
            return "duplicate", row
        if row and not row["active"]:
            self.db.ex("UPDATE players SET active=1, hearts=?, elim_order=NULL WHERE id=?", (hearts, row["id"]))
            self.log(row["id"], hearts, hearts, "بازگشت به بازی")
            return "reactivated", self.get(row["id"])
        old = self.db.one("SELECT * FROM players WHERE norm=? AND removed=1", (n,))
        if old:
            self.db.ex("UPDATE players SET removed=0, active=1, hearts=?, initial_hearts=?, elim_order=NULL WHERE id=?",
                       (hearts, hearts, old["id"]))
            self.log(old["id"], hearts, hearts, "افزودن مجدد")
            return "added", self.get(old["id"])
        cur = self.db.ex("INSERT INTO players(name,norm,hearts,initial_hearts,active,removed,added_at) VALUES(?,?,?,?,1,0,?)",
                         (name, n, hearts, hearts, self.clock()))
        self.log(cur.lastrowid, hearts, hearts, "ثبت اولیه")
        return "added", self.get(cur.lastrowid)

    def log(self, pid, delta, after, reason):
        self.db.ex("INSERT INTO heart_log(player_id,delta,hearts_after,reason,ts) VALUES(?,?,?,?,?)",
                   (pid, delta, after, reason, self.clock()))

    def set_hearts(self, pid, value, reason=""):
        """تنظیم قلب. منفی→۰. خروجی: dict(hearts, eliminated, clamped)"""
        p = self.get(pid)
        clamped = value < 0
        value = max(0, int(value))
        self.db.ex("UPDATE players SET hearts=? WHERE id=?", (value, pid))
        self.log(pid, value - p["hearts"], value, reason)
        eliminated = False
        if value == 0 and p["active"]:
            self.db.ex("UPDATE players SET active=0, elim_order=? WHERE id=?", (self._next_elim(), pid))
            eliminated = True
        elif value > 0 and not p["active"]:
            self.db.ex("UPDATE players SET active=1, elim_order=NULL WHERE id=?", (pid,))
        return {"hearts": value, "eliminated": eliminated, "clamped": clamped}

    def remove(self, pid):
        self.db.ex("UPDATE players SET active=0, removed=1 WHERE id=?", (pid,))
        self.log(pid, 0, 0, "حذف توسط مالک")

    def link(self, pid, tg_user_id):
        self.db.ex("UPDATE players SET tg_user_id=? WHERE id=?", (tg_user_id, pid))

    def by_tg(self, tg_user_id):
        return self.db.one("SELECT * FROM players WHERE tg_user_id=? AND removed=0", (tg_user_id,))

    def match_sender(self, tg_user_id, names):
        """تشخیص بازیکن از روی فرستنده: ابتدا شناسه ذخیره‌شده، بعد تطبیق نام."""
        p = self.by_tg(tg_user_id)
        if p:
            return p
        norms = [normalize(x) for x in names if x and normalize(x)]
        rows = [r for r in self.visible() if not r["tg_user_id"]]
        for r in rows:
            if r["norm"] in norms:
                self.link(r["id"], tg_user_id)
                return self.get(r["id"])
        hits = [r for r in rows if len(r["norm"]) >= 3 and any(r["norm"] in n for n in norms)]
        if len(hits) == 1:
            self.link(hits[0]["id"], tg_user_id)
            return self.get(hits[0]["id"])
        return None

    def wipe(self):
        for t in ("players", "history", "pending", "rounds", "heart_log"):
            self.db.ex(f"DELETE FROM {t}")
