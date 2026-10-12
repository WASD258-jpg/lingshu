# -*- coding: utf-8 -*-
"""问句与证据的字面重合度（判断「纯词法能否找到」的上限因素）。用法：python overlap.py zh4o|hmb_B"""
import re, sys
import tasks
N = re.compile(r"[^\u4e00-\u9fff0-9A-Za-z]")
bg = lambda s: {s[i:i + 2] for i in range(len(s) - 1)} if (s := N.sub("", s).lower()) else set()
suite = sys.argv[1]
zero = tot = 0
for t in tasks.SUITES[suite]():
    txt = {d["id"]: d["text"] for d in t["docs"]}
    for q in t["queries"]:
        if suite.startswith("zh4o"):
            g = q["gold"]
            ev = "".join(txt.get(str(j), "") for j in (g - 1, g, g + 1))
        else:
            ev = "".join(txt[i] for _, i in q["gold"])
        tot += 1
        zero += not (bg(q["q"]) & bg(ev))
print(f"{suite}: 与证据（zh4o 含前后各 1 条）无任何共同字二元组的问句 {zero}/{tot} = {100 * zero / tot:.1f}%")
