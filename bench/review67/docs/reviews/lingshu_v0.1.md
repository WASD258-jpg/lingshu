# 灵枢 lingshu 检索层测评 v0.1

> dsh-bounty #67 交付物。口径见 `测评方法论_v0.1.md`。全部读数零 LLM、可离线复跑。

## 0. 意图声明

测灵枢**上游默认检索路径** `SpacetimeMemoryEngine.store.search_content(q, limit=10)` 在三套中文公开语料上能否把人工标注的证据排进 top-10，并与共同量尺 `ref_bm25` 配对比较。
**利益声明**：测评者向灵枢提交过检索相关 PR。因此本报告把**上游 main**（横评代表读数）与**测评者 fork 上未合并的开关**（§3.2）分开列，后者只作「方案内改前/改后」参考，不参与横向排序。

## 1. 被测版本与环境

| 项 | 值 |
|---|---|
| 上游 | `FuRongJun-1999/lingshu@cb3a6ea2dbd9`（2026-10-11 main） |
| 未合并开关 | `WASD258-jpg/lingshu@cef706135baa`（分支 `feat/structure-anchor`；`LINGSHU_FTS=1 LINGSHU_FTS_CONTEXT=1 [LINGSHU_ANCHOR=1]`） |
| 接入 | `adapters/lingshu.py`：逐条 `add_perception(text, importance=0.5, skip_dedup=True)`；`fts_ctx_anchor` 另写 `chapter:N` 标签（只有 hmb_B 有章号） |
| 环境 | Linux x86_64，2 vCPU，7 GB 内存，Python 3.12.15；依赖 `pyyaml jieba numpy`（灵枢自身依赖） |

## 2. 复现步骤

```bash
git clone https://github.com/WASD258-jpg/lingshu && cd lingshu && git checkout review/67
cd bench/review67
pip install -r requirements.txt                       # 锁定版本
python fetch_data.py                                  # 约 1–2 分钟，校验 sha256
git clone https://github.com/FuRongJun-1999/lingshu /tmp/ls_main && git -C /tmp/ls_main checkout cb3a6ea
git clone -b feat/structure-anchor https://github.com/WASD258-jpg/lingshu /tmp/ls_anc && git -C /tmp/ls_anc checkout cef7061
for s in selfcheck hmb_B locomo locomo_d5k locomo_d5k_pre zh4o zh4o_s4; do
  python run.py ref_bm25 default $s
  LINGSHU_SRC=/tmp/ls_main python run.py lingshu legacy $s
  for c in fts_ctx fts_ctx_anchor; do LINGSHU_SRC=/tmp/ls_anc python run.py lingshu $c $s; done
done
bash pairs.sh lingshu                                 # 打印 §4 原始输出
```

预期耗时：单个配置 hmb_B / locomo 各 < 30 秒，locomo_d5k 约 1 分钟，zh4o 约 1–2 分钟；全部约 10 分钟。

## 3. 读数

### 3.1 横评代表：上游默认 vs 参照基线（95% CI 为配对自助法）

| 套件 | 指标 | ref_bm25 | **lingshu（上游）** | Δ [95% CI] |
|---|---|---|---|---|
| hmb_B | 证据保留@10 | 26.3 | **17.6** | −8.8 [−13.0, −5.0] |
| hmb_B | 块级命中@10 | 69.8 | **62.7** | −7.1 [−14.4, −0.4] |
| locomo | hit@10 | 100.0 | **86.6** | −13.4 [−16.4, −10.4] |
| locomo_d5k | hit@10 | 100.0 | **8.8** | −91.2 [−93.6, −88.6] |
| zh4o | 证据@10 | 26.3 | **5.3** | −21.0 [−23.4, −18.4] |
| zh4o_s4 | 证据@10 | 28.3 | **5.0** | −23.3 [−29.6, −16.4] |
| selfcheck | hit@10 | 100.0 | **100.0** | 接入正确 |

