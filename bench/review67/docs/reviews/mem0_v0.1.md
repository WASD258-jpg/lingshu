# Mem0 检索层测评 v0.1

> dsh-bounty #67 交付物。口径见 `测评方法论_v0.1.md`。全部读数零 LLM、可离线复跑。

## 0. 意图声明

测 Mem0（`mem0ai` PyPI 包）在**离线、不调用 LLM** 的配置下，`Memory.search()` 能否把中文证据排进 top-10，并与共同量尺 `ref_bm25` 配对比较；同时用「关掉关键词分支」的对照，拆出 Mem0 自带 BM25 分支对中文的贡献。
本测评与 Mem0 无利益关系。

## 1. 被测版本与配置

| 项 | 值 |
|---|---|
| 版本 | `mem0ai==2.2.1`，`fastembed==0.9.0`，`qdrant-client==1.19.1` |
| 写入 | `Memory.add([{"role":"user","content":text}], user_id="u", infer=False, metadata={"doc_id":id})`——原文逐条入库，**不做** LLM 记忆抽取 |
| 嵌入 | fastembed `BAAI/bge-small-zh-v1.5`（512 维，本地 CPU） |
| 向量库 | Qdrant 本地目录（Mem0 2.x 的 Qdrant 后端自带 `Qdrant/bm25` 稀疏向量，做混合打分） |
| 检索 | `Memory.search(q, filters={"user_id":"u"}, top_k=10)`，其余取默认 |
| `default` | 产品默认混合打分 |
| `dense_only` | 检索期把 `vector_store.keyword_search` 换成返回 `None`（只用稠密向量）；写入与 `default` 共用 |
| 实体加分 | 依赖 spaCy；`mem0ai` 默认安装不带 spaCy，`extract_entities()` 对中英文句子都返回 `[]` → **本次未生效** |
| 环境 | Linux x86_64，2 vCPU，7 GB 内存，Python 3.12.15；`MEM0_TELEMETRY=False`，`OPENAI_API_KEY` 设为占位串（`infer=False` 路径不调用） |

## 2. 复现步骤

```bash
git clone https://github.com/WASD258-jpg/lingshu && cd lingshu && git checkout review/67
cd bench/review67
pip install -r requirements.txt
python fetch_data.py
for s in selfcheck hmb_B locomo locomo_d5k zh4o zh4o_s4; do
  python run.py ref_bm25 default $s
  python run.py mem0 default,dense_only $s     # 两个配置共用一次写入
done
bash pairs.sh mem0
```

首次运行会下载约 100 MB 的 fastembed 模型。实测写入耗时（2 vCPU）：hmb_B 10.5 秒、locomo 37.6 秒、locomo_d5k 67.6 秒、zh4o_s4 83.1 秒、zh4o 全量 257.8 秒；检索 p50 16–153 毫秒。全部约 10 分钟。

## 3. 读数

### 3.1 Mem0 默认 vs 参照基线

| 套件 | 指标 | ref_bm25 | **Mem0 default** | Δ [95% CI] |
|---|---|---|---|---|
| hmb_B | 证据保留@10 | 26.3 | **27.8** | +1.5 [−3.9, +7.5] |
| hmb_B | 块级命中@10 | 69.8 | **74.1** | +4.3 [−2.8, +12.4] |
| locomo | hit@1 | 98.4 | **95.4** | −3.0 [−4.8, −1.2] |
| locomo_d5k | hit@1 | 97.8 | **94.4** | −3.4 [−5.6, −1.2] |
| locomo_d5k | hit@10 | 100.0 | **99.8** | −0.2 [−0.6, +0.0] |
| zh4o | 证据@10 | 26.3 | **22.5** | −3.8 [−6.2, −1.3] |
| zh4o_s4 | 证据@10 | 28.3 | **19.5** | −8.8 [−15.1, −2.5] |
| selfcheck | hit@10 | 100.0 | **100.0** | 接入正确 |

### 3.2 方案内：关键词分支的贡献（dense_only → default）

| 套件 | 查询形态 | 指标 | dense_only | default | Δ [95% CI] |
|---|---|---|---|---|---|
| locomo | 空格分隔关键词 | hit@1 | 94.0 | 95.4 | +1.4 [+0.2, +2.8] |
| locomo_d5k | 空格分隔关键词 | hit@1 | 93.2 | 94.4 | +1.2 [+0.4, +2.2] |
| hmb_B | 整句中文问句 | 证据保留@10 | 27.6 | 27.8 | +0.2 [−0.7, +1.3] |
| zh4o | 整句中文问句 | 证据@10 | 22.5 | 22.5 | +0.0（1064/1068 题 top-10 逐位相同） |
| zh4o_s4 | 整句中文问句 | 证据@10 | 19.5 | 19.5 | +0.0（157/159 题 top-10 逐位相同） |

