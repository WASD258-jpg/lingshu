# basic-memory 检索层测评 v0.1

> dsh-bounty #67 交付物。口径见 `测评方法论_v0.1.md`。全部读数零 LLM、可离线复跑。

## 0. 意图声明

测 basic-memory（basicmachines-co/basic-memory，本地 markdown + SQLite 的 MCP 记忆服务）的 `search_notes` 能否把中文证据排进 top-10，并与共同量尺 `ref_bm25` 配对比较。依次测：纯全文检索（未装语义依赖时的默认）、产品默认混合检索（英文嵌入模型）、换成中文嵌入模型、再关掉默认相似度阈值，逐步拆出各个环节的影响。
本测评与 basic-memory 无利益关系。

## 1. 被测版本与配置

| 项 | 值 |
|---|---|
| 版本 | `basic-memory==0.23.2`，`fastembed==0.9.0`，`sqlite-vec==0.1.9` |
| 写入 | 每条文档一篇笔记 `d<id>.md`（frontmatter `title=<id>`，正文为原文），`basic-memory project add` 后 `basic-memory reindex`——与用户把笔记放进项目目录后同步索引的路径相同 |
| 检索 | 进程内调用 MCP 工具 `basic_memory.mcp.tools.search_notes(query, project, search_type, output_format="json")`，取 30 条按笔记去重后的前 10 篇 |
| `text` | `search_type="text"`：SQLite FTS5，tokenizer `unicode61 tokenchars 0x2F` |
| `hybrid_en` | `search_type="hybrid"`，默认嵌入 `bge-small-en-v1.5`（产品默认） |
| `hybrid_zh` | 同上，嵌入换成 `BAAI/bge-small-zh-v1.5`（与 Mem0 报告同一模型），需设 `BASIC_MEMORY_SEMANTIC_EMBEDDING_DIMENSIONS=512` |
| `vector_zh` | 同一中文模型，`search_type="vector"`（只走向量） |
| `hybrid_zh_t0` | 同 `hybrid_zh`，检索时 `min_similarity=0`（默认 `semantic_min_similarity=0.55`） |
| 环境 | Linux x86_64，2 vCPU，7 GB 内存，Python 3.12.15 |

## 2. 复现步骤

```bash
git clone https://github.com/WASD258-jpg/lingshu && cd lingshu && git checkout review/67
cd bench/review67
pip install -r requirements.txt && python fetch_data.py
export BM_STATE=/tmp/bm_en            # 必须放在本地磁盘；放在网络/FUSE 目录上 SQLite 会损坏（见 §7）
for s in selfcheck hmb_B locomo locomo_d5k zh4o_s4; do
  python bm_build.py hybrid_en $s 99999        # 可中断续做；BUDGET_S=秒数 控制单次时长
  python run.py basicmem text,hybrid_en $s     # 两配置写入相同，共用
done
export BM_STATE=/tmp/bm_zh
for s in selfcheck hmb_B locomo zh4o_s4; do
  python bm_build.py hybrid_zh $s 99999
  python run.py basicmem hybrid_zh,hybrid_zh_t0 $s
done
python run.py basicmem vector_zh hmb_B; python run.py basicmem vector_zh selfcheck
bash pairs.sh basicmem
```

实测写入耗时（2 vCPU，独占）：hmb_B 203 篇 35 秒；locomo 567 篇 103 秒；locomo_d5k 5567 篇 512 秒；zh4o_s4（中文模型）5124 篇 384 秒。检索 p50：`text` 18–47 毫秒，混合 66–435 毫秒。全部约 45 分钟。

## 3. 读数

### 3.1 逐级拆解（hmb_B，证据保留@10 / 块级命中@10）

