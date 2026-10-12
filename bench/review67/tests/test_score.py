# -*- coding: utf-8 -*-
"""判分器守卫（零 LLM、纯标准库、不需要下载数据）。

  python tests/test_score.py           逐条判据，全过 → exit 0
  python tests/test_score.py --mutate  定点变异自证：对 score.py 注入 7 种错误，每种都必须让指定判据变红并点名

判据：
  G1 locomo 口径：hit@1 / hit@10 / MRR@10 精确值；只看前 10（第 11 位命中不算）
  G2 hmb 口径：证据保留按引文计数；块级命中按章计
  G3 zh4o 口径：正文逐字相同的消息等价；窗口 ±1；MRR 按窗口
  G4 配对自助法：同一份读数 Δ=0 且 CI=[0,0]；固定种子两次结果相同；Δ 等于聚合差
  G5 已发布读数回归：runs/ 与 data/ 都在时，重算 4 份报告引用的代表读数，必须与报告一致
"""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(HERE, "score.py"), encoding="utf-8").read()


def load_score(src):
    spec = importlib.util.spec_from_loader("score_under_test", loader=None)
    m = importlib.util.module_from_spec(spec)
    m.__file__ = os.path.join(HERE, "score.py")
    exec(compile(src, "score.py", "exec"), m.__dict__)
    return m


def fake(S, suite, docs, queries):
    t = {"ns": "n", "docs": docs, "queries": queries}
    S._cache[suite] = {"n": t}
    S._prep(suite)


def per(S, suite, tops):
    rows = [{"ns": "n", "qid": q, "top": top} for q, top in tops.items()]
    return {k: S.agg(v) for k, v in S.per_question({"suite": suite}, rows).items()}


def g1(S):
    docs = [{"id": f"d{i}", "text": str(i)} for i in range(12)]
    qs = [{"qid": "a", "gold": ["d0"]}, {"qid": "b", "gold": ["d2", "d9"]}, {"qid": "c", "gold": ["d10"]}]
    fake(S, "locomo", docs, qs)
    top = [f"d{i}" for i in range(12)]
    r = per(S, "locomo", {"a": top, "b": top, "c": top})
    assert abs(r["hit@1"] - 1 / 3) < 1e-9, ("G1 hit@1", r)
    assert abs(r["hit@10"] - 2 / 3) < 1e-9, ("G1 hit@10（第 11 位不算）", r)
    assert abs(r["MRR@10"] - (1 + 1 / 3 + 0) / 3) < 1e-9, ("G1 MRR@10", r)


def g2(S):
    docs = [{"id": "x1", "cid": 1, "text": ""}, {"id": "x2", "cid": 1, "text": ""}, {"id": "y1", "cid": 2, "text": ""}]
    qs = [{"qid": "q", "gold": [(1, "x1"), (1, "x2"), (2, "y1")]}]
    fake(S, "hmb_B", docs, qs)
    r = per(S, "hmb_B", {"q": ["x2"]})
    assert abs(r["证据保留@10"] - 1 / 3) < 1e-9, ("G2 证据保留@10", r)
    assert abs(r["块级命中@10"] - 2 / 3) < 1e-9, ("G2 块级命中@10", r)


def g3(S):
    docs = [{"id": str(i), "text": t} for i, t in enumerate(["用户：嗯", "甲", "乙", "用户：嗯", "丙", "丁"])]
    qs = [{"qid": "dup", "gold": 0}, {"qid": "win", "gold": 2}, {"qid": "miss", "gold": 5}]
    fake(S, "zh4o", docs, qs)
    r = per(S, "zh4o", {"dup": ["3"], "win": ["4", "1"], "miss": ["1", "2"]})
    assert abs(r["证据@10"] - 1 / 3) < 1e-9, ("G3 证据@10（逐字相同等价）", r)
    assert abs(r["窗口@10"] - 1 / 3) < 1e-9, ("G3 窗口@10（±1）", r)
    assert abs(r["MRR@10"] - (0 + 1 / 2 + 0) / 3) < 1e-9, ("G3 MRR@10（按窗口）", r)


