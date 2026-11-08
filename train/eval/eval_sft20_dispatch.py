#!/usr/bin/env python3
"""SFT20 格式验收：llama-server OpenAI 接口跑 leader/worker 提示词，统计发射/JSON/schema。

口径：
- emit     = 输出含 <tool_call> 的题数 / 总题数（leader 直答题不计入发射）
- json_ok  = <tool_call> 内 JSON 可解析的题数 / 总题数
- schema   = name + arguments 字段符合契约的题数 / 总题数
- worker_ok= leader 派到了正确工种 / worker 选对了工具
- 相对日期泄漏 = worker 结构化日期字段含相对词（应为 0）

用法：python3 eval_sft20_dispatch.py --model <gguf> --role leader|worker --port 8123 --outdir ...
"""
import argparse
import json
import os
import re
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "train/synthesize/cloud_sft20")
TC_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
REL_RE = re.compile(r"明天|后天|今天|今晚|下周|本周|这周|周[一二三四五六日天]|月底|月初|当日|当天|春节")

LEADER_PROMPTS = [
    ("calendar", "帮我约个牙医，明天下午三点，地点在口腔医院", "calendar_worker"),
    ("reminder", "明天下午三点提醒我吃药", "reminder_worker"),
    ("translate", "把这段翻译成英文：我明天不能参加会议", "translate_worker"),
    ("summary", "帮我总结一下这段：马拉松志愿服务落地滨江赛道，牵头人提前一周拉了任务清单，把物料、人员和动线逐项过了一遍。整场花费1500元，对账后结余110元。现场人员比约定时间早40分钟到位，报名名单最后停在40人。收尾点评里，督导认可了节奏控制，同时点名台账格式需要统一。", "summary_worker"),
    ("multi", "明天下午两点开会，晚上八点提醒我吃药", "calendar_worker+reminder_worker"),
    ("direct", "1+1等于几？", None),
    ("direct", "你好，简单介绍一下你自己", None),
    ("calendar", "这周六上午十点在学校开家长会，记得带成绩单", "calendar_worker"),
    ("reminder", "下周一早上八点半提醒我交报告", "reminder_worker"),
    ("translate", "把这段翻译成中文：Please confirm before Friday.", "translate_worker"),
    ("ambiguous", "帮我约个事，具体时间我发你", "calendar_worker"),
    ("multi_translate", "明天下午三点开会，另外把这段翻译成英文：会议改到四点", "calendar_worker+translate_worker"),
]

WORKER_PROMPTS = [
    ("calendar", "派单：添加日历事件：牙医复诊，明天下午三点，时长半小时，地点在口腔医院。今天是2026年11月06日。", "add_calendar_event"),
    ("calendar", "派单：添加日历事件：家长会，这周六上午十点，地点在学校，备注：带成绩单。今天是2026年11月06日。", "add_calendar_event"),
    ("reminder", "派单：设置提醒：吃药，今晚八点。今天是2026年11月06日。", "set_reminder"),
    ("reminder", "派单：设置提醒：交报告，下周一早上八点半。今天是2026年11月06日。", "set_reminder"),
    ("translate", "派单：将以下文本翻译成英文：我明天不能参加会议。今天是2026年11月06日。", "translate_text"),
    ("translate", "派单：将以下文本翻译成中文：Please confirm before Friday. 今天是2026年11月06日。", "translate_text"),
    ("summary", "派单：对以下文本进行摘要，不超过100字。\n马拉松志愿服务落地滨江赛道，牵头人提前一周拉了任务清单，把物料、人员和动线逐项过了一遍。整场花费1500元，对账后结余110元，每笔支出都附了票据照片。现场人员比约定时间早40分钟到位，报名名单最后停在40人。收尾点评里，督导认可了节奏控制，同时点名台账格式需要统一。", "summarize_text"),
    ("summary", "派单：对以下文本进行摘要，不超过80字。\n公司第三季度营收同比增长18%，主要来自海外市场。毛利率从32%提升到35%，但研发费用增加了两成。管理层计划明年在欧洲增设两个办事处，同时压缩行政开支，目标是全年利润率再提高两个百分点。", "summarize_text"),
]


