#!/usr/bin/env bash
# 补充合成完成看护：等 synth_translate_supp.py 退出 → 全量质检 → 写 SYNTH_DONE 汇总标记
set -u
cd /home/ubuntu/llm-mobile
DONE=data/sft/SYNTH_DONE
if [ -f "$DONE" ]; then echo "$(date '+%F %T') SYNTH_DONE 已存在，看护退出"; exit 0; fi
while pgrep -f "synth_translate_supp[.]py" >/dev/null 2>&1; do sleep 300; done
echo "$(date '+%F %T') 补充合成已退出，开始全量质检"
/home/ubuntu/Miniconda3/envs/vlm/bin/python3 scripts/qc_sft.py --dir data/sft --samples 5 > data/sft/qc_report.txt 2>&1
{
  echo "supplement_finished_at=$(date '+%Y-%m-%d %H:%M:%S')"
  echo "--- 主合成 meta.json ---"
  cat data/sft/meta.json 2>/dev/null || echo "(缺失)"
  echo "--- 补充合成 meta_translate_supp.json ---"
  cat data/sft/meta_translate_supp.json 2>/dev/null || echo "(缺失)"
  echo "--- qc_report ---"
  cat data/sft/qc_report.txt
} > "$DONE"
echo "$(date '+%F %T') 看护完成，标记已写 $DONE"
