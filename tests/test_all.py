# -*- coding: utf-8 -*-
import json, os, tempfile, unittest
from helpers import World, texts, OWNER, GROUP
from answers import normalize
import commands, banner


class T01_Security(unittest.TestCase):
    def test_01_owner_only_commands(self):
        w = World(); w.start()
        out = w.group("رحیم", "کم کردن یک قلب از آرش")      # بازیکن عادی
        self.assertEqual(w.eng.players.find("آرش")[0]["hearts"], 3)
        self.assertEqual(out, [])
        w.group("رحیم", "توقف بازی")
        self.assertEqual(w.eng.status, "running")
        o = w.private("وضعیت بازی", uid=777)
        self.assertIn("فقط برای مالک", texts(o))
        w.group("owner", "کم کردن یک قلب از آرش")
        self.assertEqual(w.eng.players.find("آرش")[0]["hearts"], 2)

    def test_02_name_is_not_identity(self):
        w = World(); w.start()
        w.group("fake", "تنظیم قلب نوید روی ۱")        # کسی که اسم مالک را می‌نویسد
        self.assertEqual(w.eng.players.find("نوید")[0]["hearts"], 3)


class T02_Setup(unittest.TestCase):
    def test_wizard_full_flow(self):
        w = World()
        o = w.private("شروع بازی")
        self.assertIn("موضوع", texts(o))
        tid = w.tid("ورزش‌ها")
        w.cb(f"wz:t:{tid}")
        o = w.private("نوید\nرحیم\nآرش\nمیلاد\nنوید\nارسلان")
        self.assertIn("تکراری", texts(o))              # نام تکراری تشخیص داده شد
        self.assertIn("۵ بازیکن", texts(o))
        o = w.private("-2"); self.assertIn("فقط یک عدد", texts(o))   # ورودی نامعتبر
        o = w.private("abc"); self.assertIn("فقط یک عدد", texts(o))
        w.private("۳")
        w.cb("wz:prizes:set")
        w.private("۱۰۰۰ افغانی\nکارت شارژ")
        wz = w.db.get("wizard"); self.assertEqual(wz["step"], "confirm")
        outs = w.cb("wz:ok")
        self.assertEqual(w.eng.status, "running")
        self.assertEqual(w.eng.topic_name(), "ورزش‌ها")
        self.assertEqual(len(w.eng.players.active()), 5)
        self.assertTrue(any(o.kind == "banner" for o in outs))
        self.assertEqual(w.eng.timer_len, 10)           # تایمر پیش‌فرض

    def test_all_ten_topics_selectable(self):
        w = World()
        names = [t["name"] for t in w.bank.list_topics()]
        self.assertEqual(len(names), 10)
        for n in names:
            w2 = World(); w2.start(topic=n)
            self.assertEqual(w2.eng.topic_name(), n)

    def test_min_players_and_hearts(self):
        w = World()
        self.assertFalse(w.eng.start_game(w.tid("حیوانات"), ["الف", "ب"], 3)["ok"])
        self.assertFalse(w.eng.start_game(w.tid("حیوانات"), ["الف", "ب", "ج"], 0)["ok"])

    def test_add_remove_player_midgame(self):
        w = World(); w.start()
        w.group("owner", "افزودن بازیکن ارسلان به بازی با ۲ قلب")
        self.assertEqual(w.eng.players.find("ارسلان")[0]["hearts"], 2)
        o = w.group("owner", "افزودن بازیکن ارسلان")
        self.assertIn("از قبل", texts(o))
        o = w.group("owner", "حذف ارسلان از بازی")
        self.assertIsNone(w.eng.players.find("ارسلان")[0])
        self.assertNotIn("ارسلان", banner.render(w.db, w.eng))

    def test_hearts_ops(self):
        w = World(); w.start()
        w.group("owner", "اضافه کردن یک قلب به نوید"); self.assertEqual(w.eng.players.find("نوید")[0]["hearts"], 4)
        w.group("owner", "کم کردن یک قلب از نوید"); self.assertEqual(w.eng.players.find("نوید")[0]["hearts"], 3)
        w.group("owner", "تنظیم قلب نوید روی ۱"); self.assertEqual(w.eng.players.find("نوید")[0]["hearts"], 1)
        o = w.group("owner", "کم کردن ۵ قلب از رحیم")           # منفی نمی‌شود
        self.assertEqual(w.eng.players.get(2)["hearts"], 0)
        self.assertEqual(w.eng.players.get(2)["active"], 0)       # با صفر حذف شد
        self.assertIn("حذف", texts(o))
        self.assertNotIn("رحیم", [p["name"] for p in w.eng.players.active()])