| 配置 | 读数 | 相对上一行 Δ证据 [95% CI] |
|---|---|---|
| `text`（未装语义依赖时的默认） | 0.0 / 0.0（84/84 题返回空） | — |
| `hybrid_en`（产品默认） | 7.5 / 42.4 | +7.5 [+3.9, +11.9] |
| `hybrid_zh`（换中文模型） | 12.2 / 39.2 | +4.7 [+0.4, +8.8] |
| `vector_zh`（只走向量） | 12.2 / 39.2 | 与 hybrid_zh 读数相同 |
| `hybrid_zh_t0`（关掉 0.55 阈值） | **27.2 / 73.9** | +15.0 [+10.3, +20.4] |
| 参照 `ref_bm25` | 26.3 / 69.8 | t0 相对参照 +0.9 [−4.6, +6.9] |

### 3.2 默认配置 vs 参照基线

| 套件 | 指标 | ref_bm25 | text | hybrid_en（默认） | Δ（hybrid_en − ref）[95% CI] |
|---|---|---|---|---|---|
| hmb_B | 证据保留@10 | 26.3 | 0.0 | 7.5 | −18.8 [−24.4, −13.5] |
| locomo | hit@10 | 100.0 | 95.0 | 95.6 | −4.4 [−6.4, −2.6] |
| locomo_d5k | hit@10 | 100.0 | 98.0 | 98.8 | −1.2 [−2.2, −0.4] |
| zh4o_s4 | 证据@10 | 28.3 | 0.0 | 4.4 | −23.9 [−30.8, −17.0] |

### 3.3 中文模型配置 vs 参照基线

| 套件 | 指标 | ref_bm25 | hybrid_zh | hybrid_zh_t0 | Δ（t0 − ref）[95% CI] |
|---|---|---|---|---|---|
| hmb_B | 证据保留@10 | 26.3 | 12.2 | 27.2 | +0.9 [−4.6, +6.9] |
| locomo | hit@10 | 100.0 | 99.8 | 100.0 | +0.0 [+0.0, +0.0] |
| zh4o_s4 | 证据@10 | 28.3 | 23.9 | 23.9 | −4.4 [−10.7, +2.5] |

### 3.4 机制探针

| 探针 | 结果 |
|---|---|
| FTS5 `unicode61` 对中文 | 连续汉字段（到标点为止）是**一个 token**，只能整段或前缀匹配：「茶室」在句中 → 0 结果，句首的「秦熙」→ 命中 |
| `text` 返回空的题数 | hmb_B 84/84、zh4o_s4 159/159（整句中文问句）；locomo 只有 6/500（空格分隔关键词） |
| 不设 512 维 | `reindex` 报 `Embedding model returned 512-dimensional vectors but provider was configured for 384 dimensions`，全部向量写入失败 |
| selfcheck（原文第 20–60 字片段作查询） | text 28.6、hybrid_en 71.4、hybrid_zh 90.5、hybrid_zh_t0 95.2：片段多从汉字段中间切起，FTS5 匹配不到（同 B2），召回只能靠向量 |
| 重跑稳定性（混合检索，hmb_B） | 指标相同；77/84 题 top-10 次序完全相同，82/84 题集合相同 |

## 4. 原始输出（`bash pairs.sh basicmem`，已删去 ingest_s / p50_ms 两列）

