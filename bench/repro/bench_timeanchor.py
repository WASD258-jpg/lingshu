# -*- coding: utf-8 -*-
"""相对时间锚定复现：LoCoMo（英文原版 locomo10.json）category-2 temporal 题。

用法：[LINGSHU_FTS=1] [LINGSHU_TIME_ANCHOR=1] python bench_timeanchor.py
每段对话一个独立引擎；每条 turn 以其会话时刻为 temporal_coordinate 写入（写入期间把
time.time 定到会话时刻，UTC），内容为「说话人: 原文」。

三组读数（dev = 对话 0–4，test = 对话 5–9；规则只在 dev 上调过，但开发时看过一次全量
失败样例，test 不是干净留出——见设计文档「污染声明」）：
  日期正确率   证据 turn 的事件区间 ⊆ gold 区间（gold 由本文件独立的解析器从 answer 得到，
               与引擎规则不共用代码）。关闭时引擎不建区间 → 记为「会话当日」（= 只有时间戳的系统）。
  日期点名检索 问句 = 「说话人 + gold 日期」（英文写法 / 中文写法各一组，无内容词），
               证据 turn 进 top-10 / top-1 / MRR@10。
  无日期问句   原题面（When did … ?）top-10 证据命中；开关前后应逐位不变（问句不含日期不进新路径）。
gold 只认能解析成日期区间的答案（228/321）；时长类（「4 years」）与非日期答案不计。
"""
import datetime as dt, json, os, re, sys, time
from common import DATA, engine, emit, flags

MONS = ["january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december"]
M = {m: i + 1 for i, m in enumerate(MONS)}
M.update({m[:3]: i + 1 for i, m in enumerate(MONS)})
WD = {w: i for i, w in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])}
D, TD = dt.date, dt.timedelta


# ---------------- gold 解析（测量侧，独立于引擎 timeanchor） ----------------
def _month(y, m):
    return (D(y, m, 1), (D(y + 1, 1, 1) if m == 12 else D(y, m + 1, 1)) - TD(1))


def _wk_before(d):
    return (d - TD(7), d - TD(1))


def _we_before(d):
    w = d.weekday()
    s = d - TD(8) if w == 6 else d - TD(7) if w == 5 else d - TD(w + 2)
    return (s, s + TD(1))


def _date(x):
    x = re.sub(r"(\d)([a-z])", r"\1 \2", x)
    x = re.sub(r"([a-z])(\d)", r"\1 \2", x).replace("janury", "january").replace(",", " ")
    p = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", x).split()
    try:
        if len(p) == 3 and p[0].isdigit() and p[1][:3] in M:
            return D(int(p[2]), M[p[1][:3]], int(p[0]))
        if len(p) == 3 and p[1].isdigit() and p[0][:3] in M:
            return D(int(p[2]), M[p[0][:3]], int(p[1]))
    except ValueError:
        return None
    return None


def gold(a):
    a = str(a).strip().lower().rstrip(".").strip()
    a = re.sub(r"^(?:on |approximately |about |around )?(?:a |the )?", "", a)
    m = re.match(r"^(two weekends|\w+) before (.+)$", a)
    if m and _date(m.group(2)):
        k, d = m.group(1), _date(m.group(2))
        if k == "two weekends":
            return _we_before(_we_before(d)[0])
        if k in WD:
            x = d - TD((d.weekday() - WD[k]) % 7 or 7)
            return (x, x)
        return {"week": _wk_before(d), "weekend": _we_before(d), "day": (d - TD(1), d - TD(1)),
                "month": _month(*((d.year - 1, 12) if d.month == 1 else (d.year, d.month - 1))),
                "year": (D(d.year - 1, 1, 1), D(d.year - 1, 12, 31)),
                "days": (d - TD(7), d - TD(1))}.get(k)
    m = re.match(r"^weekend of (.+)$", a)
    if m and _date(m.group(1)):
        d = _date(m.group(1))
        return (d - TD(1), d + TD(1))
    m = re.match(r"^(first|second|third|last) week of (\w+),? (\d{4})$", a)
    if m and m.group(2)[:3] in M:
        s, e = _month(int(m.group(3)), M[m.group(2)[:3]])
        if m.group(1) == "last":
            return (e - TD(6), e)
        k = ["first", "second", "third"].index(m.group(1))
        return (s + TD(7 * k), s + TD(7 * k + 6))
    m = re.match(r"^(summer|spring|fall|autumn) (?:of )?(\d{4})$", a)
    if m:
        y = int(m.group(2))
        a0, b0 = {"spring": (3, 5), "summer": (6, 8), "fall": (9, 11), "autumn": (9, 11)}[m.group(1)]
        return (D(y, a0, 1), _month(y, b0)[1])
    if _date(a):
        d = _date(a)
        return (d, d)
    m = re.match(r"^(?:in )?(?:early |late |mid-?)?(\w+),? (\d{4})$", a)
    if m and m.group(1)[:3] in M:
        return _month(int(m.group(2)), M[m.group(1)[:3]])
    m = re.match(r"^(?:in )?(\d{4})$", a)
    if m:
        y = int(m.group(1))
        return (D(y, 1, 1), D(y, 12, 31))
    return None