def g4(S):
    a = [((i,), i % 2, 1) for i in range(50)]
    b = [((i,), 1, 1) for i in range(50)]
    assert S.boot(a, a) == (0.0, 0.0), "G4 同一份读数 CI 必须为 [0,0]"
    c = [((i,), (i * 7) % 5 / 4, 1) for i in range(40)]
    e = [((i,), (i * 3) % 7 / 6, 1) for i in range(40)]
    got = S.boot(c, e)
    assert abs(got[0] + 0.14375) < 1e-12 and abs(got[1] - 0.14583333333333326) < 1e-12, \
        ("G4 种子 0 的 CI 必须等于固定值（报告里的 CI 才能逐位复现）", got)
    lo, hi = S.boot(a, b)
    d = S.agg(b) - S.agg(a)
    assert lo <= d <= hi and abs(d - 0.5) < 1e-9, ("G4 Δ 与 CI", lo, d, hi)


EXPECT = {  # 报告引用的代表读数（runs 文件, 指标, 报告值）
    ("ref_bm25.default.hmb_B", "证据保留@10", "26.3"), ("lingshu.legacy.hmb_B", "证据保留@10", "17.6"),
    ("lingshu.legacy.locomo_d5k", "hit@10", "8.8"), ("lingshu.legacy.locomo_d5k_pre", "hit@10", "85.4"),
    ("lingshu.fts_ctx_anchor.hmb_B", "证据保留@10", "39.4"), ("mem0.default.hmb_B", "证据保留@10", "27.8"),
    ("mem0.default.zh4o", "证据@10", "22.5"), ("mem0.default.zh4o_s4", "证据@10", "19.5"),
    ("basicmem.text.hmb_B", "证据保留@10", "0.0"), ("basicmem.hybrid_en.hmb_B", "证据保留@10", "7.5"),
    ("basicmem.hybrid_zh_t0.hmb_B", "证据保留@10", "27.2"), ("basicmem.hybrid_zh.zh4o_s4", "证据@10", "23.9"),
    ("ref_bm25.default.zh4o", "证据@10", "26.3"), ("basicmem.hybrid_en.locomo_d5k", "hit@10", "98.8"),
}


def g5(S):
    if not (os.path.isdir(os.path.join(HERE, "runs")) and os.path.isdir(os.path.join(HERE, "data"))):
        print("  G5 跳过：需要 runs/（tar xzf runs.tar.gz）与 data/（python fetch_data.py）")
        return
    S._cache.clear()
    for f, k, v in sorted(EXPECT):
        meta, rows = S.load(os.path.join(HERE, "runs", f + ".jsonl"))
        S._prep(meta["suite"])
        got = S.fmt(k, S.agg(S.per_question(meta, rows)[k]))
        assert got == v, (f"G5 {f} {k}", got, v)


GUARDS = [("G1", g1), ("G2", g2), ("G3", g3), ("G4", g4), ("G5", g5)]


def run(src, quiet=False):
    failed = []
    for name, g in GUARDS:
        S = load_score(src)
        try:
            g(S)
            quiet or print(f"  {name} 通过")
        except Exception as e:  # noqa: BLE001
            failed.append(name)
            quiet or print(f"  {name} 失败：{e!r}")
    return failed


MUTANTS = [  # (说明, 原文, 注入, 必须变红的判据)
    ("只看前 11 位", 'top = r["top"][:10]', 'top = r["top"][:11]', "G1"),
    ("MRR 名次差一", "1 / (p + 1), 1)\n        else:\n            text", "1 / (p + 2), 1)\n        else:\n            text", "G1"),
    ("证据保留按章计", 'put("证据保留@10", key, sum(i in S for _, i in q["gold"])', 'put("证据保留@10", key, sum(c in C for c, _ in q["gold"])', "G2"),
    ("取消逐字相同等价", "int(any(text.get(d) == gt for d in top))", "int(str(gold) in top)", "G3"),
    ("窗口只认证据本身", "win = {gold - 1, gold, gold + 1}", "win = {gold}", "G3"),
    ("自助法不固定种子", "rnd = random.Random(seed)", "rnd = random.Random()", "G4"),
    ("CI 分位取反", "return ds[int(.025 * n)], ds[int(.975 * n) - 1]", "return ds[int(.975 * n) - 1], ds[int(.025 * n)]", "G4"),
]


def mutate():
    bad = 0
    for desc, old, new, must in MUTANTS:
        assert SRC.count(old) == 1, f"变异锚点失效：{desc}"
        failed = run(SRC.replace(old, new), quiet=True)
        ok = must in failed
        bad += not ok
        print(f"  {'✓' if ok else '✗'} 注入「{desc}」→ 变红：{failed or '无'}（必须含 {must}）")
    return bad


if __name__ == "__main__":
    if "--mutate" in sys.argv:
        print("定点变异自证：")
        sys.exit(1 if mutate() else 0)
    print("判分器守卫：")
    sys.exit(1 if run(SRC) else 0)
