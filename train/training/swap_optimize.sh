#!/usr/bin/env bash
# 0.6B 续训吞吐优化「换班」脚本：到 2048 步时接管训练，换成更快配置跑完剩余步数。
#
# 流程（任一环节失败都有兜底，不会把训练搞丢）：
#   ① 轮询等待 步数≥2048 且 checkpoint-2000 已落盘（最长等 6h）
#   ② 备份 scripts + 日志 到 /home/ubuntu/backups/opt-swap-<时间戳>（训练机铁律：改在跑的东西前先备份）
#   ③ 停掉旧 torchrun（TERM，等 60s；残留进程再按具体 PID kill -9，绝不用 pkill -f 误伤）
#   ④ 分块 CE 等价性自检（loss 与 lm_head 梯度 vs 原生），FAIL 则弃用分块方案走原配置
#   ⑤ 冒烟阶梯：5 档配置各跑 10 步，取「跑通 + loss 与 v5 基准一致（±30%）+ 最快」的一档
#   ⑥ 用获胜配置 + resume_from_checkpoint 续训剩余步数（日志追加，看护脚本继续可用）
#   ⑦ PT 完成后接着跑 SFT（同一套优化开关）
#
# 无 set -e：本脚本要显式兜底（崩溃→降档重试），由每阶段自己的判断控制流向。
set -uo pipefail

export HF_ENDPOINT=https://hf-mirror.com
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
export MLFLOW_EXPERIMENT_NAME="llm-mobile"
export TOKENIZERS_PARALLELISM=false
cd /home/ubuntu/llm-mobile

VENV=/home/ubuntu/Miniconda3/envs/train/bin
TS=$(date +%Y%m%d-%H%M%S)
LOG="logs/swap_optimize.log"
PT_LOG="logs/pt_0.6b.log"
SFT_LOG="logs/sft_0.6b.log"
PT_DIR="checkpoints/qwen3-0.6b-pt-20261024"
SFT_DIR="checkpoints/qwen3-0.6b-sft-20261024"
CKPT="$PT_DIR/checkpoint-2000"
TOTAL_STEPS=4197
mkdir -p logs

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
phase() { echo "$1" | tee logs/STATUS.txt; log "$1"; }

phase "phase=swap-等待2048步与checkpoint $(date '+%F %T')"
log "===== [1/7] 等待 步数≥2048 且 $CKPT 存在（最长 6h）====="
# 恢复场景：换班已执行但训练被停掉重来时，加 --skip-wait 跳过轮询直接进流程
SKIP_WAIT="no"
[ "${1:-}" = "--skip-wait" ] && SKIP_WAIT="yes"
step=0
if [ "$SKIP_WAIT" = "yes" ]; then
  log "--skip-wait：跳过等待（恢复场景：训练已停，$CKPT 已就位）"
else
  # 每 60s 看一次日志尾部：进度条形如 " 15%|████ | 620/4197 [2:38:10<15:12:31, 15.25s/it]"
  for _ in $(seq 1 360); do
    step=$(tail -n 120 "$PT_LOG" 2>/dev/null | python3 -c \
      "import sys,re; m=re.findall(r'\| (\d+)/4197 \[', sys.stdin.read()); print(m[-1] if m else 0)" 2>/dev/null)
    if [ "${step:-0}" -ge 2048 ] && [ -d "$CKPT" ]; then
      log "条件满足：step=$step，checkpoint-2000 已落盘"
      break
    fi
    sleep 60
  done
  if [ "${step:-0}" -lt 2048 ] || [ ! -d "$CKPT" ]; then
    log "等待超时（step=${step:-?}），退出不动作，训练原样继续"
    exit 0
  fi
fi
# 无论走哪条路，没有干净的 checkpoint-2000 就绝不往下走
if [ ! -d "$CKPT" ]; then
  log "checkpoint-2000 不存在，退出（现场保留，人工确认）"
  exit 1
fi

phase "phase=swap-备份 $(date '+%F %T')"
log "===== [2/7] 备份 scripts + 日志 → /home/ubuntu/backups/opt-swap-$TS ====="
BK="/home/ubuntu/backups/opt-swap-$TS"
mkdir -p "$BK"
cp -r scripts "$BK/scripts"
cp run_0.6b.sh "$BK/"
cp -r logs "$BK/logs"
log "备份完成：$BK"

phase "phase=swap-停旧训练 $(date '+%F %T')"
log "===== [3/7] 停掉当前 torchrun（TERM 优雅退出，等 60s）====="
TPID=$(pgrep -f "torchrun --nproc_per_node=2 scripts/train_pt" | head -1)
if [ -n "$TPID" ]; then
  kill -TERM "$TPID"
  for _ in $(seq 1 60); do
    pgrep -f "scripts/train_pt.py" > /dev/null || break
    sleep 1
  done
  # 仍有残留 worker：按具体 PID 逐个 -9，绝不用 pkill -f（会误伤含同样字符串的其他进程）
  for wpid in $(pgrep -f "scripts/train_pt.py"); do
    kill -9 "$wpid" 2>/dev/null || true
  done
  log "旧训练已停（torchrun=$TPID）"
