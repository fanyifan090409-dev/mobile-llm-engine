#!/usr/bin/env python3
"""数学客观验收判分：读 outputs.json + math_eval.json，用 SymPy 对拍。

判分口径（防误杀）：
- 接受 `f'(x) = ...` 这类等式，取右侧作为答案；
- 接受 `x = ±1` 展开成两个根；
- 不定积分忽略 +C；
- 数值容差按题设置（统计题放宽）。
"""
import argparse
import json
import os
import re

import sympy as sp
from sympy.parsing.latex import parse_latex

X = sp.Symbol("x")
SAMPLES = [0.13, -0.37, 0.71, -1.23, 1.79, -2.31, 2.87]
MATH_BLOCK = re.compile(r"\$\$(.*?)\$\$|\$(.*?)\$", re.S)
NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:\s*/\s*\d+)?")
XEQ = re.compile(r"x\s*=\s*([^\s，,。;；]+)")


def clean(s):
    s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    s = s.replace("\\displaystyle", "").replace("\\left", "").replace("\\right", "")
    s = re.sub(r"\\text\{[^}]*\}", "", s)
    s = s.replace("\\,", "").replace("\\;", "").replace("\\!", "").replace("\\quad", " ")
    s = re.sub(r"e\^\{([^}]*)\}", r"\\exp(\1)", s)
    s = re.sub(r"e\^(\w)", r"\\exp(\1)", s)
    s = re.sub(r"(?<![A-Za-z\\])x\(", "x*(", s)
    s = s.replace(")(", ")*(")
    return s


def parse_one(seg):
    for fn in (lambda t: parse_latex(clean(t)),
               lambda t: sp.sympify(clean(t).replace("^", "**")),
               lambda t: sp.sympify(clean(t))):
        try:
            obj = fn(seg)
            if obj is not None:
                return obj.subs({sp.Symbol("pi"): sp.pi, sp.Symbol("e"): sp.E,
                                 sp.Symbol("i"): sp.I})
        except Exception:
            continue
    return None


def rhs_of(obj):
    """等式取右侧；x = 9 取 9；f'(x) = … 取 …。"""
    if isinstance(obj, sp.Eq):
        return obj.rhs
    return obj


def parse_seg(seg):
    """返回候选列表：处理 ±、等式右侧、+C。"""
    seg = seg.strip()
    # 不定积分常数 C 不参与对拍
    seg = re.sub(r"\+\s*C\b", "", seg)
    out = []
    if "\\pm" in seg or "±" in seg:
        for sign in ("+", "-"):
            s2 = seg.replace("\\pm", sign).replace("±", sign)
            obj = parse_one(s2)
            if obj is not None:
                out.append(rhs_of(obj))
        return out
    obj = parse_one(seg)
    if obj is not None:
        out.append(rhs_of(obj))
    # "log_2 32 = 5" 这类：等式右侧再解析一次
    if "=" in seg:
        tail = seg.rsplit("=", 1)[-1].strip()
        obj2 = parse_one(tail)
        if obj2 is not None:
            out.append(rhs_of(obj2))
    return out


def answer_block(text):
    m = re.search(r"【答案】(.*?)(?=\n【|\Z)", text, re.S)
    return m.group(1).strip() if m else text[-400:]


def to_float(obj):
    try:
        if isinstance(obj, sp.Eq) or obj in (sp.true, sp.false):
            return None
        if not obj.is_number:
            obj = sp.N(obj)
        v = complex(obj)
        return v.real if abs(v.imag) < 1e-8 else None
    except Exception:
        return None


def close(a, b, tol):
    return abs(a - b) <= tol + 1e-6 * abs(b)


def sample_match(a, b):
    ok = bad = 0
    for p in SAMPLES:
        try:
            if X not in a.free_symbols or X not in b.free_symbols:
                break
            va, vb = to_float(a.subs(X, p)), to_float(b.subs(X, p))
        except Exception:
            continue
        if va is None or vb is None:
            continue
        if close(va, vb, 1e-6):
            ok += 1
        else:
            bad += 1
    if bad:
        return False
    return True if ok else None


def candidates(block):
    out = []
    for m in MATH_BLOCK.finditer(block):
        seg = m.group(1) or m.group(2)
        out.extend(parse_seg(seg))
    # x = … 形态（含 ±）补一遍
    for m in XEQ.finditer(block):
        out.extend(parse_seg(m.group(1)))
    if not out:
        for m in NUMBER.finditer(block):
            obj = parse_one(m.group(0))
            if obj is not None:
                out.append(obj)
    return out


def judge(case, text):
    block = answer_block(text)
    cands = candidates(block)
    typ = case["answer_type"]
    tol = float(case.get("tol", 1e-6))
    if typ == "num":
        exp = sp.sympify(case["expected"])
        ev = to_float(exp)
        for c in cands[:5]:
            v = to_float(c)
            if v is not None and ev is not None and close(v, ev, tol):
                return True, f"got {v} expected {ev}"
        return False, f"cands={[str(c) for c in cands[:5]]} expected {case['expected']}"
    if typ == "expr":
        exp = sp.sympify(case["expected"])
        if X not in exp.free_symbols:
            ev = to_float(exp)
            for c in cands[:5]:
                v = to_float(c)
                if v is not None and ev is not None and close(v, ev, tol):
                    return True, f"const match {v}"
            return False, f"cands={[str(c) for c in cands[:5]]} expected {case['expected']}"
        for c in cands[:5]:
            if isinstance(c, sp.Expr) and X in c.free_symbols:
                r = sample_match(c, exp)
                if r:
                    return True, f"expr match {c}"
        return False, f"cands={[str(c) for c in cands[:5]]} expected {case['expected']}"
    if typ == "set":
        exp = [sp.sympify(e) for e in json.loads(case["expected"])]
        vals = [to_float(c) for c in cands]
        vals = [v for v in vals if v is not None]
        missing = []
        for e in exp:
            ev = to_float(e)
            if ev is None or not any(close(v, ev, tol) for v in vals):
                missing.append(str(e))
        if not missing:
            return True, f"roots match {vals}"
        return False, f"missing={missing} cands={vals} expected={[str(e) for e in exp]}"
    return False, "unknown type"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs", required=True)
    ap.add_argument("--eval", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    cases = {c["id"]: c for c in json.load(open(args.eval, encoding="utf-8"))}
    out = json.load(open(args.outputs, encoding="utf-8"))
    stats = {}
    lines = []
    for r in out["results"]:
        c = cases[r["id"]]
        ok, note = judge(c, r["output"])
        s = stats.setdefault(c["category"], [0, 0])
        s[0] += int(ok)
        s[1] += 1
        lines.append(f"[{c['category']}] {'PASS' if ok else 'FAIL'} {r['id']} {c['topic']}")
        lines.append(f"  problem: {c['problem'][:100]}")
        lines.append(f"  block  : {answer_block(r['output'])[:160].replace(chr(10), ' | ')}")
        lines.append(f"  note   : {note}")
    summary = [f"model: {out.get('model', '')}"]
    for cat, (ok, total) in stats.items():
        summary.append(f"{cat}: {ok}/{total} ({ok/total:.1%})")
    tot_ok = sum(v[0] for v in stats.values())
    tot = sum(v[1] for v in stats.values())
    summary.append(f"total: {tot_ok}/{tot} ({tot_ok/tot:.1%})")
    with open(os.path.join(args.outdir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(summary) + "\n")
    with open(os.path.join(args.outdir, "detail.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(summary))


if __name__ == "__main__":
    main()