class T03_Answers(unittest.TestCase):
    def test_normalize_and_synonyms(self):
        w = World(); tid = w.tid("حیوانات")
        for form in ("کبوتر", "کفتر", " کفتر ", "كفتر", "الاغ", "خر", "قاطر", "گوره‌خر", "گوره خر", "گورخر"):
            self.assertIsNotNone(w.bank.lookup(tid, form), form)
        self.assertEqual(normalize("ي"), normalize("ی")); self.assertEqual(normalize("ك"), normalize("ک"))
        self.assertEqual(w.bank.lookup(tid, "اسب آبی"), w.bank.lookup(tid, "اسب‌آبی"))   # نیم‌فاصله=فاصله

    def test_duplicate_by_synonym(self):
        w = World(); w.start()
        o = w.group("نوید", "کبوتر"); self.assertEqual(w.eng.last_answerer()["name"], "نوید")
        o = w.group("رحیم", "کفتر")
        self.assertIn("تکراری", texts(o))
        self.assertEqual(w.eng.last_answerer()["name"], "نوید")       # آخرین جواب عوض نشد

    def test_valid_resets_timer_dup_does_not(self):
        w = World(); w.start()
        w.group("نوید", "گربه"); end1 = w.db.get("timer_end")
        w.clock.adv(5)
        w.group("رحیم", "پیشک")                                        # تکراری
        self.assertEqual(w.db.get("timer_end"), end1)
        w.group("رحیم", "سگ")
        self.assertGreater(w.db.get("timer_end"), end1)

    def test_invalid_answer_rejected_no_change(self):
        w = World(); w.start()
        w.group("نوید", "گربه"); end1 = w.db.get("timer_end")
        o = w.group("رحیم", "سیب")                                      # میوه است، نه حیوان
        self.assertIn("در بانک نیست", texts(o))
        self.assertEqual(w.eng.last_answerer()["name"], "نوید")

    def test_owner_accepts_unknown(self):
        w = World(); w.start()
        w.group("نوید", "گربه")
        o = w.group("رحیم", "کنگاش")
        self.assertEqual(w.eng.timer_state, "paused")                   # تا تصمیم مالک
        self.assertIsNone(w.bank.lookup(w.tid("حیوانات"), "کنگاش"))
        o = w.group("owner", "کنگاش قبول")
        self.assertIsNotNone(w.bank.lookup(w.tid("حیوانات"), "کنگاش"))
        self.assertEqual(w.eng.last_answerer()["name"], "رحیم")
        self.assertEqual(w.eng.timer_state, "running")
        # در بازی بعدی هم قابل تشخیص است (بانک دائمی)
        w.eng.clear(); w.start()
        self.assertIsNotNone(w.bank.lookup(w.tid("حیوانات"), "کنگاش"))

    def test_owner_rejects_unknown(self):
        w = World(); w.start()
        w.group("نوید", "گربه"); end = w.db.get("timer_end")
        w.group("رحیم", "فیلم"); w.clock.adv(2)
        o = w.group("owner", "فیلم رد")
        self.assertIsNone(w.bank.lookup(w.tid("حیوانات"), "فیلم"))
        self.assertEqual(w.eng.last_answerer()["name"], "نوید")
        self.assertEqual(w.eng.timer_state, "running")                  # تایمر ادامه یافت
        self.assertGreater(w.db.get("timer_end"), w.clock())
        o = w.group("آرش", "فیلم"); self.assertIn("رد شده", texts(o))

    def test_reply_accept_and_history_fix_after_reject(self):
        w = World(); w.start()
        w.group("نوید", "گربه")
        w.group("رحیم", "سگ"); mid_sag = w.mid
        w.group("آرش", "گاو")
        self.assertEqual(w.eng.last_answerer()["name"], "آرش")
        o = w.group("owner", "رد", reply_to=w.mid)                       # ریپلای روی جواب «گاو»
        self.assertIn("لغو", texts(o))
        self.assertEqual(w.eng.last_answerer()["name"], "رحیم")         # بازیابی از تاریخچه
        o = w.group("میلاد", "گاو")                                      # دوباره آزاد است
        self.assertEqual(w.eng.last_answerer()["name"], "میلاد")

    def test_bank_commands_any_topic(self):
        w = World(); w.start()
        o = w.group("owner", "افزودن چپات به ورزش")
        self.assertIn("اضافه شد", texts(o)); self.assertIsNotNone(w.bank.lookup(w.tid("ورزش‌ها"), "چپات"))
        w.group("owner", "افزودن خوردن به غذا"); self.assertIsNotNone(w.bank.lookup(w.tid("غذاها"), "خوردن"))
        w.group("owner", "افزودن شبکلاش / کلاشک به حیوانات")
        self.assertEqual(w.bank.lookup(w.tid("حیوانات"), "کلاشک"), w.bank.lookup(w.tid("حیوانات"), "شبکلاش"))
        o = w.group("owner", "حذف چپات از ورزش"); self.assertIsNone(w.bank.lookup(w.tid("ورزش‌ها"), "چپات"))
        o = w.group("owner", "افزودن x به نامعلوم"); self.assertIn("نیست", texts(o))

    def test_topic_management(self):
        w = World(); w.start()
        w.group("owner", "افزودن موضوع جدید: لباس")
        self.assertIsNotNone(w.bank.find_topic("لباس"))
        o = w.group("owner", "حذف موضوع: حیوانات"); self.assertIn("دائمی", texts(o))
        o = w.group("owner", "حذف موضوع: لباس"); self.assertIn("حذف", texts(o))
        w.group("owner", "تأیید"); self.assertIsNone(w.bank.find_topic("لباس"))
        o = w.group("owner", "فهرست موضوعات"); self.assertIn("حیوانات", texts(o))