def session_dt(s):
    m = re.search(r"(\d{1,2}):(\d{2})\s*([ap]m) on (\d{1,2}) (\w+),? (\d{4})", s.lower())
    h = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
    return dt.datetime(int(m.group(6)), M[m.group(5)[:3]], int(m.group(4)), h, int(m.group(2)))


def q_en(sp, g):
    if g[0] == g[1]:
        return f"{sp} {g[0].day} {MONS[g[0].month - 1].capitalize()} {g[0].year}"
    if g[0].day == 1 and g[1] == _month(g[0].year, g[0].month)[1]:
        return f"{sp} {MONS[g[0].month - 1].capitalize()} {g[0].year}"
    if g[0] == D(g[0].year, 1, 1) and g[1] == D(g[0].year, 12, 31):
        return f"{sp} in {g[0].year}"
    return f"{sp} {g[0].day} {MONS[g[0].month - 1].capitalize()} {g[0].year}"  # 周/周末类：取起点日


def q_zh(sp, g):
    if g[0] == g[1]:
        return f"{sp} {g[0].year}年{g[0].month}月{g[0].day}日"
    if g[0].day == 1 and g[1] == _month(g[0].year, g[0].month)[1]:
        return f"{sp} {g[0].year}年{g[0].month}月"
    if g[0] == D(g[0].year, 1, 1) and g[1] == D(g[0].year, 12, 31):
        return f"{sp} {g[0].year}年"
    return f"{sp} {g[0].year}年{g[0].month}月{g[0].day}日"


def main():
    convs = json.load(open(os.path.join(DATA, "locomo10.json"), encoding="utf-8"))
    on = os.environ.get("LINGSHU_TIME_ANCHOR") == "1"
    real = time.time
    acc = {p: dict(n=0, date_ok=0, en_h10=0, en_h1=0, en_mrr=0.0, zh_h10=0, zh_h1=0, zh_mrr=0.0, raw_h10=0)
           for p in ("dev", "test")}
    for ci, conv in enumerate(convs):
        part = "dev" if ci < 5 else "test"
        e = engine()
        c = conv["conversation"]
        ids, sday = {}, {}
        for k in sorted((k for k in c if re.match(r"session_\d+$", k)), key=lambda k: int(k.split("_")[1])):
            t0 = session_dt(c[k + "_date_time"])
            ts = (t0 - dt.datetime(1970, 1, 1)).total_seconds()
            for j, t in enumerate(c[k]):
                time.time = (lambda v=ts + j: v)
                try:
                    n = e.add_perception(f"{t['speaker']}: {t['text']}", importance=0.5, skip_dedup=True)
                finally:
                    time.time = real
                ids[n.id] = t["dia_id"]
                sday[t["dia_id"]] = (n.id, t0.date(), t["speaker"])
        st = e.store
        when = {}
        if on and getattr(st, "_when", None) is not None:
            st._when.sync()
            for nid, d0, d1 in st.conn.execute("SELECT nid, d0, d1 FROM nodes_when"):
                when[nid] = (D.fromordinal(d0), D.fromordinal(d1))
        for q in conv["qa"]:
            if q.get("category") != 2:
                continue
            g = gold(q["answer"])
            ev = [x for x in q.get("evidence", []) if x in sday]
            if g is None or not ev:
                continue
            a = acc[part]
            a["n"] += 1
            nid, d0, sp = sday[ev[0]]
            iv = when.get(nid, (d0, d0))
            a["date_ok"] += g[0] <= iv[0] and iv[1] <= g[1]
            evs = set(ev)
            for tag, qq in (("en", q_en(sp, g)), ("zh", q_zh(sp, g))):
                rk = [ids[n.id] for n, _ in st.search_content(qq, limit=10)]
                p = next((i for i, x in enumerate(rk) if x in evs), None)
                if p is not None:
                    a[tag + "_h10"] += 1
                    a[tag + "_h1"] += p == 0
                    a[tag + "_mrr"] += 1 / (p + 1)
            rk = [ids[n.id] for n, _ in st.search_content(q["question"], limit=10)]
            a["raw_h10"] += any(x in evs for x in rk)
    for p, a in acc.items():
        n = a["n"]
        emit(dict(suite=f"timeanchor_{p}", 题数=n, 日期正确率=round(a["date_ok"] / n, 3),
                  英文点名_hit10=round(a["en_h10"] / n, 3), 英文点名_hit1=round(a["en_h1"] / n, 3),
                  英文点名_mrr10=round(a["en_mrr"] / n, 3),
                  中文点名_hit10=round(a["zh_h10"] / n, 3), 中文点名_hit1=round(a["zh_h1"] / n, 3),
                  中文点名_mrr10=round(a["zh_mrr"] / n, 3),
                  原题面_hit10=round(a["raw_h10"] / n, 3), time_anchor=int(on)))


main()