### 3.2 方案内：上游 → 未合并开关（仅作改前/改后参考）

| 套件 | 指标 | legacy | fts_ctx | fts_ctx_anchor |
|---|---|---|---|---|
| hmb_B | 证据保留@10 | 17.6 | 29.6（+12.0 [+7.0, +17.5]） | 39.4（+9.9 [+5.2, +15.9]，相对 fts_ctx） |
| locomo_d5k | hit@10 | 8.8 | 99.8（+91.0 [+88.2, +93.4]） | 99.8（逐位相同） |
| zh4o | 证据@10 | 5.3 | 30.0（+24.6 [+22.1, +27.2]） | 30.0（逐位相同） |

### 3.3 机制对照：只改写入顺序

| 套件 | 写入顺序 | lingshu legacy hit@10 | ref_bm25 hit@10 |
|---|---|---|---|
| locomo_d5k | 语料先、5000 条干扰后 | 8.8 | 100.0 |
| locomo_d5k_pre | 干扰先、语料后 | 85.4（+76.6 [+72.8, +80.2]） | 100.0（逐位相同） |

## 4. 原始输出（`bash pairs.sh lingshu`，已删去 ingest_s / p50_ms 两列）

```text
## lingshu
"config": "legacy", "suite": "selfcheck", "hit@1": "100.0", "hit@10": "100.0", "MRR@10": "1.000", "题数": 21
"config": "legacy", "suite": "hmb_B", "证据保留@10": "17.6", "块级命中@10": "62.7", "题数": 84
"config": "legacy", "suite": "locomo", "hit@1": "83.8", "hit@10": "86.6", "MRR@10": "0.850", "题数": 500
"config": "legacy", "suite": "locomo_d5k", "hit@1": "7.4", "hit@10": "8.8", "MRR@10": "0.079", "题数": 500
"config": "legacy", "suite": "zh4o", "证据@10": "5.3", "窗口@10": "7.8", "MRR@10": "0.040", "题数": 1068
"config": "legacy", "suite": "zh4o_s4", "证据@10": "5.0", "窗口@10": "5.7", "MRR@10": "0.031", "题数": 159
hmb_B   证据保留@10      ref_bm25.default=26.3  lingshu.legacy=17.6  Δ=-8.8  95%CI[-13.0, -5.0]
hmb_B   块级命中@10      ref_bm25.default=69.8  lingshu.legacy=62.7  Δ=-7.1  95%CI[-14.4, -0.4]
locomo  hit@1        ref_bm25.default=98.4  lingshu.legacy=83.8  Δ=-14.6  95%CI[-17.8, -11.6]
locomo  hit@10       ref_bm25.default=100.0  lingshu.legacy=86.6  Δ=-13.4  95%CI[-16.4, -10.4]
locomo  MRR@10       ref_bm25.default=0.991  lingshu.legacy=0.850  Δ=-0.142  95%CI[-0.173, -0.113]
locomo_d5k hit@1        ref_bm25.default=97.8  lingshu.legacy=7.4  Δ=-90.4  95%CI[-93.0, -87.6]
locomo_d5k hit@10       ref_bm25.default=100.0  lingshu.legacy=8.8  Δ=-91.2  95%CI[-93.6, -88.6]
locomo_d5k MRR@10       ref_bm25.default=0.988  lingshu.legacy=0.079  Δ=-0.909  95%CI[-0.932, -0.883]
zh4o    证据@10        ref_bm25.default=26.3  lingshu.legacy=5.3  Δ=-21.0  95%CI[-23.4, -18.4]
zh4o    窗口@10        ref_bm25.default=33.9  lingshu.legacy=7.8  Δ=-26.1  95%CI[-29.0, -23.2]
zh4o    MRR@10       ref_bm25.default=0.211  lingshu.legacy=0.040  Δ=-0.171  95%CI[-0.193, -0.151]
zh4o_s4 证据@10        ref_bm25.default=28.3  lingshu.legacy=5.0  Δ=-23.3  95%CI[-29.6, -16.4]
zh4o_s4 窗口@10        ref_bm25.default=39.6  lingshu.legacy=5.7  Δ=-34.0  95%CI[-41.5, -26.4]
zh4o_s4 MRR@10       ref_bm25.default=0.217  lingshu.legacy=0.031  Δ=-0.186  95%CI[-0.243, -0.128]
hmb_B   证据保留@10      lingshu.legacy=17.6  lingshu.fts_ctx=29.6  Δ=+12.0  95%CI[+7.0, +17.5]
hmb_B   块级命中@10      lingshu.legacy=62.7  lingshu.fts_ctx=72.2  Δ=+9.4  95%CI[+1.3, +18.4]
hmb_B   证据保留@10      lingshu.fts_ctx=29.6  lingshu.fts_ctx_anchor=39.4  Δ=+9.9  95%CI[+5.2, +15.9]
hmb_B   块级命中@10      lingshu.fts_ctx=72.2  lingshu.fts_ctx_anchor=71.9  Δ=-0.2  95%CI[-0.7, +0.0]
locomo_d5k hit@1        lingshu.legacy=7.4  lingshu.fts_ctx=96.2  Δ=+88.8  95%CI[+86.0, +91.4]
locomo_d5k hit@10       lingshu.legacy=8.8  lingshu.fts_ctx=99.8  Δ=+91.0  95%CI[+88.2, +93.4]
locomo_d5k MRR@10       lingshu.legacy=0.079  lingshu.fts_ctx=0.978  Δ=+0.899  95%CI[+0.872, +0.922]
locomo_d5k hit@1        lingshu.fts_ctx=96.2  lingshu.fts_ctx_anchor=96.2  Δ=+0.0  95%CI[+0.0, +0.0]
locomo_d5k hit@10       lingshu.fts_ctx=99.8  lingshu.fts_ctx_anchor=99.8  Δ=+0.0  95%CI[+0.0, +0.0]
locomo_d5k MRR@10       lingshu.fts_ctx=0.978  lingshu.fts_ctx_anchor=0.978  Δ=+0.000  95%CI[+0.000, +0.000]
zh4o    证据@10        lingshu.legacy=5.3  lingshu.fts_ctx=30.0  Δ=+24.6  95%CI[+22.1, +27.2]
zh4o    窗口@10        lingshu.legacy=7.8  lingshu.fts_ctx=36.7  Δ=+28.9  95%CI[+26.2, +31.8]
zh4o    MRR@10       lingshu.legacy=0.040  lingshu.fts_ctx=0.233  Δ=+0.193  95%CI[+0.172, +0.215]
zh4o    证据@10        lingshu.fts_ctx=30.0  lingshu.fts_ctx_anchor=30.0  Δ=+0.0  95%CI[+0.0, +0.0]
zh4o    窗口@10        lingshu.fts_ctx=36.7  lingshu.fts_ctx_anchor=36.7  Δ=+0.0  95%CI[+0.0, +0.0]
zh4o    MRR@10       lingshu.fts_ctx=0.233  lingshu.fts_ctx_anchor=0.233  Δ=+0.000  95%CI[+0.000, +0.000]
locomo_d5k hit@1        lingshu.legacy@locomo_d5k=7.4  lingshu.legacy@locomo_d5k_pre=81.8  Δ=+74.4  95%CI[+70.2, +78.2]
locomo_d5k hit@10       lingshu.legacy@locomo_d5k=8.8  lingshu.legacy@locomo_d5k_pre=85.4  Δ=+76.6  95%CI[+72.8, +80.2]
locomo_d5k MRR@10       lingshu.legacy@locomo_d5k=0.079  lingshu.legacy@locomo_d5k_pre=0.832  Δ=+0.753  95%CI[+0.713, +0.790]
locomo_d5k hit@1        ref_bm25.default@locomo_d5k=97.8  ref_bm25.default@locomo_d5k_pre=97.8  Δ=+0.0  95%CI[+0.0, +0.0]
locomo_d5k hit@10       ref_bm25.default@locomo_d5k=100.0  ref_bm25.default@locomo_d5k_pre=100.0  Δ=+0.0  95%CI[+0.0, +0.0]
locomo_d5k MRR@10       ref_bm25.default@locomo_d5k=0.988  ref_bm25.default@locomo_d5k_pre=0.988  Δ=+0.000  95%CI[+0.000, +0.000]
```

