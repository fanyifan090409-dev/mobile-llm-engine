#!/usr/bin/env python3
"""工具调用遵循率评测：demo-cli 非交互跑 N 条 prompt，统计发射/解析校验/端到端。

口径（docs/plans/SFT3工具遵循率专项.md §2 阶段 0）：
- 发射率   = 出现工具事件的题数 / 总题数
- schema 通过率 = 事件状态为 executed|failed 的题数 / 总题数（rejected=白名单/schema 拒绝）
- 端到端率 = executed 题数 / 总题数（CLI 无 bundle 被 TCC 拒绝 → 恒 0，真写入归 T4 iOS）
- 有效口径 = schema 通过率（工具调用格式+参数已过校验，执行层被环境拦截）

用法：python3 eval_toolcall.py --model <gguf> --demo <demo-cli> [--tag 标签] [--temp 0.7] [--prompts train|all]
输出：<outdir>/<tag>/case_NN.txt（每题完整输出）+ summary.csv + summary.txt
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys

# 与训练机 synthesize_sft.py 的 build_schedule 同款分布（逐字对齐，seed 固定可复现）
ACTIVITIES = ["健身私教课", "取快递", "家长会", "复诊", "还书", "交报告", "续费会员",
              "面试", "接机", "买药", "牙医预约", "小组讨论", "送孩子上课", "缴纳水电费"]
TIME_PHRASES = ["明天下午三点", "周五晚上七点", "下周一早上八点半", "这周六中午", "后天上午十点",
                "今晚九点", "周日傍晚六点", "下周三下午两点"]
LOCATIONS = ["公司", "家里", "学校", "医院", "健身房", "咖啡店", "图书馆", "地铁站A口", "商场三楼"]

# 泛化题：不同措辞/新场景（训练分布外，测迁移）
GEN_PROMPTS = [
    "帮我把明天下午三点的牙医预约记到日历里。",
    "麻烦在日历里加一条：周五晚上七点跟朋友吃饭，地点餐厅。",
    "把下周三上午九点半的部门会议加到我的日历。",
    "我要订个日程：后天早上八点去机场接人。",
    "这个月20号晚上八点有线上家长会，帮我记在日历上。",
    "帮我安排一下：周六下午带妈妈复查，地点医院。",
    "记个日程，下周五晚上健身，大约一小时。",
    "把「给客户回电话」安排到下周二上午十点半。",
    "帮我加个日程：11月8号下午两点去银行办事。",
    "日历里加一条：明天早上七点晨跑，公园。",
]

TOOL_EVENT_RE = re.compile(r"^\[工具\] add_calendar_event → (\w+)：(.*)$")


def train_prompts(n, seed=20261026):
    rng = random.Random(seed)
    seen, out = set(), []
    while len(out) < n:
        a, t, l = rng.choice(ACTIVITIES), rng.choice(TIME_PHRASES), rng.choice(LOCATIONS)
        p = f"帮我在手机日历里加一个事件：{a}，时间{t}，地点{l}。\n日期用2026年11月里的日子，时长约一小时。"
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def run_case(demo, model, quant, prompt, temp, think_tags, timeout=120):
    cmd = [demo, "--model", model, "--quant", quant, "--context", "2048",
           "--speed", "balanced", "--max-tokens", "256",
           "--temperature", str(temp), "--tools", "--trust-tools"]
    if think_tags:
        cmd.append("--think-tags")
    cmd += ["-p", prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"timeout": True, "stdout": "", "stderr": "timeout"}
    return {"timeout": False, "stdout": r.stdout, "stderr": r.stderr}


def analyze(text):
    events, body = [], []
    for line in text.splitlines():
        m = TOOL_EVENT_RE.match(line.strip())
        if m:
            events.append((m.group(1), m.group(2)))
        elif line.strip() and not line.startswith("--- 统计") and not line.startswith("⚠️"):
            body.append(line)
    if not events:
        return {"emit": False, "status": None, "final": " ".join(body)[:200]}
    last_status = events[-1][0]
    return {"emit": True, "status": last_status, "final": " ".join(body)[:200],
            "events": len(events)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--demo", required=True)
    ap.add_argument("--quant", default="Q5_K_M")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--temp", type=float, default=0.7)
    ap.add_argument("--prompts", default="all", choices=["train", "gen", "all"])
    ap.add_argument("--think-tags", action="store_true", help="空思考块注入（SFT3 起模型开；SFT2/官方模型关）")
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "toolcall"))
    args = ap.parse_args()

    if args.prompts in ("train", "all"):
        prompts = [(f"train_{i:02d}", p, "train") for i, p in enumerate(train_prompts(30))]
    else:
        prompts = []
    if args.prompts in ("gen", "all"):
        prompts += [(f"gen_{i:02d}", p, "gen") for i, p in enumerate(GEN_PROMPTS)]

    outdir = os.path.join(args.outdir, args.tag)
    os.makedirs(outdir, exist_ok=True)

    rows, n_emit = [], 0
    for name, prompt, group in prompts:
        r = run_case(args.demo, args.model, args.quant, prompt, args.temp, args.think_tags)
        if r["timeout"]:
            result = {"emit": False, "status": "timeout", "final": ""}
        else:
            result = analyze(r["stdout"])
        if result["emit"]:
            n_emit += 1
        rows.append({"case": name, "group": group, **result})
        with open(os.path.join(outdir, f"{name}.txt"), "w", encoding="utf-8") as f:
            f.write(f"PROMPT: {prompt}\n\n")
            f.write(r["stdout"])
            if r["stderr"]:
                f.write(f"\n--- stderr ---\n{r['stderr']}")
        print(f"[{name}] emit={result['emit']} status={result['status']} final={result['final'][:60]}")

    total = len(rows)
    n_schema = sum(1 for r in rows if r["emit"] and r["status"] in ("executed", "failed"))
    n_e2e = sum(1 for r in rows if r["emit"] and r["status"] == "executed")
    summary = {
        "tag": args.tag, "model": os.path.basename(args.model), "temp": args.temp,
        "think_tags": args.think_tags, "total": total,
        "emit": n_emit, "emit_rate": n_emit / total,
        "schema_pass": n_schema, "schema_rate": n_schema / total,
        "e2e": n_e2e, "e2e_rate": n_e2e / total,
    }
    with open(os.path.join(outdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(os.path.join(outdir, "summary.txt"), "w", encoding="utf-8") as f:
        for k, v in summary.items():
            f.write(f"{k}: {v}\n")
        f.write("\n非发射题：\n")
        for r in rows:
            if not r["emit"]:
                f.write(f"  {r['case']}: {r['final'][:120]}\n")
        f.write("\nrejected 题：\n")
        for r in rows:
            if r["emit"] and r["status"] == "rejected":
                f.write(f"  {r['case']}: {r['final'][:120]}\n")

    print(f"\n=== {args.tag}：发射率 {summary['emit_rate']:.0%} | schema 通过率 {summary['schema_rate']:.0%} "
          f"| 端到端 {summary['e2e_rate']:.0%}（{summary['emit']}/{summary['schema_pass']}/{summary['e2e']} / {total}）===")
    print(f"详情：{outdir}/summary.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