class T04_Timer(unittest.TestCase):
    def test_round_end_and_winner(self):
        w = World(); w.start()
        w.group("نوید", "گربه")
        outs = w.run_timer_out()
        self.assertEqual(w.eng.phase, "picking")
        self.assertIn("برنده‌ی دور", texts(outs))
        self.assertEqual(w.eng.winner_player()["name"], "نوید")
        self.assertTrue(any(o.kb for o in outs))
        self.assertTrue(any(o.kind == "banner" for o in outs))

    def test_countdown_starts_after_pause(self):
        w = World(); w.start()
        w.group("نوید", "گربه")
        o = w.tick(1); self.assertEqual([x for x in o if x.kind == "countdown"], [])   # مکث ۳ ثانیه
        o = w.tick(2.5); self.assertTrue(any("⏳" in x.text for x in o))

    def test_pause_resume_timer(self):
        w = World(); w.start()
        w.group("نوید", "گربه"); w.clock.adv(8)
        rem = w.eng.remaining()
        w.group("owner", "توقف تایمر"); w.clock.adv(60)
        self.assertEqual(w.eng.phase, "answering")                      # در پس‌زمینه تمام نشد
        w.group("owner", "ادامه تایمر")
        self.assertAlmostEqual(w.eng.remaining(), rem, delta=0.01)      # از زمان باقی‌مانده

    def test_pause_resume_game(self):
        w = World(); w.start()
        w.group("نوید", "گربه"); w.clock.adv(5); rem = w.eng.remaining()
        w.group("owner", "توقف بازی"); w.clock.adv(100)
        self.assertEqual(w.eng.status, "paused"); w.ctrl.on_tick(w.clock())
        self.assertEqual(w.eng.phase, "answering")
        o = w.group("رحیم", "سگ"); self.assertEqual(w.eng.last_answerer()["name"], "نوید")   # پردازش نشد
        w.group("owner", "ادامه بازی")
        self.assertEqual(w.eng.status, "running"); self.assertAlmostEqual(w.eng.remaining(), rem, delta=0.01)

    def test_set_timer_length(self):
        w = World(); w.start()
        w.group("owner", "شروع تایمر ۲۰"); self.assertEqual(w.eng.timer_len, 20)
        w.group("نوید", "گربه"); self.assertAlmostEqual(w.eng.remaining(), 23, delta=0.1)

    def test_state_survives_restart(self):
        path = os.path.join(tempfile.mkdtemp(), "t.db")
        w = World(path); w.start(); w.group("نوید", "گربه"); end = w.db.get("timer_end")
        w.db.conn.close()
        w2 = World(path)                                                 # ری‌استارت
        w2.clock.t = w.clock.t
        self.assertEqual(w2.eng.status, "running"); self.assertEqual(w2.db.get("timer_end"), end)
        self.assertEqual(len(w2.eng.players.active()), 4)
        w2.clock.adv(30); w2.ctrl.on_tick(w2.clock())
        self.assertEqual(w2.eng.phase, "picking")                        # تایمر بازیابی‌شده تمام شد


