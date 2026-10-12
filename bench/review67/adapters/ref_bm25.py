# -*- coding: utf-8 -*-
"""共同参照基线：字二元组 BM25（k1=1.2, b=0.75），纯标准库。不是任何一家产品，只作统一量尺。"""
import math, re
from collections import Counter, defaultdict

NAME, VERSION = "ref_bm25", "char-bigram BM25 k1=1.2 b=0.75"
CONFIGS = {"default": {}}
_NON = re.compile(r"[^\u4e00-\u9fff0-9A-Za-z]")


def _toks(s):
    s = _NON.sub("", s).lower()
    return [s[i:i + 2] for i in range(len(s) - 1)] or ([s] if s else [])


class Adapter:
    def __init__(self, cfg):
        pass

    def build(self, ns, docs):
        tf = [Counter(_toks(d["text"])) for d in docs]
        df = Counter()
        post = defaultdict(list)
        for i, c in enumerate(tf):
            for t, n in c.items():
                df[t] += 1
                post[t].append((i, n))
        dl = [sum(c.values()) for c in tf]
        return dict(ids=[d["id"] for d in docs], post=post, df=df, dl=dl,
                    avg=(sum(dl) / len(dl)) if dl else 1.0, N=len(docs))

    def search(self, h, q, k):
        s = defaultdict(float)
        for t in set(_toks(q)):
            n = h["df"].get(t)
            if not n:
                continue
            idf = math.log(1 + (h["N"] - n + 0.5) / (n + 0.5))
            for i, f in h["post"][t]:
                s[i] += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * h["dl"][i] / h["avg"]))
        top = sorted(s, key=lambda i: (-s[i], i))[:k]
        return [h["ids"][i] for i in top]
