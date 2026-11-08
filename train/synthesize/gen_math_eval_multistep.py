#!/usr/bin/env python3
"""多步工具轨迹：驻点 / 切线斜率 / 二阶导数 / 区间平均值。

SFTDataset 只对最后一条 assistant 算 loss，所以每条轨迹按 assistant 回合展开：
  step1 call 行、step2 call 行、……、最终 answer 行。
第二/三步的表达式由上一步的真实 CAS 结果拼出（与线上 ToolLoop 回填一致）。

输出 out_math_eval_sft/multistep_{train,val}.jsonl。
"""
import json
import math
import os
import random
import re
import subprocess
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_math_eval_sft import (USAGE_PROMPT, poly_str, poly_tex, signed,
                               integral_poly_value, parse_cas_number, close)

ROOT = os.path.dirname(os.path.dirname(HERE))
OUTDIR = os.path.join(ROOT, "train", "synthesize", "out_math_eval_sft")
BATCH = os.path.join(HERE, "cas_batch.js")
random.seed(20261109)

VAR_RE = re.compile(r"(?<![A-Za-z_])x(?![A-Za-z0-9_])")


def d_poly(terms):
    return [(c * p, p - 1) for c, p in terms if p > 0]


def eval_poly(terms, x):
    return sum(c * (x ** p) for c, p in terms)


def call_text(args):
    return "<tool_call>\n" + json.dumps({"name": "math_eval", "arguments": args},
                                        ensure_ascii=False) + "\n</tool_call>"


def tool_text(res):
    content = str(res["result"]) + ("（数值解）" if res.get("numeric") else "")
    return json.dumps({"status": res.get("status", "ok"), "result": content},
                      ensure_ascii=False, separators=(",", ":"))


def run_cas(requests):
    req = os.path.join(OUTDIR, "_multi_req.jsonl")
    res = os.path.join(OUTDIR, "_multi_res.jsonl")
    with open(req, "w", encoding="utf-8") as f:
        for r in requests:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    subprocess.run(["node", BATCH, req, res], check=True)
    out = {}
    with open(res, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["id"]] = r
    return out


def gen_cases():
    cases = []
    seen = set()

    def push(kind, problem, steps, expected, final):
        if problem in seen:
            return
        seen.add(problem)
        cid = f"multi-{len(cases) + 1:03d}"
        cases.append({"id": cid, "kind": kind, "problem": problem,
                      "steps": steps, "expected": expected, "final": final})

    # 1) 驻点：f' = 3(x-r1)(x-r2)，r1/r2 同奇偶保证整数系数
    n, guard = 0, 0
    while n < 40 and guard < 3000:
        guard += 1
        r1 = random.randint(-4, 3)
        r2 = random.randint(r1 + 1, 5)
        if (r1 + r2) % 2:
            continue
        a2 = -3 * (r1 + r2) // 2
        a1 = 3 * r1 * r2
        c0 = random.randint(-4, 4)
        f = [(1, 3), (a2, 2), (a1, 1), (c0, 0)]
        problem = f"求 $f(x)={poly_tex(f)}$ 的驻点。"
        roots = sorted([r1, r2])
        before = len(cases)
        push("stationary", problem,
             [{"op": "derivative", "expr": poly_str(f)}],
             {"kind": "set", "values": roots},
             lambda _, roots=roots: f"令 f'(x)=0，解得 x = {roots[0]} 或 x = {roots[1]}。\n【答案】{roots[0]}, {roots[1]}")
        n += len(cases) - before

    # 2) 切线斜率：f'(a)
    n, guard = 0, 0
    while n < 30 and guard < 3000:
        guard += 1
        deg = random.choice([2, 3])
        f = [(random.choice([-3, -2, -1, 1, 2, 3]), p) for p in range(deg, -1, -1)]
        f[0] = (random.choice([1, 2, 3]), deg)
        a = random.randint(-3, 3)
        slope = eval_poly(d_poly(f), a)
        problem = f"求 $f(x)={poly_tex(f)}$ 在 $x={a}$ 处的切线斜率。"
        before = len(cases)
        push("tangent", problem,
             [{"op": "derivative", "expr": poly_str(f)}],
             {"kind": "num", "value": slope, "a": a},
             lambda _, a=a, slope=slope: f"将 x = {a} 代入 f'(x)，得到切线斜率为 {slope}。\n【答案】{slope}")
        n += len(cases) - before

    # 3) 二阶导数
    n, guard = 0, 0
    while n < 30 and guard < 3000:
        guard += 1
        deg = random.choice([3, 4])
        f = [(random.choice([-3, -2, -1, 1, 2, 3]), p) for p in range(deg, -1, -1)]
        f[0] = (random.choice([1, 2, 3]), deg)
        d2 = d_poly(d_poly(f))
        problem = f"设 $f(x)={poly_tex(f)}$，求 $f''(x)$。"
        before = len(cases)
        push("second", problem,
             [{"op": "derivative", "expr": poly_str(f)}],
             {"kind": "expr", "expected_expr": poly_str(d2)},
             lambda res: f"对 f'(x) 再求一次导，得到 f''(x) = {res[-1]['result']}。\n【答案】{res[-1]['result']}")
        n += len(cases) - before

    # 4) 区间平均值 = (1/(b-a)) ∫_a^b f
    n, guard = 0, 0
    while n < 30 and guard < 3000:
        guard += 1
        deg = random.choice([1, 2])
        f = [(random.randint(-3, 3), p) for p in range(deg, -1, -1)]
        if f[0][0] == 0:
            continue
        a, b = sorted(random.sample(range(-2, 4), 2))
        total = integral_poly_value(f, a, b)
        avg = Fraction(total) / (b - a)
        problem = f"求 $f(x)={poly_tex(f)}$ 在 $[{a},{b}]$ 上的平均值。"
        before = len(cases)
        push("average", problem,
             [{"op": "integrate_def", "expr": poly_str(f), "lower": str(a), "upper": str(b)}],
             {"kind": "num", "value": float(avg), "b_minus_a": b - a},
             lambda res: f"平均值 = 定积分 ÷ 区间长度 = {res[-1]['result']}。\n【答案】{res[-1]['result']}")
        n += len(cases) - before

    return cases