class T05_Rounds(unittest.TestCase):
    def finish_round(self, w, who, word):
        w.group(who, word); return w.run_timer_out()

    def test_pick_and_hearts(self):
        w = World(); w.start()
        self.finish_round(w, "نوید", "گربه")
        r = self.eng_pick(w, "نوید", "رحیم")
        self.assertEqual(w.eng.players.find("رحیم")[0]["hearts"], 2)
        self.assertEqual(w.eng.phase, "answering"); self.assertEqual(w.eng.round_no, 2)

    def eng_pick(self, w, winner, victim):
        rid = w.db.get("current_round_id"); vid = w.eng.players.find(victim)[0]["id"]
        return w.ctrl.on_callback(w.users[winner], GROUP, 1, f"pick:{rid}:{vid}", w.clock())

    def test_only_winner_or_owner_can_pick(self):
        w = World(); w.start()
        self.finish_round(w, "نوید", "گربه")
        o = self.eng_pick(w, "رحیم", "آرش")                              # رحیم برنده نیست
        self.assertEqual(w.eng.phase, "picking")
        self.assertIn("فقط برنده", texts(o))
        self.eng_pick(w, "نوید", "آرش"); self.assertEqual(w.eng.phase, "answering")

    def test_cannot_pick_self_or_eliminated(self):
        w = World(); w.start()
        self.finish_round(w, "نوید", "گربه")
        self.eng_pick(w, "نوید", "نوید"); self.assertEqual(w.eng.phase, "picking")

    def test_elimination_to_finals_ranking(self):
        w = World(); w.start(hearts=1)
        self.finish_round(w, "نوید", "گربه")
        self.eng_pick(w, "نوید", "رحیم")                                  # رحیم حذف
        self.assertEqual(len(w.eng.players.active()), 3)
        self.finish_round(w, "نوید", "سگ")
        o = self.eng_pick(w, "نوید", "آرش")                               # دو نفر می‌مانند: نوید و میلاد، هر دو ۱ قلب → تساوی
        self.assertEqual(w.eng.status, "running"); self.assertEqual(w.eng.tiebreak, 1)
        self.assertIn("تعیین تکلیف", texts(o))
        outs = self.finish_round(w, "میلاد", "گاو")                        # برنده‌ی دور تعیین تکلیف
        self.assertEqual(w.eng.status, "finished")
        ranking = w.db.get("ranking")
        self.assertEqual([r["name"] for r in ranking][:2], ["میلاد", "نوید"])
        self.assertEqual(ranking[-1]["name"], "رحیم")                      # اولین حذف‌شده آخر است
        self.assertEqual([r["rank"] for r in ranking], [1, 2, 3, 4])

    def test_finals_by_hearts(self):
        w = World(); w.start(hearts=2)
        w.group("owner", "تنظیم قلب آرش روی ۰"); w.group("owner", "تنظیم قلب رحیم روی ۰")
        self.assertEqual(w.eng.status, "running")                         # نوید و میلاد هر دو ۲ قلب → تعیین تکلیف
        self.assertEqual(w.eng.tiebreak, 1)
    
    def test_finals_unequal_hearts(self):
        w = World(); w.start(hearts=2)
        w.group("owner", "کم کردن یک قلب از میلاد")
        w.group("owner", "تنظیم قلب آرش روی ۰"); w.group("owner", "تنظیم قلب رحیم روی ۰")
        self.assertEqual(w.eng.status, "finished")
        r = w.db.get("ranking"); self.assertEqual(r[0]["name"], "نوید")

    def test_manual_end(self):
        w = World(); w.start()
        o = w.group("owner", "پایان بازی"); self.assertIn("مطمئنی", texts(o))
        w.group("owner", "تأیید"); self.assertEqual(w.eng.status, "finished")


