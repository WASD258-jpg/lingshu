# -*- coding: utf-8 -*-
"""basic-memory（basicmachines-co/basic-memory，PyPI basic-memory）。本地模式：markdown 文件 + SQLite。
写入：每条 doc 一篇笔记（文件 d<id>.md，frontmatter title=<id>，正文=原文），`bm project add` + `bm reindex`
      ——与用户把笔记放进项目目录后同步索引的路径相同。配置目录用独立临时目录（BASIC_MEMORY_CONFIG_DIR）。
检索：进程内调用 MCP 工具 basic_memory.mcp.tools.search_notes(query, project, search_type, output_format="json")，
      按返回顺序取前 10 篇不同笔记（同一笔记的多个分块只计一次；为此每次取 30 条结果再去重）。
配置：
  text       search_type="text"   SQLite FTS5（tokenize='unicode61 tokenchars 0x2F'）——未装语义依赖时的产品默认
  hybrid_en  search_type="hybrid" 语义依赖齐全时的产品默认：fastembed bge-small-en-v1.5（默认模型）+ FTS
  hybrid_zh  search_type="hybrid" 把 semantic_embedding_model 换成 BAAI/bge-small-zh-v1.5（与 Mem0 同一中文模型）
  vector_zh  search_type="vector" 同一中文模型只走向量分支（与 hybrid_zh 共用写入），用来拆出融合的影响
  hybrid_zh_t0 同 hybrid_zh，但检索时 min_similarity=0（关掉默认 semantic_min_similarity=0.55 的向量结果截断）
  text 与 hybrid_en 写入完全相同（同一默认模型建索引），可共用一次写入；hybrid_zh 需单独写入。
"""
import asyncio, json, os, subprocess, sys, tempfile, importlib.metadata as _md

NAME = "basicmem"
VERSION = "basic-memory " + _md.version("basic-memory")
CONFIGS = {"text": {"type": "text"}, "hybrid_en": {"type": "hybrid"},
           "hybrid_zh": {"type": "hybrid", "model": "BAAI/bge-small-zh-v1.5", "dims": "512"},
           "vector_zh": {"type": "vector", "model": "BAAI/bge-small-zh-v1.5", "dims": "512"},
           "hybrid_zh_t0": {"type": "hybrid", "model": "BAAI/bge-small-zh-v1.5", "dims": "512", "thr": 0.0}}
_BM = os.path.join(os.path.dirname(sys.executable), "basic-memory")


def _bm():
    import shutil
    return shutil.which("basic-memory") or os.path.expanduser("~/.local/bin/basic-memory")


STATE = os.environ.get("BM_STATE")  # 持久目录：设置后写入可分多次续做（单次运行受时限时用），见 bm_build.py


class Adapter:
    def __init__(self, cfg):
        self.cfg = dict(cfg)
        if STATE:
            os.makedirs(os.path.join(STATE, "cfg"), exist_ok=True)
        os.environ["BASIC_MEMORY_CONFIG_DIR"] = os.path.join(STATE, "cfg") if STATE else tempfile.mkdtemp()
        os.environ.setdefault("BASIC_MEMORY_LOG_LEVEL", "WARNING")
        os.environ["BASIC_MEMORY_TELEMETRY_ENABLED"] = "false"
        if cfg.get("model"):
            os.environ["BASIC_MEMORY_SEMANTIC_EMBEDDING_MODEL"] = cfg["model"]
            os.environ["BASIC_MEMORY_SEMANTIC_EMBEDDING_DIMENSIONS"] = cfg["dims"]  # 不写则按 384 建表，512 维向量全部写入失败
        self.loop = asyncio.new_event_loop()

    def configure(self, h, cfg):
        if cfg.get("model") != self.cfg.get("model"):
            raise SystemExit("hybrid_zh 与其他配置写入不同，须单独运行")
        self.cfg = dict(cfg)

    def build(self, ns, docs, upto=None):
        """upto：只写入前 upto 条后同步（续做用）；全部写完后打 .built 标记，之后 build 直接复用。"""
        d = os.path.join(STATE, ns) if STATE else tempfile.mkdtemp(prefix=ns + "_")
        from basic_memory.mcp.tools import search_notes
        self.sn = search_notes
        if STATE and os.path.exists(os.path.join(d, ".built")):
            return ns
        os.makedirs(d, exist_ok=True)
        new = not any(f.endswith(".md") for f in os.listdir(d))
        for x in docs[:upto]:
            fp = os.path.join(d, f"d{x['id']}.md")
            if os.path.exists(fp):  # 续做时不重写已写入的笔记（避免 mtime 变化触发重新索引）
                continue
            body = x["text"].replace("\r", "")
            with open(fp, "w", encoding="utf-8", newline="\n") as f:
                f.write(f"---\ntitle: '{x['id']}'\ntype: note\n---\n\n{body}\n")
        env = dict(os.environ)
        steps = ([["project", "add", ns, d, "--local"]] if new else []) + [["reindex", "-p", ns]]
        for args in steps:
            r = subprocess.run([_bm()] + args, env=env, capture_output=True, text=True)
            if r.returncode:
                raise SystemExit(f"basic-memory {' '.join(args)} 失败：{r.stderr[-800:]}")
        if STATE and (upto is None or upto >= len(docs)):
            open(os.path.join(d, ".built"), "w").close()
        return ns

    def search(self, ns, q, k):
        kw = {"min_similarity": self.cfg["thr"]} if "thr" in self.cfg else {}
        r = self.loop.run_until_complete(self.sn(query=q, project=ns, page_size=30,
                                                 search_type=self.cfg["type"], output_format="json", **kw))
        if isinstance(r, str):
            try:
                r = json.loads(r)
            except ValueError:
                return []
        out = []
        for x in (r or {}).get("results", []):
            t = x.get("title")
            if t is not None and t not in out:
                out.append(str(t))
            if len(out) == k:
                break
        return out