def add_step2(cases, step1_results):
    for c in cases:
        r1 = step1_results[f"{c['id']}-s1"]
        if r1.get("status") != "ok":
            continue
        first = r1["result"]
        if c["kind"] == "stationary":
            c["steps"].append({"op": "solve", "expr": first + "=0"})
        elif c["kind"] == "tangent":
            c["steps"].append({"op": "eval", "expr": VAR_RE.sub(f"({c['expected']['a']})", first)})
        elif c["kind"] == "second":
            c["steps"].append({"op": "derivative", "expr": first,
                               "expected_expr": c["expected"]["expected_expr"]})
        elif c["kind"] == "average":
            c["steps"].append({"op": "eval", "expr": f"({first})/({c['expected']['b_minus_a']})"})


def verify(cases, step1_results, step2_results):
    ok_cases = []
    for c in cases:
        if len(c["steps"]) < 2:
            continue
        r1 = step1_results[f"{c['id']}-s1"]
        r2 = step2_results[f"{c['id']}-s2"]
        if r1.get("status") != "ok" or r2.get("status") != "ok":
            continue
        good = False
        try:
            if c["kind"] == "stationary":
                vals = [parse_cas_number(p) for p in r2["result"].split(",") if p.strip()]
                good = all(any(close(v, w) for v in vals) for w in c["expected"]["values"])
            elif c["kind"] == "tangent":
                good = close(parse_cas_number(r2["result"]), c["expected"]["value"])
            elif c["kind"] == "second":
                good = bool(r2.get("match"))
            elif c["kind"] == "average":
                good = close(parse_cas_number(r2["result"]), c["expected"]["value"], 1e-6)
        except Exception:
            good = False
        if good:
            ok_cases.append(c)
    return ok_cases


def make_rows(cases, step1_results, step2_results):
    rows = []
    for c in cases:
        calls = [call_text({k: v for k, v in s.items() if k != "expected_expr"})
                 for s in c["steps"]]
        results = [step1_results[f"{c['id']}-s1"], step2_results[f"{c['id']}-s2"]]
        head = [{"role": "system", "content": USAGE_PROMPT},
                {"role": "user", "content": c["problem"]}]
        msgs = head[:]
        for i, call in enumerate(calls):
            rows.append({"messages": msgs + [{"role": "assistant", "content": call}],
                         "category": "math_eval_call", "source": "math_eval_multistep"})
            msgs = msgs + [{"role": "assistant", "content": call},
                           {"role": "tool", "content": tool_text(results[i])}]
        answer = c["final"](results)
        rows.append({"messages": msgs + [{"role": "assistant", "content": answer}],
                     "category": "math_eval_answer", "source": "math_eval_multistep"})
    return rows


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    cases = gen_cases()
    req1 = [{"id": f"{c['id']}-s1", **c["steps"][0]} for c in cases]
    step1 = run_cas(req1)
    add_step2(cases, step1)
    req2 = [{"id": f"{c['id']}-s2", **c["steps"][1]} for c in cases if len(c["steps"]) > 1]
    step2 = run_cas(req2)
    cases = verify(cases, step1, step2)
    rows = make_rows(cases, step1, step2)
    random.shuffle(rows)
    n_val = max(1, len(rows) // 20)
    val, train = rows[:n_val], rows[n_val:]
    for name, data in (("train", train), ("val", val)):
        with open(os.path.join(OUTDIR, f"multistep_{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"cases": len(cases), "rows": len(rows),
                      "train": len(train), "val": len(val)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
