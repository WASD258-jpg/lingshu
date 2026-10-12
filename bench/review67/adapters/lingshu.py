# -*- coding: utf-8 -*-
"""灵枢（FuRongJun-1999/lingshu）。源码路径由 LINGSHU_SRC 指定（复现步骤里锁定 commit）。
检索入口：SpacetimeMemoryEngine.store.search_content(q, limit=k)。
配置（开关在 import 前写入环境变量；每个配置一个独立进程）：
  legacy          全部开关关闭 = 上游默认路径
  fts_ctx         LINGSHU_FTS=1 LINGSHU_FTS_CONTEXT=1
  fts_ctx_anchor  再加 LINGSHU_ANCHOR=1，并按 container 写入 chapter:N 标签（无 container 的套件不写标签）
"""
import os, subprocess, sys, tempfile

NAME = "lingshu"
CONFIGS = {
    "legacy": {},
    "fts_ctx": {"LINGSHU_FTS": "1", "LINGSHU_FTS_CONTEXT": "1"},
    "fts_ctx_anchor": {"LINGSHU_FTS": "1", "LINGSHU_FTS_CONTEXT": "1", "LINGSHU_ANCHOR": "1", "_TAGS": "1"},
}
SRC = os.environ.get("LINGSHU_SRC", "")
try:
    VERSION = subprocess.run(["git", "-C", SRC, "rev-parse", "--short=12", "HEAD"], capture_output=True,
                             text=True).stdout.strip() or "unknown"
except Exception:
    VERSION = "unknown"


class Adapter:
    def __init__(self, cfg):
        if not SRC:
            raise SystemExit("设置 LINGSHU_SRC=<lingshu 检出目录>")
        self.tags = cfg.get("_TAGS") == "1"
        for k, v in cfg.items():
            if not k.startswith("_"):
                os.environ[k] = v
        sys.path.insert(0, SRC)
        from lingshu.core.core import SpacetimeMemoryEngine
        self.E = SpacetimeMemoryEngine

    def build(self, ns, docs):
        e = self.E(os.path.join(tempfile.mkdtemp(), "b.db"))
        m = {}
        for d in docs:
            tags = [f"chapter:{d['container']}"] if self.tags and d.get("container") is not None else None
            m[e.add_perception(d["text"], importance=0.5, skip_dedup=True, tags=tags).id] = d["id"]
        e.store.search_content("预热", limit=1)
        return (e, m)

    def search(self, h, q, k):
        e, m = h
        return [m[n.id] for n, _ in e.store.search_content(q, limit=k) if n.id in m]