## 5. 结论与读数映射

| # | 结论 | 支撑读数 |
|---|---|---|
| L1 | 上游默认路径在 4 个中文套件上都**低于**字二元组 BM25 参照基线（CI 全部不含 0） | §3.1 前 6 行 |
| L2 | 接入本身正确：原文片段查询 21/21 命中第 1 位 | §3.1 selfcheck |
| L3 | 上游默认路径的读数**取决于写入先后**：同一批题、同一批文档，只把干扰句从「后写」改成「先写」，hit@10 从 8.8 变为 85.4；参照基线逐位不变 | §3.3 |
| L4 | L3 的代码位置：`lingshu/core/core.py`（cb3a6ea）`search_content` 的预筛 `ORDER BY importance DESC, last_access DESC LIMIT 300`。写入时 importance 相同，候选池只保留最近写入的 300 条，更早的证据进不了打分 | §3.3 读数；代码行可直接核对 |
| L5 | 未合并的 FTS5+BM25 开关消除了 L3 的写入顺序依赖，并在三套上都显著提升；结构锚定只在问句点名章节的 hmb_B 上额外 +9.9，在没有章号的套件上读数逐位不变 | §3.2 |

## 6. 未测项与原因

| 项 | 原因 |
|---|---|
| `recall()` / 反思、冲突、遗忘等写后演化 | 本次只测检索层；`recall()` 混入 importance、近因与模式加权，口径与其他两家不对等 |
| 未合并开关里的矛盾感知 / TMS / 证据账本 | 与检索命中无关，需要专门的改写/撤回语料，不在本悬赏的三套语料上 |
| Windows / macOS | 只有 Linux 机器；作者仓库自带 Windows 时钟粒度模拟（`BENCH_CLOCK=coarse`），本次未用 |
| > 4 万条规模 | 本次最大 34861 条（zh4o 全量，分 28 个独立库） |

