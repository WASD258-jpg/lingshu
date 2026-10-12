# -*- coding: utf-8 -*-
"""合并分片：python merge.py runs/<sys>.<cfg>.<suite>   （把 .part*.jsonl 按命名空间起点排序拼成一份）"""
import glob, json, sys
base = sys.argv[1]
parts = sorted(glob.glob(base + ".part*.jsonl"), key=lambda p: int(p.rsplit(".part", 1)[1].split("_")[0]))
metas, rows = [], []
for p in parts:
    L = [json.loads(l) for l in open(p, encoding="utf-8")]
    metas.append(L[0]); rows += L[1:]
m = dict(metas[0])
m.update(docs=sum(x["docs"] for x in metas), queries=len(rows), ingest_s=round(sum(x["ingest_s"] for x in metas), 1),
         p50_ms=None, parts=[x.get("p50_ms") for x in metas])
with open(base + ".jsonl", "w", encoding="utf-8", newline="\n") as f:
    f.write(json.dumps(m, ensure_ascii=False) + "\n")
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(parts), "parts", len(rows), "rows")
