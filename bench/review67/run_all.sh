#!/usr/bin/env bash
# 一键复跑 #67 全部读数。用法：bash run_all.sh  （需先 pip install -r requirements.txt && python fetch_data.py）
# 环境变量：LS_MAIN=上游灵枢检出（cb3a6ea）  LS_FORK=测评者 fork 检出（cef7061）  BM_ROOT=basic-memory 状态目录（必须是本地磁盘）
set -eu
cd "$(dirname "$0")"
: "${LS_MAIN:?请设 LS_MAIN}" "${LS_FORK:?请设 LS_FORK}"
BM_ROOT=${BM_ROOT:-/tmp/review67_bm}
export MEM0_TELEMETRY=False BASIC_MEMORY_LOG_LEVEL=WARNING
for s in selfcheck hmb_B locomo locomo_d5k zh4o zh4o_s4; do
  python run.py ref_bm25 default $s
  LINGSHU_SRC=$LS_MAIN python run.py lingshu legacy $s
  for c in fts_ctx fts_ctx_anchor; do LINGSHU_SRC=$LS_FORK python run.py lingshu $c $s; done
  python run.py mem0 default,dense_only $s
done
python run.py ref_bm25 default locomo_d5k_pre
LINGSHU_SRC=$LS_MAIN python run.py lingshu legacy locomo_d5k_pre
for s in selfcheck hmb_B locomo locomo_d5k zh4o_s4; do
  BM_STATE=$BM_ROOT/en python bm_build.py hybrid_en $s 99999
  BM_STATE=$BM_ROOT/en python run.py basicmem text,hybrid_en $s
done
for s in selfcheck hmb_B locomo zh4o_s4; do
  BM_STATE=$BM_ROOT/zh python bm_build.py hybrid_zh $s 99999
  BM_STATE=$BM_ROOT/zh python run.py basicmem hybrid_zh,hybrid_zh_t0 $s
done
for s in selfcheck hmb_B; do BM_STATE=$BM_ROOT/zh python run.py basicmem vector_zh $s; done
bash pairs.sh all
