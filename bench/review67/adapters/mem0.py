# -*- coding: utf-8 -*-
"""Mem0（mem0ai，PyPI）。离线配置：infer=False（不调 LLM 抽取，原文逐条入库）＋本地向量。
  嵌入   fastembed BAAI/bge-small-zh-v1.5（512 维，中文模型；Mem0 默认的 OpenAI 嵌入需联网与密钥，未测）
  向量库 qdrant 本地目录（Mem0 2.x 的 qdrant 后端自带 fastembed Qdrant/bm25 稀疏向量 → 混合打分）
  检索   Memory.search(q, filters={"user_id": ns}, top_k=k)，其余参数取默认（threshold=0.1, rerank=False）
配置：
  default     产品默认的混合打分（稠密召回 + BM25 加分 + 实体加分）
  dense_only  关闭关键词分支（keyword_search 返回 None）——用来拆出 BM25 分支在中文上的贡献
"""
import os, tempfile, importlib.metadata as _md

os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("OPENAI_API_KEY", "sk-offline-unused")  # 仅为通过构造期检查；infer=False 路径不调用 LLM
NAME = "mem0"
VERSION = "mem0ai " + _md.version("mem0ai") + " / fastembed " + _md.version("fastembed")
CONFIGS = {"default": {}, "dense_only": {"_DENSE": "1"}}
MODEL, DIM = "BAAI/bge-small-zh-v1.5", 512


class Adapter:
    def __init__(self, cfg):
        from mem0 import Memory
        self.M = Memory
        self.dense = cfg.get("_DENSE") == "1"

    def build(self, ns, docs):
        d = tempfile.mkdtemp()
        m = self.M.from_config({
            "embedder": {"provider": "fastembed", "config": {"model": MODEL, "embedding_dims": DIM}},
            "vector_store": {"provider": "qdrant", "config": {"path": d + "/q", "collection_name": "c",
                                                               "embedding_model_dims": DIM, "on_disk": True}},
            "history_db_path": d + "/h.db"})
        self._kw = m.vector_store.keyword_search
        self.configure(m, {"_DENSE": "1"} if self.dense else {})
        for x in docs:
            m.add([{"role": "user", "content": x["text"]}], user_id="u", infer=False,
                  metadata={"doc_id": x["id"]})
        return m

    def configure(self, m, cfg):
        """只改检索期：dense_only 时让关键词分支返回 None（写入期两配置完全相同，可共用一次写入）。"""
        m.vector_store.keyword_search = (lambda *a, **k: None) if cfg.get("_DENSE") == "1" else self._kw

    def search(self, m, q, k):
        r = m.search(q, filters={"user_id": "u"}, top_k=k)
        r = r["results"] if isinstance(r, dict) else r
        return [x["metadata"]["doc_id"] for x in r if x.get("metadata", {}).get("doc_id") is not None]
