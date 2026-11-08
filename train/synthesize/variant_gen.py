#!/usr/bin/env python3
"""SFT19 数学变式生成器（SymPy 数值变式）：
从合成样本池抽取可解析题面 → 多项式系数/常数/积分限扰动变式 →
SymPy 自动算真答案 → 输出变式题面 + 真答案 JSON。

解答环节不在本脚本（模板化解答会引入同构文本、训练过拟合风险）：
variants.jsonl 交给 teacher（30B 数学）补写【思路】【解答】【答案】，
答案用本脚本算好的真值硬对拍（比「teacher 答案 vs SymPy 现场算」更硬）。

只做可完全自动化的题型：多项式/有理式 求导、不定积分、定积分、求值；
应用题/文字题/级数/求根不动（LLM 依赖或变式后结构失控）。

用法：python3 variant_gen.py --dir data/sft19 --n 300 --outdir data/sft19_variants
输出：
  variants.jsonl    每行 {problem, true_answer, true_answer_num, kind, category, source_hash, vseed}
  gen_report.txt    统计报告
"""
import argparse
import glob
import json
import os
import random
import sys
from collections import Counter

import sympy
from sympy import Symbol, latex, diff, integrate

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 复用验证器的 LaTeX 清洗/解析/题型分类/题面提取（契约同一份，不复制逻辑）
from verify_math import (  # noqa: E402
    try_parse, extract_maths, problem_text, classify, MATH_CATS,
)

X = Symbol("x")
SEED = 20261102
# 支持变式的题型（其余 skip）
KINDS = {"derivative", "integral_indef", "integral_def", "evaluate"}
# 变式后题面/答案 LaTeX 最大长度（防爆炸式膨胀）
MAX_LATEX_LEN = 120
# 定积分上下限范围（小整数，保持美高难度）
DEF_BOUNDS = (-6, 6)
# 求值点：不规整小数（验证器同款策略，防凑整答案）
EVAL_POINTS = [0.13, -0.37, 0.71, -1.23, 1.79, -2.31, 2.87]

PROB_TEMPLATES = {
    "derivative": "设函数 $ f(x) = {f} $，求 $ f'(x) $。",
    "integral_indef": "求不定积分 $ \\int {f} \\, dx $。",
    "integral_def": "求定积分 $ \\int_{{{a}}}^{{{b}}} {f} \\, dx $ 的值。",
    "evaluate": "设函数 $ f(x) = {f} $，求 $ f({a}) $ 的值。",
}


def perturb_poly(poly, rng):
    """多项式系数扰动：每非零项系数乘 1-3 随机整数并随机取正负，保持常数项非零。
    poly: sympy.Poly(x)；返回扰动后展开的 Expr（None=退化不可用）。"""
    coeffs = poly.all_coeffs()  # 高次到低次
    n = len(coeffs)
    if n <= 1:
        return None
    new = []
    for c in coeffs:
        if c == 0:
            new.append(0)
            continue
        new.append(c * rng.randint(1, 3) * rng.choice([-1, 1]))
    if new[-1] == 0:
        new[-1] = rng.randint(1, 3) * rng.choice([-1, 1])
    return sum(c * X ** (n - 1 - i) for i, c in enumerate(new) if c != 0)


def perturb_expr(expr, rng):
    """对多项式/有理式做系数扰动（结构保留）；非多项式（根式/超越）返回 None。"""
    # 题面 math 块常是 f(x)=... 的 Eq 形态：取右侧表达式扰动
    if isinstance(expr, sympy.Equality):
        expr = expr.rhs
    if not expr.has(X):
        return None
    num, den = sympy.fraction(sympy.together(expr))
    if den == 1:
        p = sympy.Poly(num, X) if (num.has(X) and num.as_poly(X) is not None) else None
        if p is None:
            return None
        out = perturb_poly(p, rng)
        return sympy.expand(out) if out is not None else None
    # 有理式：分子分母都必须是 x 的多项式
    if num.as_poly(X) is None or den.as_poly(X) is None:
        return None
    pn, pd = sympy.Poly(num, X), sympy.Poly(den, X)
    if pn is None or pd is None:
        return None
    nn, nd = perturb_poly(pn, rng), perturb_poly(pd, rng)
    if nn is None or nd is None:
        return None
    nd_expanded = sympy.expand(nd)
    if nd_expanded == 0:
        return None
    return sympy.together(sympy.expand(nn) / nd_expanded)