```text
## basic-memory
"config": "text", "suite": "selfcheck", "hit@1": "28.6", "hit@10": "28.6", "MRR@10": "0.286", "题数": 21
"config": "text", "suite": "hmb_B", "证据保留@10": "0.0", "块级命中@10": "0.0", "题数": 84
"config": "text", "suite": "locomo", "hit@1": "93.0", "hit@10": "95.0", "MRR@10": "0.937", "题数": 500
"config": "text", "suite": "locomo_d5k", "hit@1": "93.6", "hit@10": "98.0", "MRR@10": "0.952", "题数": 500
"config": "text", "suite": "zh4o_s4", "证据@10": "0.0", "窗口@10": "0.0", "MRR@10": "0.000", "题数": 159
"config": "hybrid_en", "suite": "selfcheck", "hit@1": "57.1", "hit@10": "71.4", "MRR@10": "0.598", "题数": 21
"config": "hybrid_en", "suite": "hmb_B", "证据保留@10": "7.5", "块级命中@10": "42.4", "题数": 84
"config": "hybrid_en", "suite": "locomo", "hit@1": "93.2", "hit@10": "95.6", "MRR@10": "0.940", "题数": 500
"config": "hybrid_en", "suite": "locomo_d5k", "hit@1": "95.4", "hit@10": "98.8", "MRR@10": "0.967", "题数": 500
"config": "hybrid_en", "suite": "zh4o_s4", "证据@10": "4.4", "窗口@10": "8.2", "MRR@10": "0.031", "题数": 159
"config": "hybrid_zh", "suite": "selfcheck", "hit@1": "85.7", "hit@10": "90.5", "MRR@10": "0.865", "题数": 21
"config": "hybrid_zh", "suite": "hmb_B", "证据保留@10": "12.2", "块级命中@10": "39.2", "题数": 84
"config": "hybrid_zh", "suite": "locomo", "hit@1": "98.6", "hit@10": "99.8", "MRR@10": "0.992", "题数": 500
"config": "hybrid_zh", "suite": "zh4o_s4", "证据@10": "23.9", "窗口@10": "32.1", "MRR@10": "0.176", "题数": 159
"config": "vector_zh", "suite": "selfcheck", "hit@1": "81.0", "hit@10": "85.7", "MRR@10": "0.817", "题数": 21
"config": "vector_zh", "suite": "hmb_B", "证据保留@10": "12.2", "块级命中@10": "39.2", "题数": 84
"config": "hybrid_zh_t0", "suite": "selfcheck", "hit@1": "85.7", "hit@10": "95.2", "MRR@10": "0.889", "题数": 21
"config": "hybrid_zh_t0", "suite": "hmb_B", "证据保留@10": "27.2", "块级命中@10": "73.9", "题数": 84
"config": "hybrid_zh_t0", "suite": "locomo", "hit@1": "98.6", "hit@10": "100.0", "MRR@10": "0.993", "题数": 500
"config": "hybrid_zh_t0", "suite": "zh4o_s4", "证据@10": "23.9", "窗口@10": "32.1", "MRR@10": "0.176", "题数": 159
locomo_d5k hit@1        ref_bm25.default=97.8  basicmem.hybrid_en=95.4  Δ=-2.4  95%CI[-4.4, -0.4]
locomo_d5k hit@10       ref_bm25.default=100.0  basicmem.hybrid_en=98.8  Δ=-1.2  95%CI[-2.2, -0.4]
locomo_d5k MRR@10       ref_bm25.default=0.988  basicmem.hybrid_en=0.967  Δ=-0.020  95%CI[-0.035, -0.007]
hmb_B   证据保留@10      ref_bm25.default=26.3  basicmem.hybrid_en=7.5  Δ=-18.8  95%CI[-24.4, -13.5]
hmb_B   块级命中@10      ref_bm25.default=69.8  basicmem.hybrid_en=42.4  Δ=-27.4  95%CI[-36.0, -18.7]
hmb_B   证据保留@10      basicmem.hybrid_zh=12.2  basicmem.hybrid_zh_t0=27.2  Δ=+15.0  95%CI[+10.3, +20.4]
hmb_B   块级命中@10      basicmem.hybrid_zh=39.2  basicmem.hybrid_zh_t0=73.9  Δ=+34.7  95%CI[+26.2, +44.4]
hmb_B   证据保留@10      ref_bm25.default=26.3  basicmem.hybrid_zh_t0=27.2  Δ=+0.9  95%CI[-4.6, +6.9]
hmb_B   块级命中@10      ref_bm25.default=69.8  basicmem.hybrid_zh_t0=73.9  Δ=+4.1  95%CI[-3.7, +12.6]
locomo  hit@1        ref_bm25.default=98.4  basicmem.hybrid_en=93.2  Δ=-5.2  95%CI[-7.6, -3.0]
locomo  hit@10       ref_bm25.default=100.0  basicmem.hybrid_en=95.6  Δ=-4.4  95%CI[-6.4, -2.6]
locomo  MRR@10       ref_bm25.default=0.991  basicmem.hybrid_en=0.940  Δ=-0.052  95%CI[-0.073, -0.032]
locomo  hit@1        basicmem.hybrid_zh=98.6  basicmem.hybrid_zh_t0=98.6  Δ=+0.0  95%CI[-0.6, +0.6]
locomo  hit@10       basicmem.hybrid_zh=99.8  basicmem.hybrid_zh_t0=100.0  Δ=+0.2  95%CI[+0.0, +0.6]
locomo  MRR@10       basicmem.hybrid_zh=0.992  basicmem.hybrid_zh_t0=0.993  Δ=+0.001  95%CI[-0.003, +0.006]
locomo  hit@1        ref_bm25.default=98.4  basicmem.hybrid_zh_t0=98.6  Δ=+0.2  95%CI[-1.0, +1.6]
locomo  hit@10       ref_bm25.default=100.0  basicmem.hybrid_zh_t0=100.0  Δ=+0.0  95%CI[+0.0, +0.0]
locomo  MRR@10       ref_bm25.default=0.991  basicmem.hybrid_zh_t0=0.993  Δ=+0.001  95%CI[-0.005, +0.008]
zh4o_s4 证据@10        ref_bm25.default=28.3  basicmem.hybrid_en=4.4  Δ=-23.9  95%CI[-30.8, -17.0]
zh4o_s4 窗口@10        ref_bm25.default=39.6  basicmem.hybrid_en=8.2  Δ=-31.4  95%CI[-39.0, -23.3]
zh4o_s4 MRR@10       ref_bm25.default=0.217  basicmem.hybrid_en=0.031  Δ=-0.186  95%CI[-0.241, -0.129]
zh4o_s4 证据@10        basicmem.hybrid_zh=23.9  basicmem.hybrid_zh_t0=23.9  Δ=+0.0  95%CI[+0.0, +0.0]
zh4o_s4 窗口@10        basicmem.hybrid_zh=32.1  basicmem.hybrid_zh_t0=32.1  Δ=+0.0  95%CI[+0.0, +0.0]
zh4o_s4 MRR@10       basicmem.hybrid_zh=0.176  basicmem.hybrid_zh_t0=0.176  Δ=+0.000  95%CI[+0.000, +0.000]
zh4o_s4 证据@10        ref_bm25.default=28.3  basicmem.hybrid_zh_t0=23.9  Δ=-4.4  95%CI[-10.7, +2.5]
zh4o_s4 窗口@10        ref_bm25.default=39.6  basicmem.hybrid_zh_t0=32.1  Δ=-7.5  95%CI[-15.1, +0.0]
zh4o_s4 MRR@10       ref_bm25.default=0.217  basicmem.hybrid_zh_t0=0.176  Δ=-0.042  95%CI[-0.101, +0.015]
hmb_B   证据保留@10      basicmem.text=0.0  basicmem.hybrid_en=7.5  Δ=+7.5  95%CI[+3.9, +11.9]
hmb_B   块级命中@10      basicmem.text=0.0  basicmem.hybrid_en=42.4  Δ=+42.4  95%CI[+35.0, +50.3]
hmb_B   证据保留@10      basicmem.hybrid_en=7.5  basicmem.hybrid_zh=12.2  Δ=+4.7  95%CI[+0.4, +8.8]
hmb_B   块级命中@10      basicmem.hybrid_en=42.4  basicmem.hybrid_zh=39.2  Δ=-3.2  95%CI[-14.6, +7.7]
```

