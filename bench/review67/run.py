# -*- coding: utf-8 -*-
"""用法：python run.py <system> <config> <suite>   → runs/<system>.<config>.<suite>.jsonl
每行一题：{"ns","qid","top":[doc id…]}；首行为元信息（版本、配置、耗时）。top-k 固定 10。"""
import importlib, json, os, platform, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
K = 10


def main():
    sysname, cfgnames, suite = sys.argv[1:4]
    cfgnames = cfgnames.split(",")  # 多个配置共用一次写入：仅限只改检索期行为、声明了 configure() 的适配器
    mod = importlib.import_module(f"adapters.{sysname}")
    import tasks
    T = tasks.SUITES[suite]()
    part = os.environ.get("NS_RANGE")  # 例 NS_RANGE=0:7 只跑第 0–6 个命名空间（单次运行受时限时分片；merge.py 合并）
    if part:
        lo, hi = map(int, part.split(":"))
        T = T[lo:hi]
    a = mod.Adapter(mod.CONFIGS[cfgnames[0]])
    if len(cfgnames) > 1 and not hasattr(a, "configure"):
        raise SystemExit(f"{sysname} 的配置影响写入，不能共用一次写入；请逐个配置运行")
    os.makedirs(os.path.join(HERE, "runs"), exist_ok=True)
    rows = {c: [] for c in cfgnames}
    lat = {c: [] for c in cfgnames}
    t_ing = 0.0
    for t in T:
        t0 = time.perf_counter()
        h = a.build(t["ns"], t["docs"])
        t_ing += time.perf_counter() - t0
        for c in cfgnames:
            if len(cfgnames) > 1:
                a.configure(h, mod.CONFIGS[c])
            for q in t["queries"]:
                t0 = time.perf_counter()
                top = a.search(h, q["q"], K)[:K]
                lat[c].append(time.perf_counter() - t0)
                rows[c].append({"ns": t["ns"], "qid": q["qid"], "top": top})
    for c in cfgnames:
        L = sorted(lat[c])
        meta = {"meta": True, "system": sysname, "config": c, "suite": suite, "version": mod.VERSION,
                "python": platform.python_version(), "docs": sum(len(t["docs"]) for t in T),
                "queries": len(rows[c]), "ingest_s": round(t_ing, 1), "p50_ms": round(1000 * L[len(L) // 2], 2)}
        with open(os.path.join(HERE, "runs", f"{sysname}.{c}.{suite}" + (f".part{part.replace(':', '_')}" if part else "") + ".jsonl"), "w", encoding="utf-8",
                  newline="\n") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
            for r in rows[c]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(json.dumps(meta, ensure_ascii=False))


main()
sys.stdout.flush()
os._exit(0)  # basic-memory 的后台同步线程会让解释器退出挂起；读数已落盘