class T06_Prizes_Banner_Cleanup(unittest.TestCase):
    def test_prizes_and_announce(self):
        w = World(); w.start(hearts=1)
        w.group("owner", "تغییر جایزه ۱: ۱۰۰۰ افغانی"); w.group("owner", "تغییر جایزه ۲: کارت شارژ")
        o = w.group("owner", "تعداد برندگان ۳"); self.assertIn("برابر نیست", texts(o))   # هشدار
        w.group("owner", "تعداد برندگان ۲")
        w.group("owner", "پایان بازی"); w.group("owner", "تأیید")
        o = w.group("owner", "اعلام برندگان")
        t = texts(o); self.assertIn("۱۰۰۰ افغانی", t); self.assertIn("کارت شارژ", t)

    def test_banner_single_editable_message(self):
        w = World(); w.start()
        t = banner.render(w.db, w.eng)
        for s in ("گروه چتکده هراتی‌ها", "آخرین واژه", "تیم کاکتوس", "Cactuc ⎊ نــــوید", "حیوانات", "نوید", "❤️❤️❤️"):
            self.assertIn(s, t)
        self.assertTrue(t.index("گروه چتکده") < t.index("تیم کاکتوس") < t.index("موضوع"))
        o = w.group("owner", "کم کردن یک قلب از نوید")
        self.assertTrue(any(x.kind == "banner" for x in o))                 # بنر ویرایش می‌شود، پیام جدید نه

    def test_banner_edit_flow(self):
        w = World(); w.start()
        w.private("ویرایش بنر"); w.private("🏛 چتکده\n🎮 واژه آخر")
        self.assertEqual(w.db.get("banner_draft"), "🏛 چتکده\n🎮 واژه آخر")
        self.assertNotIn("واژه آخر", banner.render(w.db, w.eng))            # تا تأیید اعمال نشود
        o = w.private("تأیید بنر"); self.assertTrue(any(x.kind == "banner" for x in o))
        self.assertIn("واژه آخر", banner.render(w.db, w.eng))

    def test_cleanup_keeps_topics(self):
        w = World(); w.start(); w.group("نوید", "کنگاش"); w.group("owner", "کنگاش قبول")
        w.group("owner", "پایان بازی"); w.group("owner", "تأیید")
        o = w.private("پاک‌سازی بازیکنان"); w.private("تأیید")                 # تأیید اول
        self.assertEqual(len(w.eng.players.visible()), 4)                    # هنوز پاک نشده
        w.private("تأیید")                                                    # تأیید دوم
        self.assertEqual(len(w.eng.players.visible()), 0)
        self.assertEqual(w.db.q("SELECT COUNT(*) c FROM history")[0]["c"], 0)
        self.assertEqual(w.eng.status, "idle")
        self.assertEqual(len(w.bank.list_topics()), 10)
        self.assertIsNotNone(w.bank.lookup(w.tid("حیوانات"), "کنگاش"))       # جواب تأییدشده مانده
        self.assertIsNotNone(w.bank.lookup(w.tid("حیوانات"), "کفتر"))

    def test_cleanup_blocked_during_game(self):
        w = World(); w.start()
        self.assertIn("در جریان", texts(w.private("پاک‌سازی بازیکنان")))