## 5. 结论与读数映射

| # | 结论 | 支撑读数 |
|---|---|---|
| B1 | 未装语义依赖时，basic-memory 对**整句中文问句**检索不到任何结果 | §3.4：hmb_B 84/84、zh4o_s4 159/159 返回空；§3.1 `text` 0.0 |
| B2 | B1 的原因是 FTS5 `unicode61` 不切中文：连续汉字段是一个 token | §3.4 探针；locomo 关键词查询只有 6/500 为空，`text` hit@10 95.0 |
| B3 | 产品默认混合检索（英文嵌入）在中文长文档与对话上**显著低于**参照基线 | §3.2：hmb_B −18.8、zh4o_s4 −23.9，CI 不含 0 |
| B4 | 换中文嵌入模型并关掉 0.55 相似度阈值后，hmb_B、locomo 与参照基线**无显著差异**；zh4o_s4 低 4.4 个百分点但 CI 含 0 | §3.3 |
| B5 | hmb_B 上，默认阈值 0.55 是中文模型配置的主要损失：同一索引只改阈值 +15.0 | §3.1 最后两行配置 |
| B6 | 阈值的影响取决于语料：zh4o_s4 上关掉阈值读数不变 | §3.3 zh4o_s4 两列相同 |
| B7 | 混合检索重跑不完全确定（次序有少量变动，指标不变） | §3.4 最后一行 |

