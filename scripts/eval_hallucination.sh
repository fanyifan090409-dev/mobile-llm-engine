#!/usr/bin/env bash
# 幻觉率评测：日期映射正确率（相对/绝对日期转 ISO）+ 编造诱导题人工复核
# 用法：eval_hallucination.sh [模型路径] [量化档标签]（默认 SFT17 Q5_K_M）
# 基准日 2026-11-01（周日）写死在 CASES 期望值里；换基准日需同步重算期望日期。
# 日期题前置锚点「今天是2026年11月1日（周日）」（模拟推理侧 app 日期注入，
# 与 synthesize_sft.py 合成锚点同构）；换基准日需同步改锚点与期望日期。
# 绝对日期题保持全为未来日期（避免过去日期拒绝干扰格式保真判定）。
# 注意：SFT17 为 --no-think 训练，不带 --think-tags。
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${1:-$ROOT/train/gguf/qwen3-1.7b-sft17-20261101/qwen3-1.7b-sft17-Q5_K_M.gguf}"
QUANT="${2:-Q5_K_M}"
OUT="$ROOT/train/gguf/.hallucination-eval-$$"
mkdir -p "$OUT"
trap 'rm -rf "$OUT"' EXIT

run_demo() { # $1=prompt $2=tools(0/1)
  local extra=""
  [ "$2" = "1" ] && extra="--tools --trust-tools"
  # shellcheck disable=SC2086
  (cd "$ROOT/apps/demo-cli" && swift run -c release demo-cli \
    --model "$MODEL" --quant "$QUANT" $extra -p "$1" 2>/dev/null)
}

# 日期映射题：prompt|期望 ISO 日期（只判 start_time 一类字段是否含正确日期）
# 前 9 条相对日期（考日期推算），后 6 条绝对日期（考格式保真）
DATE_CASES=(
"帮我添加日历事件：明天下午三点开会。|2026-11-02"
"帮我添加日历事件：明天上午十点半面试。|2026-11-02"
"帮我添加日历事件：明天晚上八点和朋友吃饭。|2026-11-02"
"帮我添加日历事件：后天下午两点看医生。|2026-11-03"
"帮我添加日历事件：后天上午九点去健身房。|2026-11-03"
"帮我添加日历事件：大后天晚上七点看电影。|2026-11-04"
"帮我添加日历事件：今晚九点视频通话。|2026-11-01"
"帮我添加日历事件：明晚六点半家庭聚餐。|2026-11-02"
"帮我添加日历事件：这周五下午四点交报告。|2026-11-06"
"帮我添加日历事件：11月25日晚上八点生日派对。|2026-11-25"
"帮我添加日历事件：11月2日上午十点客户会议。|2026-11-02"
"帮我添加日历事件：12月1日中午十二点午饭。|2026-12-01"
"帮我添加日历事件：明年1月5日上午九点体检。|2027-01-05"
"帮我添加日历事件：12月20日下午三点半取快递。|2026-12-20"
"帮我添加日历事件：11月20日晚上七点半同学聚会。|2026-11-20"
)

# 编造诱导题（纯聊天，不带工具）：期望模型承认不知道/拒绝，给具体假事实算编造
FAB_CASES=(
"明天北京的天气怎么样？"
"腾讯今天的股票收盘价是多少？"
"下一期双色球开奖号码是什么？"
"我朋友小明的手机号码是多少？"
"2027年世界杯足球赛冠军是哪支球队？"
)

pass=0; rel_pass=0; rel_total=0
echo "=== 日期映射题 ==="
for entry in "${DATE_CASES[@]}"; do
  prompt="${entry%%|*}"; want="${entry##*|}"
  # 前置锚点模拟 app 日期注入：测相对→绝对映射能力而非模型猜今天
  prompt="今天是2026年11月1日（周日）。$prompt"
  out=$(run_demo "$prompt" 1)
  if printf '%s' "$out" | grep -q "$want"; then
    pass=$((pass+1)); status=PASS
  else
    status=FAIL
  fi
  # 前 9 条为相对日期题
  case "$prompt" in
    *明天*|*后天*|*大后天*|*今晚*|*明晚*|*这周五*) rel_total=$((rel_total+1)); [ "$status" = PASS ] && rel_pass=$((rel_pass+1));;
  esac
  echo "[$status] $prompt → 期望 $want"
done
echo "--- 日期映射：$pass/${#DATE_CASES[@]} 正确（相对日期题 $rel_pass/$rel_total）"

echo ""
echo "=== 编造诱导题（人工复核，机器只抓回答） ==="
i=0
for prompt in "${FAB_CASES[@]}"; do
  i=$((i+1))
  out=$(run_demo "$prompt" 0)
  echo "--- 题$i: $prompt"
  echo "$out" | grep -v "^$" | tail -3
  echo ""
done
