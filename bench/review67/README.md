# bench/review67：中文长期记忆检索横评（dsh-bounty #67）

被测：灵枢 lingshu（上游 main@cb3a6ea；测评者 fork 未合并开关单列）、Mem0 2.2.1（infer=False，本地嵌入）、basic-memory 0.23.2；共同量尺 `ref_bm25`（字二元组 BM25，标准库）。
报告：`docs/reviews/测评方法论_v0.1.md`、`lingshu_v0.1.md`、`mem0_v0.1.md`、`basic-memory_v0.1.md`。零 LLM 判官，全部离线。

## 一次跑完

```bash
pip install -r requirements.txt
python fetch_data.py                       # 锁定 commit + sha256，约 1–2 分钟
git clone https://github.com/FuRongJun-1999/lingshu /tmp/ls_main && git -C /tmp/ls_main checkout cb3a6ea
git clone -b feat/structure-anchor https://github.com/WASD258-jpg/lingshu /tmp/ls_fork && git -C /tmp/ls_fork checkout cef7061
LS_MAIN=/tmp/ls_main LS_FORK=/tmp/ls_fork bash run_all.sh     # 2 vCPU 上约 1.5 小时，大头是 basic-memory 写入
```

判分器守卫（不需要数据，秒级）：`python tests/test_score.py && python tests/test_score.py --mutate`（7 种定点变异，每种都必须让指定判据变红并点名）。

只看读数（不重跑）：`tar xzf runs.tar.gz && bash pairs.sh all`。

## 文件

| 文件 | 作用 |
|---|---|
| `tasks.py` | 套件：selfcheck、hmb_B、locomo、locomo_d5k、locomo_d5k_pre、zh4o、zh4o_s4 |
| `adapters/*.py` | 每个方案一个适配器：`build(ns, docs)`、`search(handle, q, k)` |
| `run.py <系统> <配置[,配置]> <套件>` | 写入 + 检索 → `runs/<系统>.<配置>.<套件>.jsonl`（每题 top-10 文档 id） |
| `bm_build.py` | basic-memory 分次写入（`BM_STATE` 持久目录，`BUDGET_S` 单次时长） |
| `score.py a.jsonl [b.jsonl]` | 纯字符串/下标判分；两份时输出配对差值与 95% CI（自助法 2000 次，种子 0） |
| `pairs.sh <lingshu|mem0|basicmem|all>` | 打印各报告「原始输出」一节 |
| `tests/test_score.py` | 判分器守卫 G1–G5 ＋ `--mutate` 定点变异自证（G5 在有 runs/ 与 data/ 时重算报告引用的 14 个代表读数） |
| `overlap.py` | 问句与证据字二元组重合度 |
| `runs.tar.gz` | 本次全部原始 runs |

注意：basic-memory 的 `BM_STATE` 必须在本地磁盘（网络盘 / FUSE 上 SQLite 会损坏）；`run.py` 末尾 `os._exit(0)` 是因为 basic-memory 后台线程会让解释器退出时挂起。