def system_prompts(role):
    path = os.path.join(DATA, "leader_sft20.jsonl" if role == "leader" else "worker_sft20.jsonl")
    prompts = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            sys = next((m["content"] for m in r["messages"] if m["role"] == "system"), "")
            prompts.setdefault(r.get("task_type", "default"), sys)
    return prompts


def chat(port, system, user, max_tokens=512):
    body = json.dumps({
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())["choices"][0]["message"].get("content") or ""


def check_tool_calls(text):
    calls, parse_ok = [], True
    for js in TC_RE.findall(text):
        try:
            calls.append(json.loads(js))
        except Exception:
            parse_ok = False
    return calls, parse_ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--role", required=True, choices=["leader", "worker"])
    ap.add_argument("--port", type=int, default=8123)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--max-tokens", type=int, default=512)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    sysmap = system_prompts(args.role)
    default_sys = sysmap.get("default") or next(iter(sysmap.values()))
    prompts = LEADER_PROMPTS if args.role == "leader" else WORKER_PROMPTS

    emit = json_ok = schema = worker_ok = rel_leak = 0
    lines = []
    for i, (cat, user, expect) in enumerate(prompts, 1):
        system = sysmap.get(cat, default_sys)
        t0 = time.time()
        try:
            text = chat(args.port, system, user, args.max_tokens)
        except Exception as e:
            text = f"__ERROR__ {type(e).__name__}: {e}"
        calls, parse_ok = check_tool_calls(text)
        has_emit = bool(calls) or "<tool_call>" in text
        if has_emit:
            emit += 1
        if parse_ok:
            json_ok += 1
        ok_schema = False
        ok_worker = False
        if args.role == "leader":
            if expect is None:
                ok_schema = not has_emit
                ok_worker = not has_emit
            elif calls:
                ok_schema = all(
                    c.get("name") == "dispatch_to_worker"
                    and isinstance((c.get("arguments") or {}).get("worker"), str)
                    and isinstance((c.get("arguments") or {}).get("task"), str)
                    for c in calls)
                got = [c.get("arguments", {}).get("worker", "") for c in calls]
                ok_worker = set(got) == set(expect.split("+"))
        else:
            if calls:
                ok_schema = all(c.get("name") == expect for c in calls)
                ok_worker = ok_schema
                for c in calls:
                    a = c.get("arguments") or {}
                    for k in ("start_time", "end_time", "remind_time"):
                        v = a.get(k)
                        if isinstance(v, str) and REL_RE.search(v):
                            rel_leak += 1
        schema += int(ok_schema)
        worker_ok += int(ok_worker)
        lines.append(f"[{i:02d}] {cat} emit={has_emit} json={parse_ok} schema={ok_schema} target={ok_worker} {time.time()-t0:.1f}s")
        lines.append(f"  user: {user[:80]}")
        lines.append(f"  out : {text[:400].replace(chr(10), ' | ')}")
        with open(os.path.join(args.outdir, f"case_{i:02d}.txt"), "w", encoding="utf-8") as f:
            f.write(text)

    n = len(prompts)
    summary = "\n".join([
        f"model: {os.path.basename(args.model)}",
        f"role: {args.role}",
        f"total: {n}",
        f"emit: {emit}  emit_rate: {emit/n:.3f}",
        f"json_ok: {json_ok}  json_rate: {json_ok/n:.3f}",
        f"schema: {schema}  schema_rate: {schema/n:.3f}",
        f"target_ok: {worker_ok}  target_rate: {worker_ok/n:.3f}",
        f"relative_date_leaks: {rel_leak}",
    ])
    with open(os.path.join(args.outdir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n")
    with open(os.path.join(args.outdir, "detail.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(summary)


if __name__ == "__main__":
    main()