def make_variant(expr, kind, rng):
    """生成一条变式：返回 dict 或 None（退化）。"""
    vexpr = perturb_expr(expr, rng)
    if vexpr is None:
        return None
    # 守卫：变式只能含 x 一个自由符号（多变量题面 y 混入当常数的变式语义荒谬）
    if vexpr.free_symbols - {X}:
        return None
    flatex = latex(vexpr)
    if len(flatex) > MAX_LATEX_LEN:
        return None
    rec = {"kind": kind, "vseed": rng.randint(0, 10 ** 9)}

    if kind == "derivative":
        ans = latex(sympy.simplify(diff(vexpr, X)))
        problem = PROB_TEMPLATES[kind].format(f=flatex)
        num = None
    elif kind == "integral_indef":
        ans = latex(integrate(vexpr, X)) + " + C"
        problem = PROB_TEMPLATES[kind].format(f=flatex)
        num = None
    elif kind == "integral_def":
        a = rng.randint(*DEF_BOUNDS)
        b = a + rng.randint(1, 8)
        I = integrate(vexpr, (X, a, b))
        ans = f"{latex(I)} = {float(sympy.N(I)):.4f}"
        num = f"{float(sympy.N(I)):.4f}"
        problem = PROB_TEMPLATES[kind].format(f=flatex, a=a, b=b)
    else:  # evaluate
        a = rng.choice(EVAL_POINTS)
        v = sympy.N(vexpr.subs(X, a))
        ans = f"{float(v):.4f}"
        num = f"{float(v):.4f}"
        problem = PROB_TEMPLATES[kind].format(f=flatex, a=a)

    if len(ans) > MAX_LATEX_LEN:
        return None
    rec.update({"problem": problem, "true_answer": ans, "true_answer_num": num})
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="合成样本目录（data/sft19 等）")
    ap.add_argument("--n", type=int, default=300, help="目标变式条数")
    ap.add_argument("--per-source", type=int, default=4, help="每个源题面最多产几条变式")
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    rng = random.Random(SEED)
    os.makedirs(args.outdir, exist_ok=True)

    # 1) 抽取可解析源题面（按表达式去重）
    sources = {}  # latex_key -> (expr, kind, category, source_hash)
    files = [f for f in sorted(glob.glob(os.path.join(args.dir, "*.jsonl")))
             if os.path.basename(f).replace(".jsonl", "") in MATH_CATS]
    for fn in files:
        cat = os.path.basename(fn).replace(".jsonl", "")
        with open(fn, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ptext = problem_text(rec)
                if len(ptext) < 20:
                    continue
                kind = classify(ptext)
                if kind not in KINDS:
                    continue
                maths = extract_maths(ptext)
                if not maths:
                    continue
                obj = try_parse(maths[0])
                if obj is None or not obj.has(X):
                    continue
                key = latex(sympy.together(obj))
                if key not in sources:
                    sources[key] = (obj, kind, cat, rec.get("hash", ""))

    if not sources:
        print("没有可解析的变式源题面（derivative/integral_indef/integral_def/evaluate）")
        sys.exit(1)

    # 2) 变式生成：每源每轮产 1 条，轮询保证类别均衡，直到 --n
    out = []
    degenerate = 0
    src_items = list(sources.items())
    rng.shuffle(src_items)
    for slot in range(args.per_source):
        if len(out) >= args.n:
            break
        for key, (expr, kind, cat, src_hash) in src_items:
            if len(out) >= args.n:
                break
            var = make_variant(expr, kind, rng)
            if var is None:
                degenerate += 1
                continue
            # 变式不能与原题完全相同
            if latex(sympy.together(try_parse_checked(var["problem"]))) == key:
                degenerate += 1
                continue
            var.update({"category": cat, "source_hash": src_hash})
            out.append(var)

    # 3) 落盘
    with open(os.path.join(args.outdir, "variants.jsonl"), "w", encoding="utf-8") as f:
        for rec in out:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    report = [f"dir={args.dir}",
              f"源题面 {len(sources)} 条 → 产出变式 {len(out)} 条（目标 {args.n}）",
              f"退化/失败 {degenerate} 条"]
    if out:
        report.append("类别分布: " + " | ".join(
            f"{k}×{v}" for k, v in sorted(Counter(r['category'] for r in out).items())))
        report.append("题型分布: " + " | ".join(
            f"{k}×{v}" for k, v in sorted(Counter(r['kind'] for r in out).items())))
    text = "\n".join(report)
    with open(os.path.join(args.outdir, "gen_report.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


def try_parse_checked(problem):
    """从变式题面里取回 SymPy 表达式（与源题面 key 对比防重复）。"""
    maths = extract_maths(problem)
    if not maths:
        return None
    return try_parse(maths[0])


if __name__ == "__main__":
    main()
