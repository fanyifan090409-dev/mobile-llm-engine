#!/usr/bin/env python3
"""SFT21 领队评测：模糊指令=不派单且反问/拒答；清晰指令=派单正确；chat=不派单。

用法：python3 eval_sft21_clarify.py --model <gguf> --port 8125 --outdir <dir>
"""
import argparse
import json
import os
import re
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_FILE = os.path.join(ROOT, "train/eval/clarify_eval.json")
LEADER_SRC = os.path.join(ROOT, "train/synthesize/cloud_sft20/leader_sft20.jsonl")
TC_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
INFO_RE = re.compile(r"告诉我|先说|请问|哪一个|哪个|什么|几点|哪天|日期|名称|具体|确认|需要知道|还得知道")


def leader_system():
    with open(LEADER_SRC, encoding="utf-8") as f:
        r = json.loads(f.readline())
    return next(m["content"] for m in r["messages"] if m["role"] == "system")


def chat(port, system, user, max_tokens=384):
    body = json.dumps({
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0, "max_tokens": max_tokens, "stream": False,
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())["choices"][0]["message"].get("content") or ""


def parse_calls(text):
    calls = []
    for js in TC_RE.findall(text):
        try:
            calls.append(json.loads(js))
        except Exception:
            pass
    return calls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, default=8125)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    system = leader_system()
    cases = json.load(open(EVAL_FILE, encoding="utf-8"))
    lines = []
    stats = {"ambiguous": [0, 0], "dispatch": [0, 0], "chat": [0, 0]}

    def run(cat, user, check):
        t0 = time.time()
        try:
            text = chat(args.port, system, user)
        except Exception as e:
            text = f"__ERROR__ {type(e).__name__}: {e}"
        ok, note = check(text)
        stats[cat][0] += int(ok)
        stats[cat][1] += 1
        lines.append(f"[{cat}] {'PASS' if ok else 'FAIL'} {time.time()-t0:.1f}s {note}")
        lines.append(f"  user: {user[:80]}")
        lines.append(f"  out : {text[:400].replace(chr(10), ' | ')}")

    def check_ambiguous(expect):
        def f(text):
            calls = parse_calls(text)
            if calls or "<tool_call>" in text:
                return False, "出现工具调用"
            if not text.strip():
                return False, "空回复"
            if expect == "refuse":
                return True, ""
            if "？" not in text and "?" not in text and not INFO_RE.search(text):
                return False, "未反问"
            return True, ""
        return f

    def check_dispatch(expected):
        def f(text):
            calls = parse_calls(text)
            if not calls:
                return False, "未派单"
            if not all(c.get("name") == "dispatch_to_worker" for c in calls):
                return False, "工具名错误"
            got = [c.get("arguments", {}).get("worker", "") for c in calls]
            if set(got) != set(expected):
                return False, f"工人={got} 期望={expected}"
            return True, ""
        return f

    def check_chat(text):
        if parse_calls(text) or "<tool_call>" in text:
            return False, "chat 被派单"
        if not text.strip():
            return False, "空回复"
        return True, ""

    for c in cases["ambiguous"]:
        run("ambiguous", c["user"], check_ambiguous(c["expect"]))
    for c in cases["dispatch"]:
        run("dispatch", c["user"], check_dispatch(c["workers"]))
    for c in cases["chat"]:
        run("chat", c["user"], check_chat)

    summary = [f"model: {os.path.basename(args.model)}"]
    for cat, (ok, total) in stats.items():
        summary.append(f"{cat}: {ok}/{total} ({ok/total:.1%})")
    summary.append(f"total: {sum(v[0] for v in stats.values())}/{sum(v[1] for v in stats.values())}")
    with open(os.path.join(args.outdir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(summary) + "\n")
    with open(os.path.join(args.outdir, "detail.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(summary))


if __name__ == "__main__":
    main()
