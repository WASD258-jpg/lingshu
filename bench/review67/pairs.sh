#!/usr/bin/env bash
# 打印各方案报告里贴的原始对照读数（只读 runs/，不重跑）。用法：bash pairs.sh lingshu|mem0|basicmem|all
set -u
cd "$(dirname "$0")"
R=runs
p() { [ -f "$R/$1.jsonl" ] && [ -f "$R/$2.jsonl" ] && python3 score.py "$R/$1.jsonl" "$R/$2.jsonl" || echo "未跑: $1 vs $2"; }
s() { [ -f "$R/$1.jsonl" ] && python3 score.py "$R/$1.jsonl" || echo "未跑: $1"; }
case "${1:-all}" in
lingshu|all)
  echo "## lingshu"
  for t in selfcheck hmb_B locomo locomo_d5k zh4o zh4o_s4; do s lingshu.legacy.$t; done
  for t in hmb_B locomo locomo_d5k zh4o zh4o_s4; do p ref_bm25.default.$t lingshu.legacy.$t; done
  for t in hmb_B locomo_d5k zh4o; do p lingshu.legacy.$t lingshu.fts_ctx.$t; p lingshu.fts_ctx.$t lingshu.fts_ctx_anchor.$t; done
  p lingshu.legacy.locomo_d5k lingshu.legacy.locomo_d5k_pre; p ref_bm25.default.locomo_d5k ref_bm25.default.locomo_d5k_pre ;;&
mem0|all)
  echo "## mem0"
  for t in selfcheck hmb_B locomo locomo_d5k zh4o zh4o_s4; do s mem0.default.$t; done
  for t in hmb_B locomo locomo_d5k zh4o zh4o_s4; do p ref_bm25.default.$t mem0.default.$t; p mem0.dense_only.$t mem0.default.$t; done ;;&
basicmem|all)
  echo "## basic-memory"
  for c in text hybrid_en hybrid_zh vector_zh hybrid_zh_t0; do for t in selfcheck hmb_B locomo locomo_d5k zh4o_s4; do [ -f $R/basicmem.$c.$t.jsonl ] && s basicmem.$c.$t; done; done
  p ref_bm25.default.locomo_d5k basicmem.hybrid_en.locomo_d5k
  for t in hmb_B locomo zh4o_s4; do p ref_bm25.default.$t basicmem.hybrid_en.$t; p basicmem.hybrid_zh.$t basicmem.hybrid_zh_t0.$t; p ref_bm25.default.$t basicmem.hybrid_zh_t0.$t; done
  p basicmem.text.hmb_B basicmem.hybrid_en.hmb_B; p basicmem.hybrid_en.hmb_B basicmem.hybrid_zh.hmb_B ;;
esac