else
  log "未找到 torchrun 进程，可能已结束，继续"
fi
sleep 5

phase "phase=swap-CE等价自检 $(date '+%F %T')"
log "===== [4/7] 分块 CE 等价性自检（单卡，~2 分钟）====="
CE_OK="no"
if CUDA_VISIBLE_DEVICES=0 "$VENV/python" scripts/check_ce.py --model models/Qwen3-0.6B 2>&1 \
     | tee -a "$LOG" | grep -q "CE_EQUIVALENCE_OK"; then
  CE_OK="yes"
  log "等价自检通过"
else
  log "等价自检失败 → 弃用分块 CE，走原 bs4 配置续训（慢但安全）"
fi

phase "phase=swap-冒烟阶梯 $(date '+%F %T')"
log "===== [5/7] 冒烟阶梯：5 档配置各 10 步，取「loss 与 v5 一致 + 最快」====="
# 每档声明：名字 | 额外参数（bs/accum 固定 128/设备，与当前有效批量一致）
# 注意：全部保持梯度检查点开启（关检查点实测 28 层激活吃满 31GB，bs8 都 OOM）
declare -a NAMES=() EXTRA=() BS=() ACC=()
if [ "$CE_OK" = "yes" ]; then
  NAMES+=(v1_compile_bs16) ; EXTRA+=("--chunked-ce --torch-compile") ; BS+=(16) ; ACC+=(8)
  NAMES+=(v2_bs16)          ; EXTRA+=("--chunked-ce")             ; BS+=(16) ; ACC+=(8)
  NAMES+=(v3_bs8)           ; EXTRA+=("--chunked-ce")             ; BS+=(8)  ; ACC+=(16)
  NAMES+=(v4_bs4)           ; EXTRA+=("--chunked-ce")             ; BS+=(4)  ; ACC+=(32)
fi
# v5 兜底：原生产配置（纯 Trainer，无分块），任何情况都放最后一档
NAMES+=(v5_plain_bs4); EXTRA+=(""); BS+=(4); ACC+=(32)

declare -A RS=() RLOSS=()
: > "logs/opt_ladder_$TS.tsv"
for i in "${!NAMES[@]}"; do
  n=${NAMES[$i]}; f="logs/smoke_opt_$n.log"
  log "冒烟 $n ..."
  # timeout 1800：单档最多 30 分钟（防 torch.compile 等档位挂死拖垮整个阶梯）
  timeout 1800 "$VENV/torchrun" --nproc_per_node=2 scripts/train_pt.py --model models/Qwen3-0.6B \
    --data data/pt/fw2.bin,data/pt/belle.bin --out checkpoints/smoke_opt \
    --deepspeed scripts/ds_zero2.json --max-steps 10 --save-steps 1000000 \
    --seq-len 2048 --per-device-bs "${BS[$i]}" --grad-accum "${ACC[$i]}" \
    --logging-steps 1 --overwrite ${EXTRA[$i]} > "$f" 2>&1
  s=$(grep -oE '[0-9.]+s/it' "$f" | tail -1 | grep -oE '[0-9.]+')
  L=$(grep -oE "'loss': '[0-9.]+'" "$f" | tail -1 | grep -oE '[0-9.]+')
  if grep -q "CUDA out of memory" "$f"; then
    echo -e "$n\tOOM\t-" | tee -a "logs/opt_ladder_$TS.tsv"; log "  $n OOM，跳过"; continue
  fi
  if [ -z "$s" ]; then
    echo -e "$n\tCRASH\t-" | tee -a "logs/opt_ladder_$TS.tsv"; log "  $n 崩溃（无 s/it），跳过"; continue
  fi
  if [ -z "$L" ]; then
    echo -e "$n\tNOLOSS\t-" | tee -a "logs/opt_ladder_$TS.tsv"; log "  $n 无 loss 记录，跳过"; continue
  fi
  RS[$n]="$s"; RLOSS[$n]="$L"
  echo -e "$n\t$s\tloss=$L" | tee -a "logs/opt_ladder_$TS.tsv"
  log "  $n = ${s}s/it loss=$L"
done

