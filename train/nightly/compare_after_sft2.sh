#!/usr/bin/env bash
# 训练后自动评测链（Mac 侧，nohup 常驻轮询）：
# 等训练机 sft2_f16.done → rsync f16 → 量化五档 → eval_compare 全矩阵 → 生成对比报告。
# 冒烟已验证 eval_compare/generate_report 全路径（work/compare_smoke）。
set -u
cd "$(dirname "$0")"
BIN=/Users/fanyifan/Documents/Qoder/2026-10-23/90ee63b2/tools/llama.cpp/build/bin
WORK=work
LOG=work/compare_after_sft2.log
DONE_MARK=/home/ubuntu/llm-mobile/tools/llama_convert/sft2_f16.done
REMOTE_F16=/home/ubuntu/llm-mobile/tools/llama_convert/sft2_f16.gguf
OUTDIR=/Users/fanyifan/Documents/Qoder/2026-10-23/90ee63b2/train/gguf/qwen3-0.6b-sft2-20261026
MANIFEST=compare_manifest_final.json
PY=venv/bin/python  # 夜间 venv（含 jieba，供词级 chrF）

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
log "评测链启动，等训练机完成标记 $DONE_MARK"

# ---- 阶段 1：等 SFT2+convert 完成（每 10 分钟查一次）----
while true; do
  if ssh trainer "test -f $DONE_MARK" 2>/dev/null; then
    log "完成标记出现，开始取货"
    break
  fi
  # 训练机侧任一环节失败：放弃等待，留日志人工介入
  if ssh trainer "grep -l '两次尝试均失败\|人工介入' /home/ubuntu/llm-mobile/logs/pt2_wsd.log /home/ubuntu/llm-mobile/logs/watch_sft2.log /home/ubuntu/llm-mobile/logs/sft2_0.6b.log 2>/dev/null" | grep -q .; then
    log "FATAL 训练机侧失败（PT2/SFT2/convert），评测链退出"
    exit 1
  fi
  sleep 600
done

# ---- 阶段 2：rsync f16（--partial 防半截文件）----
rsync -a --partial -e ssh "trainer:$REMOTE_F16" "$WORK/sft2_f16.gguf"
SZ=$(stat -f %z "$WORK/sft2_f16.gguf")
if [ "$SZ" -lt 1400000000 ]; then
  log "FATAL f16 大小异常 $SZ 字节，停止"
  exit 1
fi
log "f16 已到 Mac：$SZ 字节"

# ---- 阶段 3：量化五档（IQ4_XS 叠中文 imatrix，复用 SFT1 校准集）----
mkdir -p "$OUTDIR"
cp "$WORK/sft2_f16.gguf" "$OUTDIR/qwen3-0.6b-sft2-F16.gguf"
for q in Q8_0 Q5_K_M Q4_K_M; do
  "$BIN/llama-quantize" "$WORK/sft2_f16.gguf" "$OUTDIR/qwen3-0.6b-sft2-$q.gguf" "$q" >> "$LOG" 2>&1 \
    && log "量化 $q 完成" || { log "FATAL 量化 $q 失败"; exit 1; }
done
"$BIN/llama-quantize" --imatrix "$WORK/imatrix.dat" "$WORK/sft2_f16.gguf" \
  "$OUTDIR/qwen3-0.6b-sft2-IQ4_XS.gguf" IQ4_XS >> "$LOG" 2>&1 \
  && log "量化 IQ4_XS 完成" || { log "FATAL 量化 IQ4_XS 失败"; exit 1; }
log "五档量化全部完成"

# ---- 阶段 4：全矩阵评测 ----
cat > "$MANIFEST" << EOF
{
  "corpora": {
    "target": "$PWD/$WORK/eval_corpus.txt",
    "general": "$PWD/$WORK/eval_general_corpus.txt"
  },
  "models": [
    {"tag": "orig-F16", "gguf": "$PWD/$WORK/orig_f16.gguf", "group": "orig", "quant": "F16"},
    {"tag": "orig-Q8_0", "gguf": "$PWD/$WORK/orig-Q8_0.gguf", "group": "orig", "quant": "Q8_0"},
    {"tag": "orig-Q5_K_M", "gguf": "$PWD/$WORK/orig-Q5_K_M.gguf", "group": "orig", "quant": "Q5_K_M"},
    {"tag": "orig-Q4_K_M", "gguf": "$PWD/$WORK/orig-Q4_K_M.gguf", "group": "orig", "quant": "Q4_K_M"},
    {"tag": "sft2-F16", "gguf": "$OUTDIR/qwen3-0.6b-sft2-F16.gguf", "group": "sft2", "quant": "F16"},
    {"tag": "sft2-Q8_0", "gguf": "$OUTDIR/qwen3-0.6b-sft2-Q8_0.gguf", "group": "sft2", "quant": "Q8_0"},
    {"tag": "sft2-Q5_K_M", "gguf": "$OUTDIR/qwen3-0.6b-sft2-Q5_K_M.gguf", "group": "sft2", "quant": "Q5_K_M"},
    {"tag": "sft2-Q4_K_M", "gguf": "$OUTDIR/qwen3-0.6b-sft2-Q4_K_M.gguf", "group": "sft2", "quant": "Q4_K_M"},
    {"tag": "sft2-IQ4_XS", "gguf": "$OUTDIR/qwen3-0.6b-sft2-IQ4_XS.gguf", "group": "sft2", "quant": "IQ4_XS"}
  ]
}
EOF
log "全矩阵评测开始（9 个模型）"
"$PY" eval_compare.py --manifest "$MANIFEST" --work "$WORK/compare_final" --llama-bin "$BIN" >> "$LOG" 2>&1 \
  || { log "FATAL eval_compare 失败"; exit 1; }
log "评测完成"

# ---- 阶段 5：生成报告 ----
mkdir -p ../docs/评测
"$PY" generate_report.py \
  --results "$WORK/compare_final/results.json" \
  --out ../docs/评测/0.6B训练前后对比报告.md \
  --title "0.6B 模型训练前后对比评测报告（PT2+SFT2 最终版）" \
  --headline-pair orig-F16,sft2-Q5_K_M >> "$LOG" 2>&1 \
  || { log "FATAL 报告生成失败"; exit 1; }
log "ALL_DONE 报告已生成 docs/评测/0.6B训练前后对比报告.md"
