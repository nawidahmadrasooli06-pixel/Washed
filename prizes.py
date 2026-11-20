# -*- coding: utf-8 -*-
"""جایزه‌ها و اعلام برندگان."""


class Prizes:
    def __init__(self, db):
        self.db = db

    def all(self):
        return self.db.q("SELECT * FROM prizes ORDER BY rank")

    def count(self):
        return len(self.all())

    def winners_count(self):
        v = self.db.get("winners_count")
        return v if v is not None else self.count()

    def set_winners_count(self, n):
        self.db.set("winners_count", int(n))

    def set(self, rank, name):
        self.db.ex("INSERT INTO prizes(rank,name) VALUES(?,?) ON CONFLICT(rank) DO UPDATE SET name=excluded.name",
                   (rank, name.strip()))

    def append(self, name):
        r = self.db.one("SELECT COALESCE(MAX(rank),0)+1 AS n FROM prizes")["n"]
        self.set(r, name)
        return r

    def delete(self, rank):
        if not self.db.one("SELECT 1 FROM prizes WHERE rank=?", (rank,)):
            return False
        self.db.ex("DELETE FROM prizes WHERE rank=?", (rank,))
        rows = self.db.q("SELECT * FROM prizes WHERE rank>? ORDER BY rank", (rank,))
        for r in rows:  # شماره‌ها پشت سر هم بمانند
            self.db.ex("UPDATE prizes SET rank=? WHERE rank=?", (r["rank"] - 1, r["rank"]))
        return True

    def set_count(self, n):
        """تعداد جایزه‌ها: اضافه‌ها حذف می‌شوند؛ کمبود باید با «تغییر جایزه» پر شود."""
        self.db.ex("DELETE FROM prizes WHERE rank>?", (n,))

    def replace_all(self, names):
        self.db.ex("DELETE FROM prizes")
        for i, n in enumerate(names, 1):
            self.set(i, n)
        self.set_winners_count(len(names))

    def prize_for(self, rank):
        r = self.db.one("SELECT name FROM prizes WHERE rank=?", (rank,))
        return r["name"] if r else None

    def warning(self):
        w, c = self.winners_count(), self.count()
        if w != c:
            return f"⚠️ تعداد برندگان ({w}) با تعداد جایزه‌ها ({c}) برابر نیست."
        return None

    def lines(self):
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        return [f"{medals.get(r['rank'], '🏅')} رتبه {r['rank']}: {r['name']}" for r in self.all()]
