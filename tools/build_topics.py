# -*- coding: utf-8 -*-
"""ساخت data/topics.json از tools/bank_src.py"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import bank_src
from answers import normalize


def parse(blocks):
    groups = []
    for i, blk in enumerate(blocks):
        if i == 0:   # هر خط یک گروه
            for line in blk.strip().splitlines():
                parts = [p.strip() for p in line.split("/") if p.strip()]
                if parts:
                    groups.append(parts)
        else:        # واژه‌های تکی
            for w in re.split(r"[،,\n]", blk):
                if w.strip():
                    groups.append([w.strip()])
    return groups


def build():
    topics = []
    for name, blocks in bank_src.TOPICS:
        seen, out = {}, []
        for g in parse(blocks):
            norms = [normalize(x) for x in g]
            hit = next((seen[n] for n in norms if n in seen), None)
            if hit is not None:
                for x, n in zip(g, norms):
                    if n not in seen:
                        out[hit].append(x); seen[n] = hit
                continue
            uniq, used = [], set()
            for x, n in zip(g, norms):
                if n not in used:
                    uniq.append(x); used.add(n)
            out.append(uniq)
            for n in used:
                seen[n] = len(out) - 1
        topics.append({"name": name, "answers": out})
    return {"version": 1, "topics": topics}


if __name__ == "__main__":
    data = build()
    with open(os.path.join(HERE, "..", "data", "topics.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    for t in data["topics"]:
        print(t["name"], len(t["answers"]))
