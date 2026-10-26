#!/usr/bin/env bash
# 夜间自动链：等 SFT 完成 → 拉模型 → convert f16 → 6 档量化 → 评测 → 报告 → 红灯加训再评
# 用法：bash train/nightly/quant_eval_night.sh   （tmux 内跑）
set -u
ROOT=/Users/fanyifan/Documents/Qoder/2026-10-23/90ee63b2
NIGHTLY=$ROOT/train/nightly
LLAMA=$ROOT/tools/llama.cpp
BIN=$LLAMA/build/bin
WORK=$NIGHTLY/work
GGUF=$ROOT/train/gguf/qwen3-0.6b-sft-20261025
LOGD=$NIGHTLY/logs
SSH="ssh trainer"
REMOTE=/home/ubuntu/llm-mobile
SFT_DIR=$REMOTE/checkpoints/qwen3-0.6b-sft-20261024
VENVPY=$NIGHTLY/venv/bin/python

mkdir -p "$WORK" "$GGUF" "$LOGD"
TS=$(date +%Y%m%d_%H%M%S)
LOG=$LOGD/night_$TS.log
STATUS=$WORK/STATUS.txt
set_status() { echo "$(date '+%F %T') $1" | tee -a "$STATUS"; }
exec >> "$LOG" 2>&1
echo "===== 夜间自动链启动 $TS ====="

# ---------- 0. 工具链自检 ----------
set_status "STEP0 工具链自检"
[ -x "$BIN/llama-quantize" ] || { echo "FATAL: llama-quantize 未编译"; exit 1; }
[ -x "$BIN/llama-cli" ] || { echo "FATAL: llama-cli 未编译"; exit 1; }
IMATRIX_TOOL=$BIN/llama-importance-matrix
[ -x "$IMATRIX_TOOL" ] || IMATRIX_TOOL=$BIN/llama-imatrix
[ -x "$IMATRIX_TOOL" ] || { echo "FATAL: imatrix 工具未编译"; exit 1; }
[ -x "$BIN/llama-perplexity" ] || { echo "FATAL: llama-perplexity 未编译"; exit 1; }
[ -x "$BIN/llama-bench" ] || { echo "FATAL: llama-bench 未编译"; exit 1; }
[ -x "$VENVPY" ] || { echo "FATAL: venv 未就绪"; exit 1; }
echo "工具链 OK"

# ---------- 1. 等 SFT 完成 ----------
set_status "STEP1 等 SFT 完成"
for i in $(seq 1 180); do
  if $SSH "grep -q 'TRAINING_FINISHED' $REMOTE/logs/sft_0.6b.log 2>/dev/null"; then
    echo "SFT 完成（第 $i 次轮询）"; break
  fi
  if $SSH "grep -q '两次尝试均失败' $REMOTE/logs/sft_0.6b.log 2>/dev/null"; then
    echo "FATAL: SFT 两次尝试均失败，停止"; exit 1
  fi
  [ "$i" = 180 ] && { echo "FATAL: 3h 内 SFT 未完成，停止"; exit 1; }
  sleep 60
done