## 6. 未测项与原因

| 项 | 原因 |
|---|---|
| zh4o 全量（34861 篇） | 按实测写入速度（中文模型约 13 篇/秒）单次约 45 分钟，超过本环境单个后台作业 20 分钟上限；改测前 4 段 zh4o_s4（5124 篇、159 题），所有方案都在 zh4o_s4 上给了同口径读数 |
| locomo_d5k 的中文模型配置 | 同上原因；英文默认配置已测（§3.2） |
| `vector_zh` 在 hmb_B 以外的套件 | 时间所限；hmb_B 上与 hybrid_zh 读数相同，已足够说明融合在该套件上无增益 |
| 知识图谱关系检索（`build_context`、`memory://` 链接遍历） | 需要笔记之间有 `[[wikilink]]` / 关系，三套语料都没有 |
| 云同步版、Obsidian 联动 | 需要账号或 GUI |

## 7. 可信边界

- **已验**：§3 全部读数；§3.4 全部探针；混合检索在 hmb_B 上重跑一次。
- **未验**：其他套件的重跑稳定性。
- **不确定**：B6 中阈值在 hmb_B 有影响、在 zh4o_s4 没有影响，推测与文档长度有关（hmb 每块是一段长文，与短问句的余弦相似度更低），未做长度分组验证。
- **环境注意**：状态目录放在本机 FUSE 挂载的工作区上时，两次出现 `sqlite3.DatabaseError: database disk image is malformed` / `file is not a database`；移到本地 `/tmp` 后不再出现。这是测评环境问题，不计为 basic-memory 的缺陷。

## 8. 预期结果（测前写下）与对照

| 预期 | 实测 |
|---|---|
| 纯 FTS5 对中文召回很差 | 成立，且更严重：整句问句全部为空 |
| 混合检索接近 Mem0 | 部分成立：只有换中文模型并关阈值后才接近（hmb_B 27.2 vs Mem0 27.8） |

## 9. 不适用条件

1. **中文用户、未安装语义依赖**（`text` 检索）：整句中文提问返回空（B1）。只有用空格分隔关键词、或查询正好是笔记开头的汉字段时才有结果。
2. **中文用户、使用默认嵌入模型** `bge-small-en-v1.5`：证据召回比字二元组 BM25 低 18.8–23.9 个百分点（B3）。
3. **换了中文模型但保留默认阈值 0.55、笔记是长段落**：hmb_B 上证据召回只有关阈值时的一半不到（12.2 vs 27.2，B5）。
4. **需要逐位可复现的检索结果**（审计、回归测试）：混合检索重跑时次序会变（B7）。
5. **一次导入上万篇笔记**：本环境写入约 6–13 篇/秒，5000 篇约 6–9 分钟。
6. 状态目录放在网络盘或 FUSE 挂载目录上（见 §7 环境注意）。
