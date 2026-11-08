#!/usr/bin/env python3
"""CAS 二期端到端验收：模型自己决定是否调 math_eval，回填真实结果后继续答。

流程（对齐线上 ToolLoop）：
  system(usagePrompt) + user(题目) → assistant(<tool_call>…) → tool({"status":…,"result":…})
  → assistant(讲解 +【答案】)；最多 3 轮工具，超过即停止。

用法：
  python3 eval_math_e2e.py --model <gguf> --port 8140 --outdir <dir>
输出 outputs.json（results[].output 可直接交给 score_math_eval.py 判分）。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_FILE = os.path.join(ROOT, "train/eval/math_eval.json")
CAS_CLI = os.path.join(ROOT, "train/eval/cas_eval_cli.js")

# 必须与 apps/demo-cli/Sources/demo-cli/MathEvalTool.swift 的 usagePrompt 逐字一致
SYSTEM = (
    "你是数学助手。遇到需要精确计算时，第一步只输出一个工具调用块，不要输出其他内容，格式：\n"
    '<tool_call>\n{"name": "math_eval", "arguments": {"op": "eval", "expr": "x^2+3*x"}}\n</tool_call>\n'
    "expr 用 math.js 语法：乘方 ^、乘法 *、函数 sin(x)/cos(x)/exp(x)/log(x)/log(x, 底数)；不要用 LaTeX 的 {}、\\frac、\\log_2。\n"
    "op 可选 eval（求值）/ derivative（求导）/ simplify（化简）/ integrate_def（定积分）/ solve（解方程）/ stats（统计）。"
    'solve 可写 "x^2-5x+6=0"；积分与解方程用 lower/upper 给区间（可写 pi/2）；'
    "stats 用 stat_op 与 data：mean/median/variance/std/variance_pop/std_pop/iqr/sum/min/max/combination/permutation/binomial/regression/normalcdf，"
    'data 逗号分隔，regression 用 "x1,y1;x2,y2"，normalcdf 用 "mu,sigma,x"。'
    "收到工具结果后，如果还需要下一步计算就继续调用工具；否则用中文简要讲解，并在最后一行写【答案】。"
)
TC_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
ARG_KEYS = ("op", "expr", "variable", "lower", "upper", "stat_op", "data")


def chat(port, messages, max_tokens):
    body = json.dumps({
        "messages": messages, "temperature": 0, "max_tokens": max_tokens, "stream": False,
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())["choices"][0]["message"].get("content") or ""


def cas_resources():
    env = os.environ.get("CAS_RESOURCES")
    if env:
        return env
    for rel in ("apps/demo-cli/Sources/demo-cli/Resources", "eval_cas"):
        path = os.path.join(ROOT, rel)
        if os.path.exists(os.path.join(path, "math.js")):
            return path
    return os.path.join(ROOT, "eval_cas")


def loads_call(raw):
    """模型把 LaTeX 直接塞进 JSON（\\left、\\frac）时是非法 JSON；先把 LaTeX 命令的反斜杠补一层。
    注意 \\right / \\tan 会被 JSON 当成 \\r / \\t + 字母，所以字母开头的反斜杠一律先转义。"""
    fixed = re.sub(r"\\(?=[A-Za-z])", r"\\\\", raw)
    fixed = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", fixed)
    try:
        return json.loads(fixed, strict=False)
    except json.JSONDecodeError:
        return json.loads(raw, strict=False)


def cas_call(arguments):
    req = {k: str(arguments[k]) for k in ARG_KEYS if k in arguments and arguments[k] is not None}
    env = dict(os.environ)
    env["CAS_RESOURCES"] = cas_resources()
    try:
        p = subprocess.run(["node", CAS_CLI], input=json.dumps(req), text=True,
                           capture_output=True, env=env, timeout=30)
        out = json.loads(p.stdout)
    except Exception as exc:
        return {"status": "error", "result": f"CAS 执行失败：{exc}"}
    return out


def tool_content(out):
    result = str(out.get("result", ""))
    if out.get("status") == "ok" and out.get("numeric"):
        result += "（数值解）"
    return json.dumps({"status": out.get("status", "error"), "result": result},
                      ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, default=8140)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--max-tokens", type=int, default=768)
    ap.add_argument("--max-rounds", type=int, default=3)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    cases = json.load(open(EVAL_FILE, encoding="utf-8"))

    results, emitted = [], 0
    for i, c in enumerate(cases, 1):
        t0 = time.time()
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": c["problem"]}]
        tool_runs, calls, final, error = [], [], "", None
        for _ in range(args.max_rounds):
            try:
                text = chat(args.port, messages, args.max_tokens)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                break
            if not TC_RE.search(text):
                final = text
                break
            messages.append({"role": "assistant", "content": text})
            for raw in TC_RE.findall(text):
                try:
                    obj = loads_call(raw)
                    call_args = obj.get("arguments") or {}
                    if isinstance(call_args, str):
                        call_args = json.loads(call_args)
                    if not isinstance(call_args, dict):
                        raise ValueError("arguments 必须是 JSON 对象")
                    if obj.get("name") != "math_eval":
                        raise ValueError(f"未知工具 {obj.get('name')}")
                except Exception as exc:
                    tool_runs.append({"raw": raw[:200], "error": str(exc)})
                    messages.append({"role": "tool", "content": json.dumps(
                        {"status": "error", "result": f"工具调用格式错误：{exc}"},
                        ensure_ascii=False, separators=(",", ":"))})
                    continue
                calls.append(call_args)
                out = cas_call(call_args)
                tool_runs.append({"arguments": call_args, "result": out})
                messages.append({"role": "tool", "content": tool_content(out)})
        if error:
            final = f"__ERROR__ {error}"
        elif not final:
            # 最后一轮仍是工具调用：拿最后一条 assistant 文本当答案，判分自然失败
            final = messages[-1].get("content", "") if messages[-1]["role"] == "assistant" else ""
        if calls:
            emitted += 1
        results.append({
            "id": c["id"], "category": c["category"], "problem": c["problem"],
            "answer_type": c["answer_type"], "output": final,
            "calls": calls, "tool_runs": tool_runs, "error": error,
            "secs": round(time.time() - t0, 2),
        })
        print(f"[{i}/{len(cases)}] {c['id']} calls={len(calls)} {time.time()-t0:.1f}s", flush=True)

    out = {"model": os.path.basename(args.model), "results": results,
           "emit": emitted, "total": len(results)}
    with open(os.path.join(args.outdir, "outputs.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"EMIT {emitted}/{len(results)} ({emitted/len(results):.1%})")
    print("DONE", len(results))


if __name__ == "__main__":
    main()