### 3.3 机制探针（`Qdrant/bm25` 稀疏编码的 token 数）

| 输入 | 稀疏 token 数 |
|---|---|
| locomo 问句「慈善跑 心理健康 发声 意识 意义」 | 5 |
| zh4o 问句「赵齐对白羽岚的昵称是什么？」 | 1 |

## 4. 原始输出（`bash pairs.sh mem0`，已删去 ingest_s / p50_ms 两列）

```text
## mem0
"config": "default", "suite": "selfcheck", "hit@1": "100.0", "hit@10": "100.0", "MRR@10": "1.000", "题数": 21
"config": "default", "suite": "hmb_B", "证据保留@10": "27.8", "块级命中@10": "74.1", "题数": 84
"config": "default", "suite": "locomo", "hit@1": "95.4", "hit@10": "100.0", "MRR@10": "0.974", "题数": 500
"config": "default", "suite": "locomo_d5k", "hit@1": "94.4", "hit@10": "99.8", "MRR@10": "0.967", "题数": 500
"config": "default", "suite": "zh4o", "证据@10": "22.5", "窗口@10": "28.2", "MRR@10": "0.155", "题数": 1068
"config": "default", "suite": "zh4o_s4", "证据@10": "19.5", "窗口@10": "25.2", "MRR@10": "0.135", "题数": 159
hmb_B   证据保留@10      ref_bm25.default=26.3  mem0.default=27.8  Δ=+1.5  95%CI[-3.9, +7.5]
hmb_B   块级命中@10      ref_bm25.default=69.8  mem0.default=74.1  Δ=+4.3  95%CI[-2.8, +12.4]
hmb_B   证据保留@10      mem0.dense_only=27.6  mem0.default=27.8  Δ=+0.2  95%CI[-0.7, +1.3]
hmb_B   块级命中@10      mem0.dense_only=72.8  mem0.default=74.1  Δ=+1.3  95%CI[+0.0, +3.8]
locomo  hit@1        ref_bm25.default=98.4  mem0.default=95.4  Δ=-3.0  95%CI[-4.8, -1.2]
locomo  hit@10       ref_bm25.default=100.0  mem0.default=100.0  Δ=+0.0  95%CI[+0.0, +0.0]
locomo  MRR@10       ref_bm25.default=0.991  mem0.default=0.974  Δ=-0.017  95%CI[-0.027, -0.007]
locomo  hit@1        mem0.dense_only=94.0  mem0.default=95.4  Δ=+1.4  95%CI[+0.2, +2.8]
locomo  hit@10       mem0.dense_only=99.6  mem0.default=100.0  Δ=+0.4  95%CI[+0.0, +1.0]
locomo  MRR@10       mem0.dense_only=0.962  mem0.default=0.974  Δ=+0.012  95%CI[+0.004, +0.021]
locomo_d5k hit@1        ref_bm25.default=97.8  mem0.default=94.4  Δ=-3.4  95%CI[-5.6, -1.2]
locomo_d5k hit@10       ref_bm25.default=100.0  mem0.default=99.8  Δ=-0.2  95%CI[-0.6, +0.0]
locomo_d5k MRR@10       ref_bm25.default=0.988  mem0.default=0.967  Δ=-0.021  95%CI[-0.035, -0.008]
locomo_d5k hit@1        mem0.dense_only=93.2  mem0.default=94.4  Δ=+1.2  95%CI[+0.4, +2.2]
locomo_d5k hit@10       mem0.dense_only=99.2  mem0.default=99.8  Δ=+0.6  95%CI[+0.0, +1.4]
locomo_d5k MRR@10       mem0.dense_only=0.956  mem0.default=0.967  Δ=+0.010  95%CI[+0.004, +0.017]
zh4o    证据@10        ref_bm25.default=26.3  mem0.default=22.5  Δ=-3.8  95%CI[-6.2, -1.3]
zh4o    窗口@10        ref_bm25.default=33.9  mem0.default=28.2  Δ=-5.7  95%CI[-8.4, -3.0]
zh4o    MRR@10       ref_bm25.default=0.211  mem0.default=0.155  Δ=-0.056  95%CI[-0.075, -0.037]
zh4o    证据@10        mem0.dense_only=22.5  mem0.default=22.5  Δ=+0.0  95%CI[+0.0, +0.0]
zh4o    窗口@10        mem0.dense_only=28.2  mem0.default=28.2  Δ=+0.0  95%CI[+0.0, +0.0]
zh4o    MRR@10       mem0.dense_only=0.155  mem0.default=0.155  Δ=-0.000  95%CI[-0.000, +0.000]
zh4o_s4 证据@10        ref_bm25.default=28.3  mem0.default=19.5  Δ=-8.8  95%CI[-15.1, -2.5]
zh4o_s4 窗口@10        ref_bm25.default=39.6  mem0.default=25.2  Δ=-14.5  95%CI[-21.4, -6.9]
zh4o_s4 MRR@10       ref_bm25.default=0.217  mem0.default=0.135  Δ=-0.082  95%CI[-0.131, -0.035]
zh4o_s4 证据@10        mem0.dense_only=19.5  mem0.default=19.5  Δ=+0.0  95%CI[+0.0, +0.0]
zh4o_s4 窗口@10        mem0.dense_only=25.2  mem0.default=25.2  Δ=+0.0  95%CI[+0.0, +0.0]
zh4o_s4 MRR@10       mem0.dense_only=0.135  mem0.default=0.135  Δ=+0.000  95%CI[+0.000, +0.000]
```

