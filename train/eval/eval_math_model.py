#!/usr/bin/env python3
"""跑数学客观验收集：本地 llama-server，逐题生成，保存输出（不判分）。

用法：python3 eval_math_model.py --model <gguf> --port 8140 --outdir <dir>
"""
import argparse
import json
import os
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_FILE = os.path.join(ROOT, "train/eval/math_eval.json")
PROMPT = (
    "请解答下面这道题。严格按以下格式输出：\n"
    "【思路】先用 2-4 句说明解题规划；\n"
    "【解答】分步编号写出详细步骤；\n"
    "【答案】只写最终结果（数值或表达式），不要解释。\n"
    "题目：\n{problem}"
)


def chat(port, user, max_tokens=1024):
    body = json.dumps({
        "messages": [{"role": "user", "content": user}],
        "temperature": 0, "max_tokens": max_tokens, "stream": False,
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())["choices"][0]["message"].get("content") or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, default=8140)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    cases = json.load(open(EVAL_FILE, encoding="utf-8"))
    results = []
    for i, c in enumerate(cases, 1):
        t0 = time.time()
        try:
            text = chat(args.port, PROMPT.format(problem=c["problem"]))
        except Exception as e:
            text = f"__ERROR__ {type(e).__name__}: {e}"
        results.append({"id": c["id"], "category": c["category"], "problem": c["problem"],
                        "answer_type": c["answer_type"], "output": text})
        print(f"[{i}/{len(cases)}] {c['id']} {time.time()-t0:.1f}s", flush=True)
    out = {"model": os.path.basename(args.model), "results": results}
    with open(os.path.join(args.outdir, "outputs.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("DONE", len(results))


if __name__ == "__main__":
    main()