## 7. 可信边界

- **已验**：§3 全部读数；同一机器重跑 hmb_B、locomo_d5k、zh4o 的 runs 文件逐位相同（`diff` 为空）；fork `cef7061` 与本地开发分支的 `lingshu/` 目录逐文件相同。
- **未验**：L4 只在 locomo_d5k 上用写入顺序做了对照，zh4o（无干扰）上 legacy 读数低是否也全由 300 条截断造成，没有单独拆。
- **不确定**：hmb 引文按「整句或任意 10 字片段」定位到块，少数引文可能落在相邻块，对各方案影响相同。

## 8. 预期结果（测前写下）与对照

| 预期 | 实测 |
|---|---|
| 上游默认路径在有干扰时显著退化 | 成立：locomo_d5k hit@10 8.8 |
| FTS 开关后与参照基线同一水平 | 成立：hmb_B 29.6 vs 26.3、zh4o 30.0 vs 26.3 |

## 9. 不适用条件（上游默认路径）

1. **写入量超过约 300 条、且证据不在最近写入的 300 条里**：候选池截断（L3/L4），证据进不了打分。长对话、导入历史文档后再提问，都属这种情况。
2. **重要度全部相同**（逐条写入、未经反思调整）：截断退化为纯「最近写入优先」。
3. 问句与证据**没有共同的字片段**（同义改写、指代）：路径是纯词法匹配，召回只能靠字面重合。
4. 需要跨方案对比时不能用 fork 上的开关读数代表上游：那些开关截至 2026-10-13 未合并。
