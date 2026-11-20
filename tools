# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from database import Database
from topics import Bank
from game_engine import Engine
from controller import Controller, Msg

OWNER, GROUP = 8659480577, -1001


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def adv(self, s):
        self.t += s


class World:
    def __init__(self, path=":memory:"):
        self.clock = Clock()
        self.db = Database(path)
        self.bank = Bank(self.db)
        self.bank.seed()
        self.eng = Engine(self.db, self.bank, self.clock)
        self.ctrl = Controller(self.db, self.eng, self.bank, OWNER, GROUP)
        self.mid = 100
        self.users = {}

    def tid(self, name):
        return self.bank.find_topic(name)["id"]

    def start(self, topic="حیوانات", names=("نوید", "رحیم", "آرش", "میلاد"), hearts=3):
        r = self.eng.start_game(self.tid(topic), list(names), hearts)
        assert r["ok"], r
        for i, n in enumerate(names):
            p = self.eng.players.find(n)[0]
            self.eng.players.link(p["id"], 5000 + i)
            self.users[n] = 5000 + i
        return r

    def group(self, who, text, reply_to=None, reply_user=None):
        self.mid += 1
        uid = OWNER if who == "owner" else self.users.get(who, 9999)
        name = "نوید" if who == "owner" else who
        return self.ctrl.on_text(Msg(uid, GROUP, "group", text, self.mid, reply_to, reply_user, name, name), self.clock())

    def private(self, text, uid=OWNER):
        self.mid += 1
        return self.ctrl.on_text(Msg(uid, uid, "private", text, self.mid, None, None, "x", "x"), self.clock())

    def cb(self, data, uid=OWNER):
        return self.ctrl.on_callback(uid, uid, 1, data, self.clock())

    def tick(self, secs=0.0):
        self.clock.adv(secs)
        return self.ctrl.on_tick(self.clock())

    def run_timer_out(self):
        """زمان را جلو می‌برد تا دور تمام شود."""
        outs = []
        for _ in range(40):
            outs += self.tick(1)
            if self.eng.phase != "answering" or self.eng.status == "finished":
                break
        return outs


def texts(outs):
    return "\n".join(o.text for o in outs)