class T07_Panel_and_Help(unittest.TestCase):
    def test_all_panel_buttons_work(self):
        w = World(); w.start()
        o = w.private("/start"); labels = [b[0] for row in o[0].kb for b in row]
        self.assertEqual(len(labels), 12)
        for row in o[0].kb:
            for label, data in row:
                outs = w.cb(data)
                self.assertTrue(outs, label)
                self.assertFalse(any(x.kind == "toast" and x.text.startswith("خطا") for x in outs), label)

    def test_sub_buttons(self):
        w = World(); w.start()
        pid = w.eng.players.find("رحیم")[0]["id"]
        w.cb(f"hp:{pid}:-1"); self.assertEqual(w.eng.players.get(pid)["hearts"], 2)
        w.cb(f"hp:{pid}:1"); self.assertEqual(w.eng.players.get(pid)["hearts"], 3)
        w.cb("tm:15"); self.assertEqual(w.eng.timer_len, 15)
        w.cb("set:stop"); self.assertEqual(w.eng.status, "paused")
        w.cb("set:resume"); self.assertEqual(w.eng.status, "running")
        w.cb(f"pd:{pid}"); self.assertIsNone(w.eng.players.find("رحیم")[0])
        w.cb("pa"); w.private("ارسلان"); self.assertIsNotNone(w.eng.players.find("ارسلان")[0])
        w.cb("ta"); w.private("لباس"); self.assertIsNotNone(w.bank.find_topic("لباس"))
        w.cb("pz:set"); w.private("جایزه الف\nجایزه ب"); self.assertEqual(w.eng.prizes.count(), 2)
        self.assertEqual(w.cb("cf:no")[0].text, "ℹ️ چیزی برای تأیید نیست.")
        self.assertTrue(w.cb("bn:update")); self.assertTrue(w.cb("bn:recreate")[0].final)

    def test_non_owner_buttons_blocked(self):
        w = World(); w.start()
        self.assertIn("فقط مالک", texts(w.cb("menu:main", uid=123)))

    def test_help_and_wrong_command(self):
        w = World(); w.start()
        for c in ("راهنما", "راهنمای بازی", "راهنمای بازیکنان", "راهنمای تایمر", "راهنمای قلب‌ها",
                  "راهنمای موضوعات", "راهنمای جایزه‌ها", "راهنمای بنر"):
            self.assertTrue(texts(w.group("owner", c)), c)
        o = w.group("owner", "افزودن چیزی"); self.assertIn("درست نوشته نشده", texts(o))   # ساکت نیست
        o = w.group("owner", "کم کردن یک قلب از ناشناس"); self.assertIn("پیدا نشد", texts(o))

    def test_status_and_players(self):
        w = World(); w.start()
        self.assertIn("حیوانات", texts(w.group("owner", "وضعیت بازی")))
        self.assertIn("رحیم", texts(w.group("owner", "وضعیت بازیکنان")))

    def test_group_registration(self):
        w = World(); w.ctrl._env_group = None
        o = w.ctrl.on_text(__import__("controller").Msg(OWNER, -555, "group", "ثبت گروه", 1, None, None, "n", "n"))
        self.assertEqual(w.ctrl.group_id, -555)


