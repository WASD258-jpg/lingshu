# -*- coding: utf-8 -*-
"""basic-memory 分次写入（单个命名空间写入超过单次运行时限时用）。
  BM_STATE=<持久目录> python bm_build.py <config> <suite> <upto>
反复以递增的 upto 运行（如 2000、4000、全部），每次只新增文件并做增量 reindex；最后一次 upto≥总数时打 .built 标记。
随后 BM_STATE=<同一目录> python run.py basicmem <config…> <suite> 直接复用已建索引检索。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tasks
from adapters import basicmem
cfg, suite, upto = sys.argv[1], sys.argv[2], int(sys.argv[3])
assert basicmem.STATE, "须设置 BM_STATE"
a = basicmem.Adapter(basicmem.CONFIGS[cfg])
t0, budget = time.time(), float(os.environ.get("BUDGET_S", "900"))  # 超过预算就不再开新的命名空间，下次续做
for t in tasks.SUITES[suite]():
    if os.path.exists(os.path.join(basicmem.STATE, t["ns"], ".built")):
        continue
    if time.time() - t0 > budget:
        print("budget reached; rerun to continue", flush=True)
        break
    t1 = time.time()
    a.build(t["ns"], t["docs"], upto)
    print(t["ns"], min(upto, len(t["docs"])), "/", len(t["docs"]), f"{time.time() - t1:.0f}s", flush=True)
os._exit(0)
