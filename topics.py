# -*- coding: utf-8 -*-
"""موضوعات و بانک جواب‌ها."""
import json
import os

from answers import normalize, clean_display

SEED_VERSION = 1
DEFAULT_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "topics.json")


class Bank:
    def __init__(self, db):
        self.db = db

    # ---------- بذر اولیه
    def seed(self, path=DEFAULT_DATA):
        if self.db.get("seed_version", 0) >= SEED_VERSION:
            return False
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for t in data["topics"]:
            tid = self.ensure_topic(t["name"], builtin=True)
            for group in t["answers"]:
                self.add_answer(tid, " / ".join(group))
        self.db.set("seed_version", SEED_VERSION)
        return True

    # ---------- موضوعات
    def ensure_topic(self, name, builtin=False):
        row = self.find_topic(name)
        if row:
            return row["id"]
        cur = self.db.ex("INSERT INTO topics(name,norm,builtin) VALUES(?,?,?)",
                         (clean_display(name), normalize(name), 1 if builtin else 0))
        return cur.lastrowid

    def list_topics(self):
        return self.db.q("SELECT t.*, (SELECT COUNT(*) FROM answers a WHERE a.topic_id=t.id) AS n FROM topics t ORDER BY id")

    def get_topic(self, tid):
        return self.db.one("SELECT * FROM topics WHERE id=?", (tid,))

    def find_topic(self, name):
        n = normalize(name)
        if not n:
            return None
        r = self.db.one("SELECT * FROM topics WHERE norm=?", (n,))
        if r:
            return r
        if n.startswith("موضوع"):
            r = self.db.one("SELECT * FROM topics WHERE norm=?", (n[5:],))
            if r:
                return r
        # تطبیق نرم: «ورزش» ↔ «ورزش‌ها»، «غذا» ↔ «غذاها»، «میوه» ↔ «میوه‌ها»
        rows = self.db.q("SELECT * FROM topics")
        cands = [x for x in rows if x["norm"].startswith(n) or n.startswith(x["norm"])]
        cands = [x for x in cands if abs(len(x["norm"]) - len(n)) <= 3]
        if len(cands) == 1:
            return cands[0]
        # «وسایل نقلیه» ↔ «نقلیه»
        cands = [x for x in rows if len(n) >= 4 and (n in x["norm"] or x["norm"] in n)]
        return cands[0] if len(cands) == 1 else None

    def add_topic(self, name):
        if self.find_topic(name) and self.find_topic(name)["norm"] == normalize(name):
            return None
        return self.ensure_topic(name, builtin=False)

    def remove_topic(self, tid):
        t = self.get_topic(tid)
        if not t or t["builtin"]:
            return False
        self.db.ex("DELETE FROM forms WHERE topic_id=?", (tid,))
        self.db.ex("DELETE FROM answers WHERE topic_id=?", (tid,))
        self.db.ex("DELETE FROM topics WHERE id=?", (tid,))
        return True

    # ---------- جواب‌ها
    def lookup(self, tid, raw):
        n = normalize(raw)
        if not n:
            return None
        r = self.db.one("SELECT answer_id FROM forms WHERE topic_id=? AND norm=?", (tid, n))
        return r["answer_id"] if r else None

    def canonical(self, answer_id):
        r = self.db.one("SELECT canonical FROM answers WHERE id=?", (answer_id,))
        return r["canonical"] if r else None

    def add_answer(self, tid, text):
        """text می‌تواند «الف / ب / ج» باشد (الف = نام اصلی، بقیه مترادف).
        خروجی: (answer_id, 'new'|'exists'|'merged')"""
        parts = [clean_display(p) for p in text.split("/") if normalize(p)]
        if not parts:
            return None, "empty"
        existing = [self.lookup(tid, p) for p in parts]
        ids = [i for i in existing if i]
        if ids:
            aid = ids[0]
            status = "exists"
        else:
            cur = self.db.ex("INSERT INTO answers(topic_id,canonical) VALUES(?,?)", (tid, parts[0]))
            aid = cur.lastrowid
            status = "new"
        for p in parts:
            if not self.lookup(tid, p):
                self.db.ex("INSERT INTO forms(answer_id,topic_id,text,norm) VALUES(?,?,?,?)",
                           (aid, tid, p, normalize(p)))
                if status == "exists":
                    status = "merged"
        return aid, status

    def remove_answer(self, tid, raw):
        aid = self.lookup(tid, raw)
        if not aid:
            return False
        self.db.ex("DELETE FROM forms WHERE answer_id=?", (aid,))
        self.db.ex("DELETE FROM answers WHERE id=?", (aid,))
        return True

    def forms_of(self, answer_id):
        return [r["text"] for r in self.db.q("SELECT text FROM forms WHERE answer_id=?", (answer_id,))]