class T07b_Edge(unittest.TestCase):
    def test_unregistered_and_eliminated_ignored(self):
        w = World(); w.start()
        o = w.group("غریبه", "گربه"); self.assertEqual(o, []); self.assertIsNone(w.eng.last_answerer())
        w.group("owner", "تنظیم قلب رحیم روی ۰")
        w.group("رحیم", "گربه"); self.assertIsNone(w.eng.last_answerer())     # حذف‌شده نمی‌تواند ادامه دهد
        self.assertNotIn("رحیم", [p["name"] for p in w.eng.players.active()])
        self.assertIn("رحیم", banner.render(w.db, w.eng))                      # در فهرست حذف‌شده‌ها می‌ماند

    def test_auto_match_by_telegram_name(self):
        w = World()
        w.eng.start_game(w.tid("حیوانات"), ["نوید", "رحیم", "آرش"], 3)
        from controller import Msg
        w.ctrl.on_text(Msg(42, GROUP, "group", "گربه", 1, None, None, "Cactuc ⎊ نــــوید", "Cactuc ⎊ نــــوید"), w.clock())
        self.assertEqual(w.eng.last_answerer()["name"], "نوید")

    def test_chatter_ignored(self):
        w = World(); w.start()
        self.assertEqual(w.group("نوید", "سلام بچه ها امروز چطورید همگی خوبید؟"), [])

    def test_rejected_by_owner_keeps_last_answer_and_timer(self):
        w = World(); w.start(); w.group("نوید", "گربه")
        w.group("رحیم", "چیزعجیب"); w.group("owner", "چیزعجیب رد")
        self.assertEqual(w.eng.last_answerer()["name"], "نوید"); self.assertEqual(w.eng.timer_state, "running")


class T08_Data(unittest.TestCase):
    def test_banks(self):
        w = World()
        with open(os.path.join(os.path.dirname(__file__), "..", "data", "topics.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["topics"]), 10)
        n = {t["name"]: len(t["answers"]) for t in data["topics"]}
        self.assertEqual(n["کشورهای جهان"], 195)
        tid = w.tid("کشورهای جهان")
        for form in ("پرتگال", "دبی", "بلجیم", "آمریکا", "USA", "گینه نو", "کوید", "نرووی", "Vatican", "فلسطین"):
            self.assertIsNotNone(w.bank.lookup(tid, form), form)
        self.assertEqual(w.bank.lookup(tid, "دبی"), w.bank.lookup(tid, "امارات متحده عربی"))
        self.assertIsNone(w.bank.lookup(tid, "کوزوو"))                            # بدون تأیید مالک اضافه نشده
        v = w.tid("سبزیجات")
        self.assertEqual(w.bank.lookup(v, "بادمجون"), w.bank.lookup(v, "بانجان سیاه"))
        h = w.tid("وسایل خانه")
        self.assertNotEqual(w.bank.lookup(h, "پاتختی"), w.bank.lookup(h, "دمدری"))
        self.assertEqual(w.bank.lookup(h, "پادیری"), w.bank.lookup(h, "دمدری"))
        self.assertIsNone(w.bank.lookup(w.tid("حیوانات"), "همستر"))
        self.assertIsNone(w.bank.lookup(w.tid("نوشیدنی‌ها"), "شربت آلبالو"))
        self.assertIsNotNone(w.bank.lookup(w.tid("نوشیدنی‌ها"), "آب آلبالو"))
        self.assertIsNotNone(w.bank.lookup(w.tid("غذاها"), "شیر برنج"))
        self.assertIsNone(w.bank.lookup(w.tid("نوشیدنی‌ها"), "شیر برنج"))
        v2 = w.tid("وسایل نقلیه"); self.assertEqual(w.bank.lookup(v2, "موتر"), w.bank.lookup(v2, "ماشین"))

    def test_seed_idempotent_and_backup(self):
        w = World(); before = w.db.q("SELECT COUNT(*) c FROM answers")[0]["c"]
        w.bank.seed(); self.assertEqual(before, w.db.q("SELECT COUNT(*) c FROM answers")[0]["c"])
        p = os.path.join(tempfile.mkdtemp(), "b.db"); w.db.backup(p); self.assertTrue(os.path.getsize(p) > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
