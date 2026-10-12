# -*- coding: utf-8 -*-
"""三套公开语料 → 统一任务格式（与被测方案无关，所有适配器看到逐字相同的输入）。

任务 = 若干命名空间；每个命名空间 = docs（按写入顺序）+ queries。
  doc   = {"id": str, "text": str, "container": int|None}   container 为章号/会话号（结构标签，可用可不用）
  query = {"qid": str, "q": str, "gold": [...]}               gold 的含义由各套件的判分函数定义

套件
  hmb_B   hive-memory-bench@72130ac，第 1–16 章，块 = 章内自然段依次合并到 ≥150 字（203 块）；
          84 题 / 467 条引文证据（题卡 supporting_evidence|evidence_pool 中落在切内者）
  locomo  dsh-memory@2c21e3f data/benchmarks/locomo-zh-500：567 条中文对话轮，500 题（关键词串查询）
  zh4o    MOOM-Roleplay-Dialogue@942927e ZH-4O：28 段角色扮演长对话（每段一个命名空间，按消息写入），
          1068 道题，金标为人工标注的证据消息下标；只用题干，不带选项
"""
import glob, json, os, random, re

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
_NON = re.compile(r"[^\u4e00-\u9fff0-9A-Za-z]")
_OPT = re.compile(r"\s*A[\s\.．、:：]+(.+?)\s+B[\s\.．、:：]+(.+?)\s+C[\s\.．、:：]+(.+?)\s+D[\s\.．、:：]+(.+?)\s*$")


def _need():
    for p in ("hmb/cards", "locomo", "zh4o"):
        if not os.path.isdir(os.path.join(DATA, p)):
            raise SystemExit("缺少语料：先运行 python fetch_data.py")


def _norm(s):
    return _NON.sub("", s or "")


def _chapters():
    chs = []
    for i in (1, 2, 3):
        chs += json.load(open(os.path.join(DATA, "hmb", "corpus", f"u0{i}.json"), encoding="utf-8"))["chapters"]
    return chs


def _chunks(chs, maxch, minlen=150):
    out = []
    for ch in chs:
        if ch["chapter_no"] > maxch:
            continue
        buf = ""
        for p in ch["text"].split("\n"):
            p = p.strip()
            if not p:
                continue
            buf = (buf + "\n" + p) if buf else p
            if len(buf) >= minlen:
                out.append((ch["cid"], ch["chapter_no"], buf))
                buf = ""
        if buf:
            out.append((ch["cid"], ch["chapter_no"], buf))
    return out


def _locate(quote, chunks):
    q = _norm(quote)
    if not q:
        return None
    for i, (_, _, t) in enumerate(chunks):
        if q in _norm(t):
            return i
    n = min(10, len(q))
    for i, (_, _, t) in enumerate(chunks):
        nt = _norm(t)
        if any(q[j:j + n] in nt for j in range(0, len(q) - n + 1)):
            return i
    return None


def hmb_B():
    _need()
    chs = _chapters()
    chunks = _chunks(chs, 16)
    cids = {c["cid"] for c in chs if c["chapter_no"] <= 16}
    qs = []
    for f in sorted(glob.glob(os.path.join(DATA, "hmb", "cards", "*.yaml"))):
        c = yaml.safe_load(open(f, encoding="utf-8"))
        ev = []
        for e in c.get("supporting_evidence") or c.get("evidence_pool") or []:
            if e.get("cid") in cids:
                i = _locate(e["quote"], chunks)
                if i is not None:
                    ev.append([e["cid"], str(i)])
        if ev:
            qs.append({"qid": c["qid"], "q": c["question"], "gold": ev})
    docs = [{"id": str(i), "text": t, "container": no, "cid": cid} for i, (cid, no, t) in enumerate(chunks)]
    return [{"ns": "hmb_B", "docs": docs, "queries": qs}]


def locomo():
    _need()
    d = os.path.join(DATA, "locomo")
    corpus = [json.loads(l) for l in open(os.path.join(d, "corpus567.jsonl"), encoding="utf-8")]
    qs = [json.loads(l) for l in open(os.path.join(d, "questions500.jsonl"), encoding="utf-8")]
    docs = [{"id": c["id"], "text": c["zh"], "container": None} for c in corpus]
    queries = [{"qid": str(k), "q": q["question"], "gold": list(q["evidence_turns"])} for k, q in enumerate(qs)]
    return [{"ns": "locomo", "docs": docs, "queries": queries}]


def zh4o():
    _need()
    Z = os.path.join(DATA, "zh4o")
    out = []
    for i in range(1, 29):
        d = json.loads(open(os.path.join(Z, f"label_{i}.jsonl"), encoding="utf-8").readline())
        docs = [{"id": str(j), "text": f"{m['sender_name']}：{m['text']}", "container": None}
                for j, m in enumerate(d["messages"])]
        qa = json.load(open(os.path.join(Z, f"qa_{i}.json"), encoding="utf-8"))
        queries = []
        for key, (q, _ans) in qa.items():
            m = _OPT.search(q)
            queries.append({"qid": f"{i}:{key}", "q": q[:m.start()] if m else q, "gold": int(key)})
        out.append({"ns": f"zh4o_{i}", "docs": docs, "queries": queries})
    return out


def locomo_d5k(n=5000, seed=7):
    """locomo + n 条 KdConv 跨领域干扰句（按种子 7 打乱后取前 n 条，追加在语料之后写入）。
    不带干扰时 567 条语料过小，参照基线 hit@10 已到 100%，无区分度。"""
    [t] = locomo()
    u = [json.loads(l)["t"] for l in open(os.path.join(DATA, "kdconv_utts.jsonl"), encoding="utf-8")]
    random.Random(seed).shuffle(u)
    t["docs"] += [{"id": f"kd{j}", "text": x, "container": None} for j, x in enumerate(u[:n])]
    t["ns"] = "locomo_d5k"
    return [t]


def selfcheck():
    """适配器自检：hmb_B 语料，每 10 块取一块的第 20–60 字作查询，金标 = 该块。
    任何正确接入的检索系统都应接近满分；读数低说明接入有误或该路径无法召回原文片段。"""
    [t] = hmb_B()
    t["queries"] = [{"qid": f"s{d['id']}", "q": d["text"].replace("\n", "")[20:60], "gold": [d["id"]]}
                    for d in t["docs"][::10]]
    t["ns"] = "selfcheck"
    return [t]


def locomo_d5k_pre():
    """同 locomo_d5k，但干扰句先写入、语料后写入（只用来检验「候选池按写入先后截断」这一机制）。"""
    [t] = locomo_d5k()
    t["docs"] = t["docs"][567:] + t["docs"][:567]
    t["ns"] = "locomo_d5k_pre"
    return [t]


def zh4o_s4():
    """ZH-4O 前 4 段对话（固定子集）：basic-memory 写入吞吐（约 6 条/秒）跑不完全量 28 段时，所有方案都在这个子集上再报一遍，保证同口径。"""
    return zh4o()[:4]


SUITES = {"locomo_d5k_pre": locomo_d5k_pre, "zh4o_s4": zh4o_s4, "selfcheck": selfcheck, "hmb_B": hmb_B, "locomo": locomo, "locomo_d5k": locomo_d5k, "zh4o": zh4o}