# loss 相对门禁（全部跑完后统一判）：以 v5 原生 loss 为基准，各档必须落在 [0.7×, 1.3×]。
# 换相对基准的原因：绝对门禁 0<loss<10 拦不住「双卡 num_items 翻倍 → loss/梯度减半」的
# 归一化 bug（1.873 照样过关）；×gas 和 ×0.5 两类错误只有跟基准比才现形。
L5=${RLOSS[v5_plain_bs4]:-}
if [ -z "$L5" ] || ! awk "BEGIN{exit !($L5 > 2 && $L5 < 8)}"; then
  log "v5 基准档 loss 异常（=${L5:-?}），连兜底配置都不可信，退出人工介入"
  exit 1
fi
WIN=""; WIN_S="999999"
for i in "${!NAMES[@]}"; do
  n=${NAMES[$i]}; L=${RLOSS[$n]:-}; s=${RS[$n]:-}
  [ -z "$L" ] && continue
  if ! awk "BEGIN{exit !($L >= 0.7*$L5 && $L <= 1.3*$L5)}"; then
    echo -e "$n\tBADLOSS\tloss=$L（基准 $L5）" | tee -a "logs/opt_ladder_$TS.tsv"
    log "  $n loss=$L 偏离 v5 基准 $L5 超 30%，判定归一化 bug，剔除"
    continue
  fi
  # awk 比较选最快（只在 loss 达标的档里比）
  if awk "BEGIN{exit !($s < $WIN_S)}"; then WIN=$n; WIN_S=$s; fi
done
if [ -z "$WIN" ]; then
  log "全部档位失败，保留现场退出（原训练已停，需人工介入）"
  exit 1
fi
log "获胜配置：$WIN（${WIN_S}s/it，当前旧配置 15.25s/it）"
echo "OPT_WINNER $WIN ${WIN_S}s/it" >> "logs/opt_ladder_$TS.tsv"

phase "phase=swap-PT续训($WIN) $(date '+%F %T')"
log "===== [6/7] 用 $WIN 续训 PT（resume checkpoint-2000，日志追加）====="
wi=-1
for i in "${!NAMES[@]}"; do [ "${NAMES[$i]}" = "$WIN" ] && wi=$i; done
retry=0
while true; do
  log "启动 PT 续训（尝试 $((retry+1))）：bs=${BS[$wi]} accum=${ACC[$wi]} ${EXTRA[$wi]}"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_pt.py --model models/Qwen3-0.6B \
    --data data/pt/fw2.bin,data/pt/belle.bin --out "$PT_DIR" \
    --deepspeed scripts/ds_zero2.json --epochs 1 --seq-len 2048 \
    --per-device-bs "${BS[$wi]}" --grad-accum "${ACC[$wi]}" \
    --save-steps 2000 --logging-steps 10 --resume-from-checkpoint "$CKPT" \
    ${EXTRA[$wi]} >> "$PT_LOG" 2>&1
  if grep -q "TRAINING_FINISHED" <(tail -n 100 "$PT_LOG"); then
    log "PT 续训完成"
    break
  fi
  # 崩溃：降档重试（下一档），兜底 v5 也失败则退出人工介入
  retry=$((retry+1)); wi=$((wi+1))
  if [ "$wi" -ge "${#NAMES[@]}" ]; then
    log "PT 全部档位尝试失败，退出（现场保留，可 resume 重来）"
    exit 1
  fi
  log "PT 崩溃，降档重试 → ${NAMES[$wi]}"
done

phase "phase=swap-SFT微调($WIN) $(date '+%F %T')"
log "===== [7/7] SFT 2 epochs（沿用获胜配置的分块/编译开关）====="
sft_extra=$( [ "$CE_OK" = "yes" ] && echo "--chunked-ce" || echo "" )
if echo "${EXTRA[$wi]}" | grep -q "torch-compile"; then
  sft_extra="$sft_extra --torch-compile"
fi
for attempt in 1 2; do
  log "启动 SFT（尝试 $attempt）"
  "$VENV/torchrun" --nproc_per_node=2 scripts/train_sft.py \
    --model "$PT_DIR/final" --tokenizer models/Qwen3-0.6B \
    --data data/train/train.jsonl --out "$SFT_DIR" \
    --deepspeed scripts/ds_zero2.json --epochs 2 --max-len 2048 \
    --per-device-bs 16 --grad-accum 4 --save-steps 500 --logging-steps 10 \
    $sft_extra >> "$SFT_LOG" 2>&1
  if grep -q "TRAINING_FINISHED" <(tail -n 100 "$SFT_LOG"); then
    log "SFT 完成"
    break
  fi
  if [ "$attempt" = "1" ]; then
    log "SFT 崩溃，去掉 torch-compile 重试一次"
    sft_extra=$(echo "$sft_extra" | sed 's/--torch-compile//')
  else
    log "SFT 两次失败，退出（现场保留）"
    exit 1
  fi
done

phase "phase=swap-ALL_DONE 优化换班全链完成 $(date '+%F %T')"
log "SWAP_ALL_DONE winner=$WIN pt_finished sft_finished"