# ---------- 2. 生成 PPL/校准语料 ----------
set_status "STEP2 生成 PPL/校准语料"
$SSH "tail -500 $REMOTE/data/train/train.jsonl" > "$WORK/tail500.jsonl"
WORKX=$WORK $VENVPY - <<'PYEOF'
import json, os
from pathlib import Path
w = Path(os.environ["WORKX"])
rows = [json.loads(l) for l in (w/"tail500.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
texts = []
for r in rows:
    for m in r.get("messages", []):
        if m.get("role") == "assistant" and isinstance(m.get("content"), str):
            texts.append(m["content"])
corpus = "\n\n".join(texts)
(w/"eval_corpus.txt").write_text(corpus, encoding="utf-8")
print("语料条数:", len(texts), "字符数:", len(corpus))
PYEOF
[ -s "$WORK/eval_corpus.txt" ] || { echo "FATAL: 语料生成失败"; exit 1; }

# ---------- 3. 拉 f16 GGUF（convert 已在训练机完成，Mac 不装 torch） ----------
set_status "STEP3 拉 f16 GGUF"
if [ ! -f "$WORK/f16.gguf" ]; then
  rsync -a --partial -e ssh "trainer:$REMOTE/tools/llama_convert/qwen3-0.6b-sft-20261025-f16.gguf" "$WORK/f16.gguf"
fi
[ -f "$WORK/f16.gguf" ] || { echo "FATAL: f16.gguf 拉取失败"; exit 1; }
ls -la "$WORK/f16.gguf"

# ---------- 4. imatrix ----------
set_status "STEP4 imatrix 校准"
"$IMATRIX_TOOL" -m "$WORK/f16.gguf" -f "$WORK/eval_corpus.txt" \
  -o "$WORK/imatrix.dat" -ngl 99 -t 8 2>&1 | tail -3
[ -s "$WORK/imatrix.dat" ] || echo "WARN: imatrix 失败，跳过 IQ 档"

# ---------- 5. 量化 6 档 ----------
set_status "STEP5 量化"
# b11857 参数顺序：选项必须在位置参数（输入/输出/类型）之前，放后面会被当 nthreads
QZ() { # $1 输出名（无扩展名） $2 类型；其余为前置量化选项
  local name=$1 type=$2; shift 2
  echo "--- 量化 $name ---"
  "$BIN/llama-quantize" "$@" "$WORK/f16.gguf" "$GGUF/$name.gguf" "$type" \
    && ls -la "$GGUF/$name.gguf"
}
QZ qwen3-0.6b-sft-Q8_0 Q8_0
QZ qwen3-0.6b-sft-Q6_K Q6_K
QZ qwen3-0.6b-sft-Q5_K_M Q5_K_M
QZ qwen3-0.6b-sft-Q4_K_M Q4_K_M
# 分层比特：embedding 与输出层 q8_0，主干 Q4_K_M
QZ qwen3-0.6b-sft-Q4_K_M_emb8 Q4_K_M --token-embedding-type q8_0 --output-tensor-type q8_0
if [ -s "$WORK/imatrix.dat" ]; then
  echo "--- 量化 IQ4_XS（imatrix）---"
  "$BIN/llama-quantize" --imatrix "$WORK/imatrix.dat" "$WORK/f16.gguf" \
    "$GGUF/qwen3-0.6b-sft-IQ4_XS.gguf" IQ4_XS && ls -la "$GGUF/qwen3-0.6b-sft-IQ4_XS.gguf"
fi

# ---------- 6. bench 测速 ----------
set_status "STEP6 bench"
for g in "$GGUF"/*.gguf; do
  n=$(basename "$g" .gguf)
  "$BIN/llama-bench" -m "$g" -p 512 -n 128 -r 2 -o json > "$WORK/bench_$n.json" 2>&1 || true
done
echo "bench 完成"

# ---------- 7. PPL（4 档代表） ----------
set_status "STEP7 PPL"
for n in Q8_0 Q4_K_M Q4_K_M_emb8 IQ4_XS; do
  g="$GGUF/qwen3-0.6b-sft-$n.gguf"
  [ -f "$g" ] || continue
  echo "--- PPL $n ---"
  "$BIN/llama-perplexity" -m "$g" -f "$WORK/eval_corpus.txt" -ngl 99 -t 8 2>&1 \
    | grep -E "Final estimate" | tail -1 | tee "$WORK/ppl_$n.txt"
done

# ---------- 8. 生成评测：Q8_0 全量判定 + 其他档抽样 ----------
set_status "STEP8 生成评测"
gen_eval() { # $1 tag $2 模型路径；返回 0=通过 2=红灯
  $VENVPY "$NIGHTLY/eval_gen.py" --model "$2" --llama-cli "$BIN/llama-cli" \
    --out "$WORK/gen_$1" --tag "$1"
}
gen_eval Q8_0 "$GGUF/qwen3-0.6b-sft-Q8_0.gguf"; Q8_RC=$?
for n in Q6_K Q5_K_M Q4_K_M Q4_K_M_emb8 IQ4_XS; do
  g="$GGUF/qwen3-0.6b-sft-$n.gguf"
  [ -f "$g" ] || continue
  $VENVPY "$NIGHTLY/eval_gen.py" --model "$g" --llama-cli "$BIN/llama-cli" \
    --out "$WORK/gen_$n" --tag "$n" --sample-only || true
done

# ---------- 9. 红灯判定 → 加训 ----------
set_status "STEP9 质量判定"
if [ "$Q8_RC" = "2" ]; then
  echo "=== 质量红灯：触发训练机 SFT 加训（2 epochs, lr 5e-6）==="
  scp -q "$ROOT/train/training/train_sft_extra.sh" "trainer:$REMOTE/scripts/" || exit 1
  $SSH "chmod +x $REMOTE/scripts/train_sft_extra.sh && tmux new-session -d -s sft-extra $REMOTE/scripts/train_sft_extra.sh"
  for i in $(seq 1 120); do
    $SSH "grep -q 'TRAINING_FINISHED' $REMOTE/logs/sft_extra.log 2>/dev/null" && break
    [ "$i" = 120 ] && { echo "FATAL: 加训 2h 未完成"; exit 1; }
    sleep 60
  done
  set_status "STEP9b 加训完成，二轮评测"
  # 加训 final 在训练机直接 convert，再 rsync 回 Mac（Mac venv 无 torch）
  $SSH "cd $REMOTE/tools/llama_convert && /home/ubuntu/Miniconda3/envs/train/bin/python convert_hf_to_gguf.py $REMOTE/checkpoints/qwen3-0.6b-sft-20261024-extra/final --outfile extra_f16.gguf --outtype f16"
  rsync -a --partial -e ssh "trainer:$REMOTE/tools/llama_convert/extra_f16.gguf" "$WORK/extra_f16.gguf"
  "$BIN/llama-quantize" "$WORK/extra_f16.gguf" "$GGUF/qwen3-0.6b-sft-extra-Q4_K_M.gguf" Q4_K_M
  "$BIN/llama-quantize" --token-embedding-type q8_0 --output-tensor-type q8_0 \
    "$WORK/extra_f16.gguf" "$GGUF/qwen3-0.6b-sft-extra-Q4_K_M_emb8.gguf" Q4_K_M
  gen_eval extra-Q4_K_M "$GGUF/qwen3-0.6b-sft-extra-Q4_K_M.gguf"; RC_EXTRA=$?
  if [ "$RC_EXTRA" = "2" ]; then
    echo "=== 加训后仍红灯：停止自动链，留档人工介入 ==="
    set_status "END 加训后仍红灯（人工介入）"
  else
    echo "=== 加训后通过 ==="
    set_status "END 加训后通过"
  fi
else
  echo "=== Q8_0 生成评测通过，无需加训 ==="
  set_status "END 质量通过"
fi

# ---------- 10. 汇总报告 ----------
set_status "STEP10 汇总报告"
WORKX=$WORK GGUFX=$GGUF TSX=$TS $VENVPY - <<'PYEOF'
import json, os
from pathlib import Path
w = Path(os.environ["WORKX"]); gguf = Path(os.environ["GGUFX"])
lines = ["# 夜间自动链报告 " + os.environ["TSX"], "", "## 产物", ""]
for g in sorted(gguf.glob("*.gguf")):
    lines.append(f"- {g.name} {g.stat().st_size/1e6:.0f}MB")
lines += ["", "## 生成评测判定", ""]
for j in sorted(w.glob("gen_*/*_judge.json")):
    d = json.loads(j.read_text(encoding="utf-8"))
    lines.append(f"- {j.parent.name}: {'RED ' + ','.join(d['red_cats']) if d['red'] else 'PASS'}")
lines += ["", "## PPL", ""]
for p in sorted(w.glob("ppl_*.txt")):
    lines.append(f"### {p.stem.replace('ppl_','')}\n```\n{p.read_text(encoding='utf-8', errors='ignore').strip()}\n```")
lines += ["", "## 人工复审指引", "",
          "生成文本存档在 train/nightly/work/gen_*/ 各 txt；重点看 translate/record 两类质量，",
          "以及红灯类别（若有）的生成样本。"]
(w/"report.md").write_text("\n".join(lines), encoding="utf-8")
print("报告已写", w/"report.md")
PYEOF

echo "===== 夜间自动链结束 $(date '+%F %T') ====="
echo "NIGHT_ALL_DONE"
