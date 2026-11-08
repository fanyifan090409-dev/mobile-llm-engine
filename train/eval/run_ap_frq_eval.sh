#!/usr/bin/env bash
# AP Calc BC FRQ 评测运行器：把私有评测 JSON 逐题喂给本地模型（temperature 0），
# 输出存 train/eval/private/output/，供人工按评分标准打分。
# SFT18 加训前后用同一脚本+同一 JSON 保证可比性。
# 用法：run_ap_frq_eval.sh [模型路径] [量化档标签]
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODEL="${1:-$ROOT/train/gguf/qwen3-1.7b-sft17-20261101/qwen3-1.7b-sft17-Q5_K_M.gguf}"
QUANT="${2:-Q5_K_M}"
JSON="$ROOT/train/eval/private/ap_calc_bc_frq_2025_2026.json"
OUT="$ROOT/train/eval/private/output"
mkdir -p "$OUT"

# 逐题生成 prompt 文件（题目内容在私有 JSON 里，脚本本身不进仓库敏感内容）
python3 - "$JSON" "$OUT" <<'PYEOF'
import json, sys, os
json_path, out_dir = sys.argv[1], sys.argv[2]
data = json.load(open(json_path))
for q in data["questions"]:
    lines = ["以下是 AP 微积分 BC 自由响应题，请逐部分（A/B/C/D）作答，写出计算步骤和理由，最后给出明确答案。"]
    lines.append(f"[{q['year']} 年第 {q['num']} 题]")
    lines.append(q["statement"])
    if q.get("figure"):
        lines.append(f"[附图说明] {q['figure']}")
    for p in q["parts"]:
        lines.append(f"({p['id']}) {p['prompt']}")
    fname = os.path.join(out_dir, f"prompt-{q['year']}-q{q['num']}.txt")
    open(fname, "w").write("\n".join(lines) + "\n")
print(f"生成 {len(data['questions'])} 个 prompt")
PYEOF

for pf in "$OUT"/prompt-*.txt; do
  qtag="$(basename "$pf" .txt)"
  echo "=== $qtag ==="
  (cd "$ROOT/apps/demo-cli" && swift run -c release demo-cli \
    --model "$MODEL" --quant "$QUANT" --temperature 0 --max-tokens 1024 \
    -p "$(cat "$pf")" 2>/dev/null) | tee "$OUT/answer-$qtag.txt"
done