## 5. 结论与读数映射

| # | 结论 | 支撑读数 |
|---|---|---|
| M1 | 离线中文配置下，Mem0 在 hmb_B（长文档分析题）上与参照基线**无显著差异**，在 ZH-4O 角色扮演对话上**显著低于**参照基线 | §3.1 hmb_B 两行 CI 含 0；zh4o / zh4o_s4 CI 全为负 |
| M2 | 在关键词式查询的 locomo 上，hit@10 与参照基线持平，排序首位略差 | §3.1 locomo hit@1 −3.0、locomo_d5k hit@1 −3.4 |
| M3 | 5000 条无关干扰对 Mem0 几乎没有影响 | locomo 95.4 → locomo_d5k 94.4（hit@1），hit@10 100.0 → 99.8 |
| M4 | Mem0 自带的 BM25 分支**只对空格分隔的查询起作用**；整句中文问句上开关它读数不变 | §3.2：locomo +1.4 / +1.2（CI 不含 0）；hmb_B、zh4o、zh4o_s4 Δ 为 0 或 CI 含 0 |
| M5 | M4 的原因：`Qdrant/bm25` 按空白与标点切词，不切中文；一个整句中文问句只编码成 1 个 token，几乎不可能与文档 token 相等 | §3.3 |
| M6 | 重跑确定：hmb_B 两个配置重跑，runs 文件逐位相同 | 可信边界「已验」 |

## 6. 未测项与原因

| 项 | 原因 |
|---|---|
| `infer=True`（LLM 抽取记忆） | 需要 LLM，违反本悬赏零 LLM 要求，且读数会随模型与提示词漂移 |
| 默认 OpenAI 嵌入 / 托管平台 Mem0 Platform | 需要联网与密钥，不可离线复跑 |
| 实体加分、词形还原 | 依赖 spaCy（`pip install mem0ai[nlp]`），默认安装不带；且 spaCy 中文模型另需下载 |
| 图记忆（graph store） | 需要 Neo4j 等外部服务 |
| 其他嵌入模型（如 bge-m3） | 时间所限只测一个中文模型；结论 M1 可能随模型变 |
| 更新 / 删除 / 去重语义 | 本次只测检索层 |

## 7. 可信边界

- **已验**：§3 全部读数；hmb_B 重跑逐位相同；`extract_entities()` 在本环境返回空（实体加分未生效）；§3.3 token 数。
- **未验**：其他套件的重跑确定性（只重跑了 hmb_B）；装上 spaCy 后读数是否变化。
- **不确定**：zh4o 上 dense_only 与 default 有 4 题 top-10 次序不同、指标相同，原因可能是同分时的次序，未逐题追查。

## 8. 预期结果（测前写下）与对照

| 预期 | 实测 |
|---|---|
| 稠密向量在改写类问句上优于纯词法 | **不成立**：hmb_B 无显著差异，ZH-4O 反而更低 |
| Mem0 的 BM25 分支对中文贡献有限 | 成立，且更强：整句中文问句上为 0 |

## 9. 不适用条件（本次测的离线配置）

1. **中文整句提问且依赖关键词召回**：BM25 分支不分中文词（M4/M5），召回完全靠向量模型。
2. **角色扮演、闲聊式长对话**（大量短句、称呼与指代）：本配置比字二元组 BM25 低 3.8–8.8 个百分点（M1）。
3. **要求严格确定、可审计的白盒检索**：结果取决于嵌入模型权重，换模型或量化版本会改变排序。
4. **无法下载模型或 CPU 很弱的环境**：首次需下载约 100 MB 模型；zh4o 全量 34861 条写入用了 258 秒。
5. 本报告**不代表** `infer=True` 的 Mem0：那是另一条以 LLM 抽取为核心的路径，未测。
