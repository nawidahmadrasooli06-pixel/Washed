# -*- coding: utf-8 -*-
"""منطق اصلی بازی «آخرین واژه» (مستقل از تلگرام، قابل تست)."""
import math
import time

from answers import normalize, clean_display
from players import Players
from prizes import Prizes

PAUSE_BEFORE = 3      # مکث کوتاه قبل از شروع شمارش (ثانیه)
LATE_TOLERANCE = 0.7  # تحمل تأخیر شبکه (ثانیه)
DEFAULT_TIMER = 10


class Engine:
    def __init__(self, db, bank, clock=time.time):
        self.db, self.bank, self.clock = db, bank, clock
        self.players = Players(db, clock)
        self.prizes = Prizes(db)

    # ---------- وضعیت
    @property
    def status(self):
        return self.db.get("status", "idle")

    @property
    def phase(self):
        return self.db.get("phase", "answering")

    @property
    def topic_id(self):
        return self.db.get("topic_id")

    @property
    def round_no(self):
        return self.db.get("round_no", 0)

    @property
    def timer_len(self):
        return self.db.get("timer_len", DEFAULT_TIMER)

    @property
    def timer_state(self):
        return self.db.get("timer_state", "none")

    @property
    def tiebreak(self):
        return self.db.get("tiebreak", 0)

    def topic_name(self):
        t = self.bank.get_topic(self.topic_id) if self.topic_id else None
        return t["name"] if t else None

    # ---------- شروع و پایان
    def start_game(self, topic_id, names, hearts):
        if self.status in ("running", "paused"):
            return {"ok": False, "error": "game_running"}
        if not self.bank.get_topic(topic_id):
            return {"ok": False, "error": "no_topic"}
        if hearts < 1:
            return {"ok": False, "error": "bad_hearts"}
        self.players.wipe()
        added, dups = [], []
        for nm in names:
            st, p = self.players.add(nm, hearts)
            if st == "added":
                added.append(p["name"])
            elif st == "duplicate":
                dups.append(clean_display(nm))
        if len(added) < 3:
            self.players.wipe()
            return {"ok": False, "error": "few_players", "dups": dups}
        for k, v in dict(status="running", phase="answering", round_no=1, tiebreak=0, topic_id=topic_id,
                         timer_state="none", timer_game_paused=0, timer_pending_pause=0,
                         round_winner_id=None, current_round_id=None, ranking=None).items():
            self.db.set(k, v)
        self.db.set("init_hearts", hearts)
        return {"ok": True, "added": added, "dups": dups}

    def clear(self):
        """پاک‌سازی بازیکنان و داده‌های بازی؛ موضوعات/بانک/جایزه‌ها/بنر دست‌نخورده می‌مانند."""
        self.players.wipe()
        for k, v in dict(status="idle", phase="answering", round_no=0, tiebreak=0, topic_id=None,
                         timer_state="none", timer_game_paused=0, timer_pending_pause=0,
                         round_winner_id=None, current_round_id=None, ranking=None).items():
            self.db.set(k, v)
        for k in ("timer_end", "grace_end", "timer_rem", "grace_rem", "wizard", "await", "pending_confirm",
                  "countdown_msg_id", "cd_last", "pick_msg_id"):
            self.db.delete(k)

    def pause_game(self):
        if self.status != "running":
            return False
        if self.timer_state == "running":
            self._freeze_timer()
            self.db.set("timer_game_paused", 1)
        self.db.set("status", "paused")
        return True

    def resume_game(self):
        if self.status != "paused":
            return False
        self.db.set("status", "running")
        if self.db.get("timer_game_paused") and self.timer_state == "paused":
            self._unfreeze_timer()
        self.db.set("timer_game_paused", 0)
        return True

    def finish(self, first_pid=None, manual=False):
        ranking = self._ranking(first_pid, manual)
        self.db.set("ranking", ranking)
        self.db.set("status", "finished")
        self.db.set("phase", "done")
        self.db.set("timer_state", "none")
        return ranking

    def _ranking(self, first_pid=None, manual=False):
        act = sorted(self.players.active(), key=lambda p: -p["hearts"])
        if first_pid:
            act = [p for p in act if p["id"] == first_pid] + [p for p in act if p["id"] != first_pid]
        elim = sorted(self.players.eliminated(), key=lambda p: -p["elim_order"])
        out = []
        for i, p in enumerate(act + elim, 1):
            tie = False
            if p["active"] and not first_pid:
                tie = any(q["id"] != p["id"] and q["hearts"] == p["hearts"] for q in act)
            out.append({"rank": i, "id": p["id"], "name": p["name"], "hearts": p["hearts"], "tie": tie})
        return out

    # ---------- تایمر
    def _start_timer(self):
        now = self.clock()
        self.db.set("timer_pending_pause", 0)
        if self.timer_state == "paused":      # تایمر دستی متوقف است: فقط زمان باقی‌مانده تازه می‌شود
            self.db.set("timer_rem", PAUSE_BEFORE + self.timer_len)
            self.db.set("grace_rem", PAUSE_BEFORE)
            return
        self.db.set("grace_end", now + PAUSE_BEFORE)
        self.db.set("timer_end", now + PAUSE_BEFORE + self.timer_len)
        self.db.set("timer_state", "running")
        self.db.delete("cd_last")

    def _freeze_timer(self):
        now = self.clock()
        self.db.set("timer_rem", max(0.0, self.db.get("timer_end", now) - now))
        self.db.set("grace_rem", max(0.0, self.db.get("grace_end", now) - now))
        self.db.set("timer_state", "paused")

    def _unfreeze_timer(self):
        now = self.clock()
        self.db.set("timer_end", now + self.db.get("timer_rem", self.timer_len))
        self.db.set("grace_end", now + self.db.get("grace_rem", 0))
        self.db.set("timer_state", "running")
        self.db.delete("cd_last")

    def pause_timer(self):
        if self.timer_state != "running":
            return False
        self._freeze_timer()
        return True

    def resume_timer(self):
        if self.status != "running":
            return "game_paused"
        if self.timer_state != "paused":
            return "not_paused"
        if self.open_pending():
            return "pending_open"
        self._unfreeze_timer()
        self.db.set("timer_pending_pause", 0)
        return "ok"

    def set_timer_len(self, n):
        self.db.set("timer_len", int(n))

    def restart_timer(self):
        """شروع دوباره شمارش با طول فعلی (فقط اگر آخرین جواب معتبری هست)."""
        if self.status != "running" or self.phase != "answering" or not self._latest_valid():
            return False
        self._start_timer()
        return True

    def remaining(self):
        if self.timer_state == "running":
            return max(0.0, self.db.get("timer_end") - self.clock())
        if self.timer_state == "paused":
            return self.db.get("timer_rem", 0)
        return None

    def tick(self, now=None):
        """باید هر ~۰٫۵ ثانیه صدا زده شود. خروجی: فهرست رویدادها."""
        now = self.clock() if now is None else now
        ev = []
        if self.status != "running" or self.phase != "answering" or self.timer_state != "running":
            return ev
        end = self.db.get("timer_end")
        if now >= end + LATE_TOLERANCE:
            last = self._latest_valid()
            self.db.set("timer_state", "none")
            if not last:
                return [{"type": "no_winner"}]
            winner = self.players.get(last["player_id"])
            cur = self.db.ex("INSERT INTO rounds(round_no,winner_id,ts) VALUES(?,?,?)",
                             (self.round_no, winner["id"], now))
            self.db.set("current_round_id", cur.lastrowid)
            self.db.set("round_winner_id", winner["id"])
            if self.tiebreak:
                ranking = self.finish(first_pid=winner["id"])
                return [{"type": "round_end", "winner": winner, "round_id": cur.lastrowid, "final": True},
                        {"type": "finished", "ranking": ranking}]
            self.db.set("phase", "picking")
            return [{"type": "round_end", "winner": winner, "round_id": cur.lastrowid, "final": False}]
        if now >= self.db.get("grace_end", end):
            sec = max(0, math.ceil(end - now))
            if self.db.get("cd_last") != sec:
                self.db.set("cd_last", sec)
                ev.append({"type": "countdown", "sec": sec})
        return ev

    # ---------- جواب‌ها
    def used(self, answer_id):
        return self.db.one("SELECT 1 FROM history WHERE answer_id=? AND status='valid'", (answer_id,)) is not None

    def _latest_valid(self):
        rows = self.db.q("SELECT h.* FROM history h JOIN players p ON p.id=h.player_id "
                         "WHERE h.status='valid' AND h.round_no=? AND p.active=1 ORDER BY h.id DESC LIMIT 1",
                         (self.round_no,))
        return rows[0] if rows else None

    def last_answerer(self):
        h = self._latest_valid()
        return self.players.get(h["player_id"]) if h else None

    def open_pending(self):
        return self.db.q("SELECT * FROM pending WHERE status='open' ORDER BY id")

    def process_answer(self, player, raw, chat_id=None, message_id=None):
        if self.status != "running" or self.phase != "answering" or not player or not player["active"]:
            return {"kind": "ignored"}
        aid = self.bank.lookup(self.topic_id, raw)
        if aid is None:
            return self._unknown(player, raw, chat_id, message_id)
        canon = self.bank.canonical(aid)
        if self.used(aid):
            return {"kind": "dup", "canonical": canon}
        self.db.ex("INSERT INTO history(round_no,answer_id,raw,player_id,status,chat_id,message_id,ts) VALUES(?,?,?,?,?,?,?,?)",
                   (self.round_no, aid, clean_display(raw), player["id"], "valid", chat_id, message_id, self.clock()))
        self._start_timer()
        return {"kind": "valid", "canonical": canon, "player": player}

    def _unknown(self, player, raw, chat_id, message_id):
        n = normalize(raw)
        same = self.db.one("SELECT * FROM pending WHERE topic_id=? AND norm=? ORDER BY id DESC", (self.topic_id, n))
        if same and same["status"] == "open":
            return {"kind": "unknown_dup"}
        if same and same["status"] == "rejected":
            return {"kind": "rejected_before"}
        cur = self.db.ex("INSERT INTO pending(topic_id,raw,norm,player_id,chat_id,message_id,ts) VALUES(?,?,?,?,?,?,?)",
                         (self.topic_id, clean_display(raw), n, player["id"], chat_id, message_id, self.clock()))
        if self.timer_state == "running":      # تا تصمیم مالک، تایمر نایستاده به پایان نرسد
            self._freeze_timer()
            self.db.set("timer_pending_pause", 1)
        return {"kind": "unknown", "pending_id": cur.lastrowid}

    def find_pending(self, text=None, chat_id=None, message_id=None):
        if message_id is not None:
            r = self.db.one("SELECT * FROM pending WHERE status='open' AND message_id=? AND (chat_id=? OR ? IS NULL) "
                            "ORDER BY id DESC", (message_id, chat_id, chat_id))
            if r:
                return r
        if text:
            return self.db.one("SELECT * FROM pending WHERE status='open' AND norm=? ORDER BY id DESC", (normalize(text),))
        return None

    def _resume_after_pending(self):
        if self.db.get("timer_pending_pause") and not self.open_pending() and self.status == "running" \
                and self.timer_state == "paused":
            self._unfreeze_timer()
            self.db.set("timer_pending_pause", 0)
            return True
        return False

    def reject_pending(self, pend_id):
        self.db.ex("UPDATE pending SET status='rejected' WHERE id=?", (pend_id,))
        return {"resumed": self._resume_after_pending()}

    def accept_pending(self, pend_id, text=None):
        p = self.db.one("SELECT * FROM pending WHERE id=?", (pend_id,))
        if not p or p["status"] != "open":
            return None
        aid, st = self.bank.add_answer(p["topic_id"], text or p["raw"])
        self.db.ex("UPDATE pending SET status='accepted' WHERE id=?", (pend_id,))
        res = {"answer_id": aid, "canonical": self.bank.canonical(aid), "registered": False, "player": None}
        player = self.players.get(p["player_id"])
        if (self.status == "running" and self.phase == "answering" and p["topic_id"] == self.topic_id
                and player and player["active"] and not self.used(aid)):
            self.db.ex("INSERT INTO history(round_no,answer_id,raw,player_id,status,chat_id,message_id,ts) VALUES(?,?,?,?,?,?,?,?)",
                       (self.round_no, aid, p["raw"], player["id"], "valid", p["chat_id"], p["message_id"], self.clock()))
            self.db.set("timer_pending_pause", 0)
            if self.timer_state == "paused" and not self.db.get("timer_game_paused"):
                # تایمر به‌خاطر جواب ناشناخته ایستاده بود → حالا با جواب تأییدشده از نو شروع شود
                self.db.set("timer_state", "none")
            self._start_timer()
            if self.open_pending() and self.timer_state == "running":
                self._freeze_timer()
                self.db.set("timer_pending_pause", 1)
            res["registered"] = True
            res["player"] = player
        else:
            self._resume_after_pending()
        return res

    def find_valid_history(self, text=None, chat_id=None, message_id=None):
        if message_id is not None:
            r = self.db.one("SELECT * FROM history WHERE status='valid' AND message_id=? ORDER BY id DESC", (message_id,))
            if r:
                return r
        if text:
            aid = self.bank.lookup(self.topic_id, text) if self.topic_id else None
            if aid:
                return self.db.one("SELECT * FROM history WHERE status='valid' AND answer_id=? ORDER BY id DESC", (aid,))
        return None

    def revoke(self, history_id):
        """رد یک جواب که قبلاً معتبر ثبت شده؛ تاریخچه اصلاح و آخرین جواب معتبر قبلی بازیابی می‌شود."""
        self.db.ex("UPDATE history SET status='revoked' WHERE id=?", (history_id,))
        last = self.last_answerer()
        if not last and self.timer_state in ("running", "paused") and self.phase == "answering":
            self.db.set("timer_state", "none")
        return {"last": last}

    # ---------- بازیکنان و قلب‌ها
    def add_player(self, name, hearts):
        st, p = self.players.add(name, hearts)
        return st, p, self.after_change()

    def remove_player(self, player):
        self.players.remove(player["id"])
        return self.after_change()

    def change_hearts(self, player, delta=None, set_to=None, reason=""):
        cur = self.players.get(player["id"])["hearts"]
        target = set_to if set_to is not None else cur + delta
        res = self.players.set_hearts(player["id"], target, reason or "تغییر توسط مالک")
        res["events"] = self.after_change()
        return res

    def after_change(self):
        """بررسی مرحله نهایی پس از هر تغییر فهرست بازیکنان."""
        if self.status not in ("running", "paused") or self.phase == "done":
            return []
        act = self.players.active()
        if len(act) > 2:
            if self.tiebreak:
                self.db.set("tiebreak", 0)
            return []
        if len(act) <= 1:
            ranking = self.finish(first_pid=act[0]["id"] if act else None)
            return [{"type": "finished", "ranking": ranking}]
        a, b = act
        if a["hearts"] != b["hearts"]:
            return [{"type": "finished", "ranking": self.finish()}]
        if not self.tiebreak:
            self.db.set("tiebreak", 1)
            self.db.set("phase", "answering")
            self.db.set("timer_state", "none")
            return [{"type": "tiebreak", "players": [a, b]}]
        return []

    def pick(self, round_id, victim_id):
        """برنده دور، بازیکنی را برای کسر یک قلب انتخاب می‌کند."""
        if self.status != "running" or self.phase != "picking" or self.db.get("current_round_id") != round_id:
            return {"ok": False, "error": "not_picking"}
        winner_id = self.db.get("round_winner_id")
        victim = self.players.get(victim_id)
        if not victim or not victim["active"] or victim["removed"]:
            return {"ok": False, "error": "bad_victim"}
        if victim["id"] == winner_id:
            return {"ok": False, "error": "self"}
        self.db.ex("UPDATE rounds SET victim_id=? WHERE id=?", (victim_id, round_id))
        res = self.players.set_hearts(victim_id, victim["hearts"] - 1, f"انتخاب برنده دور {self.round_no}")
        self.db.set("phase", "answering")
        self.db.set("round_no", self.round_no + 1)
        self.db.set("round_winner_id", None)
        events = self.after_change()
        return {"ok": True, "victim": self.players.get(victim_id), "hearts": res["hearts"],
                "eliminated": res["eliminated"], "events": events}

    def winner_player(self):
        wid = self.db.get("round_winner_id")
        return self.players.get(wid) if wid else None

    def summary(self):
        return {
            "status": self.status, "phase": self.phase, "topic": self.topic_name(), "round": self.round_no,
            "timer_len": self.timer_len, "timer_state": self.timer_state, "remaining": self.remaining(),
            "active": len(self.players.active()), "eliminated": len(self.players.eliminated()),
            "last": (self.last_answerer() or {"name": None})["name"] if self.last_answerer() else None,
            "tiebreak": bool(self.tiebreak), "pending": len(self.open_pending()),
        }
