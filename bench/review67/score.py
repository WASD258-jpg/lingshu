# -*- coding: utf-8 -*-
"""机械判分（零 LLM）。用法：
  python score.py runs/<a>.jsonl                  单份读数
  python score.py runs/<base>.jsonl runs/<x>.jsonl 配对对照：两份读数 + 差值 + 配对自助法 95% CI（题为单位，2000 次，种子 0）

指标（全部 = Σ分子 / Σ分母，按题聚合，便于配对自助法）
  hmb_B   证据保留@10  引文所在块进 top-10 的比例（分母 = 引文条数）
          块级命中@10  引文所在章有任一块进 top-10 的比例
  locomo  hit@1 / hit@10 / MRR@10   任一证据轮进入前 k
  zh4o    证据@10      证据消息进 top-10；正文逐字相同的消息视为同一条（不可区分，统一口径作用于所有方案）
          窗口@10      允许证据的上一条或下一条（一问一答常跨两条）
          MRR@10       按窗口口径
"""
import json, random, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tasks  # noqa: E402

_cache = {}


def _task(suite):
    if suite not in _cache:
        _cache[suite] = {t["ns"]: t for t in tasks.SUITES[suite]()}
    return _cache[suite]


def load(path):
    L = [json.loads(l) for l in open(path, encoding="utf-8")]
    return L[0], L[1:]


def per_question(meta, rows):
    """→ {metric: [(qkey, num, den), …]}"""
    T = _task(meta["suite"])
    out = {}

    def put(m, key, n, d):
        out.setdefault(m, []).append((key, n, d))

    for r in rows:
        t = T[r["ns"]]
        q = t["_qi"][r["qid"]]
        top = r["top"][:10]
        key = (r["ns"], r["qid"])
        if meta["suite"] == "hmb_B":
            cid = {d["id"]: d["cid"] for d in t["docs"]}
            S, C = set(top), {cid[i] for i in top}
            put("证据保留@10", key, sum(i in S for _, i in q["gold"]), len(q["gold"]))
            put("块级命中@10", key, sum(c in C for c, _ in q["gold"]), len(q["gold"]))
        elif meta["suite"].startswith("locomo") or meta["suite"] == "selfcheck":
            g = set(q["gold"])
            p = next((k for k, d in enumerate(top) if d in g), None)
            put("hit@1", key, int(p == 0), 1)
            put("hit@10", key, int(p is not None), 1)
            put("MRR@10", key, 0.0 if p is None else 1 / (p + 1), 1)
        else:
            text = t["_text"]
            gold = q["gold"]
            gt = text[str(gold)]
            put("证据@10", key, int(any(text.get(d) == gt for d in top)), 1)
            win = {gold - 1, gold, gold + 1}
            p = next((k for k, d in enumerate(top) if d.isdigit() and int(d) in win), None)
            put("窗口@10", key, int(p is not None), 1)
            put("MRR@10", key, 0.0 if p is None else 1 / (p + 1), 1)
    return out


def _prep(suite):
    T = _task(suite)
    for t in T.values():
        t.setdefault("_qi", {q["qid"]: q for q in t["queries"]})
        t.setdefault("_text", {d["id"]: d["text"] for d in t["docs"]})


def agg(v):
    d = sum(x[2] for x in v)
    return sum(x[1] for x in v) / d if d else 0.0


def fmt(m, x):
    return f"{x:.3f}" if m.startswith("MRR") else f"{100 * x:.1f}"


def boot(a, b, n=2000, seed=0):
    A = {k: (x, y) for k, x, y in a}
    B = {k: (x, y) for k, x, y in b}
    keys = sorted(A)
    rnd = random.Random(seed)
    ds = []
    for _ in range(n):
        s = [keys[rnd.randrange(len(keys))] for _ in keys]
        da = sum(A[k][1] for k in s)
        ds.append(sum(B[k][0] for k in s) / da - sum(A[k][0] for k in s) / da)
    ds.sort()
    return ds[int(.025 * n)], ds[int(.975 * n) - 1]


def main():
    paths = sys.argv[1:]
    metas, pqs = [], []
    for p in paths:
        meta, rows = load(p)
        _prep(meta["suite"])
        metas.append(meta)
        pqs.append(per_question(meta, rows))
    if len(paths) == 1:
        m = metas[0]
        print(json.dumps({"system": m["system"], "config": m["config"], "suite": m["suite"],
                          **{k: fmt(k, agg(v)) for k, v in pqs[0].items()}, "题数": m["queries"],
                          "ingest_s": m["ingest_s"], "p50_ms": m["p50_ms"]}, ensure_ascii=False))
        return
    (ma, mb), (pa, pb) = metas, pqs
    if ma["suite"] != mb["suite"]:  # 只允许题目完全相同、仅写入方式不同的两套（如 locomo_d5k 与 locomo_d5k_pre）
        pa = {k: [(q[1], n, d) for q, n, d in v] for k, v in pa.items()}
        pb = {k: [(q[1], n, d) for q, n, d in v] for k, v in pb.items()}
        assert all({x[0] for x in pa[k]} == {x[0] for x in pb[k]} for k in pa), "两份读数的题目必须相同"
    la = f"{ma['system']}.{ma['config']}" + (f"@{ma['suite']}" if ma["suite"] != mb["suite"] else "")
    lb = f"{mb['system']}.{mb['config']}" + (f"@{mb['suite']}" if ma["suite"] != mb["suite"] else "")
    for k in pa:
        lo, hi = boot(pa[k], pb[k])
        a, b = agg(pa[k]), agg(pb[k])
        sc = 1 if k.startswith("MRR") else 100
        print(f"{ma['suite']:7s} {k:12s} {la}={fmt(k, a)}  "
              f"{lb}={fmt(k, b)}  Δ={sc * (b - a):+.{3 if sc == 1 else 1}f}  "
              f"95%CI[{sc * lo:+.{3 if sc == 1 else 1}f}, {sc * hi:+.{3 if sc == 1 else 1}f}]")


if __name__ == "__main__":
    main()
