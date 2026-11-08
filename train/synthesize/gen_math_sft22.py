#!/usr/bin/env python3
"""SFT22 数学纠错数据生成（SymPy 出题 + 正确分步解）。

针对 2026-11-08 客观评测暴露的弱项：
  AP Calc 求导（系数/乘积/商/链式）、积分、极限、切线/极值/面积；
  AP Stats 平均数/方差/正态/二项/回归/组合/IQR；Precalc 对数指数方程。

输出：train/synthesize/math_sft22/{train.jsonl,val.jsonl,stats.json}
训练机 venv 跑（需 sympy）：
  python3 gen_math_sft22.py --outdir /home/ubuntu/llm-mobile/data/train_sft22_math
"""
import argparse
import json
import os
import random
from collections import Counter

import sympy as sp

x = sp.Symbol("x")
rng = random.Random(20261108)
PROMPT = (
    "请解答下面这道题。严格按以下格式输出：\n"
    "【思路】先用 2-4 句说明解题规划（用什么方法、为什么适用）；\n"
    "【解答】分步编号写出详细步骤，每步说明理由（为什么这么做），不跳步；\n"
    "【答案】单独一行给出最终结果，并验算确认。\n"
    "题目：\n{problem}"
)


def L(expr):
    return sp.latex(expr)


def sample(problem, steps, answer, category):
    body = "【思路】" + steps[0] + "\n【解答】\n" + "\n".join(
        f"{i}. {s}" for i, s in enumerate(steps[1:], 1)) + f"\n【答案】\n$ {answer} $"
    return {"messages": [{"role": "user", "content": PROMPT.format(problem=problem)},
                         {"role": "assistant", "content": body}],
            "category": category}


def poly(deg, maxc=9):
    return sum(rng.randint(-maxc, maxc) * x**i for i in range(deg + 1) if i == deg or rng.random() < 0.8)


def nz(a=1, b=9):
    v = rng.randint(a, b)
    return v if rng.random() < 0.5 else -v


def gen_derivative_poly(n):
    out = []
    for _ in range(n):
        deg = rng.randint(2, 4)
        f = poly(deg)
        d = sp.diff(f, x)
        terms = []
        for term in sp.Add.make_args(f):
            c, e = term.as_coeff_exponent(x)
            if e == 0:
                terms.append(f"常数项 ${L(term)}$ 的导数为 $0$")
            else:
                terms.append(f"${L(term)}$ 求导得 ${L(c*e)}x^{{{e-1}}}$")
        out.append(sample(
            f"设 $f(x)={L(f)}$，求 $f'(x)$。",
            ["对多项式逐项使用幂函数求导法则 $\\frac{d}{dx}x^n=nx^{n-1}$，再把各项结果相加。",
             "写出原函数并逐项求导：",
             "；".join(terms) + "。",
             f"合并同类项，得到 $f'(x)={L(d)}$。"],
            L(d), "ap_calc"))
    return out


def gen_product(n):
    out = []
    for _ in range(n):
        if rng.random() < 0.5:
            u = sp.Integer(nz()) * x + rng.randint(-9, 9)
            v = sp.Integer(nz()) * x**2 + rng.randint(-9, 9) * x + rng.randint(-9, 9)
        else:
            u = x**rng.randint(2, 3)
            v = sp.sin(sp.Integer(nz(2, 5)) * x) if rng.random() < 0.5 else sp.exp(sp.Integer(nz(1, 3)) * x)
        f = sp.expand(u * v)
        d = sp.diff(f, x)
        du, dv = sp.diff(u, x), sp.diff(v, x)
        out.append(sample(
            f"设 $f(x)={L(f)}$，求 $f'(x)$。",
            ["识别为两个函数的乘积，使用乘积法则 $(uv)'=u'v+uv'$。",
             f"取 $u={L(u)}$，$v={L(v)}$。",
             f"分别求导：$u'={L(du)}$，$v'={L(dv)}$。",
             f"代入乘积法则：$f'(x)=({L(du)})({L(v)})+({L(u)})({L(dv)})$。",
             f"展开并合并同类项，得 $f'(x)={L(d)}$。"],
            L(d), "ap_calc"))
    return out


def gen_quotient(n):
    out = []
    for _ in range(n):
        a, b, c, d = nz(), rng.randint(-9, 9), nz(), rng.randint(-9, 9)
        u = sp.Integer(a) * x + b
        v = sp.Integer(c) * x + d
        f = u / v
        der = sp.simplify(sp.diff(f, x))
        out.append(sample(
            f"设 $f(x)={L(f)}$，求 $f'(x)$。",
            ["识别为两个函数的商，使用商法则 $\\left(\\frac{u}{v}\\right)'=\\frac{u'v-uv'}{v^2}$。",
             f"取 $u={L(u)}$，$v={L(v)}$，则 $u'={a}$，$v'={c}$。",
             f"代入公式：$f'(x)=\\frac{{{a}({L(v)})-({L(u)})({c})}}{{{L(v)}^2}}$。",
             f"分子化简：${L(sp.expand(a*v - c*u))}$，所以 $f'(x)={L(der)}$。"],
            L(der), "ap_calc"))
    return out


def gen_chain(n):
    out = []
    for _ in range(n):
        a = nz(2, 6)
        inner = sp.Integer(a) * x + rng.randint(-6, 6)
        kind = rng.choice(["sin", "cos", "exp", "ln", "sqrt", "pow"])
        if kind == "sin":
            f = sp.sin(inner)
        elif kind == "cos":
            f = sp.cos(inner)
        elif kind == "exp":
            f = sp.exp(inner)
        elif kind == "ln":
            f = sp.log(inner)
        elif kind == "sqrt":
            f = sp.sqrt(inner)
        else:
            f = inner**rng.randint(2, 4)
        der = sp.simplify(sp.diff(f, x))
        out.append(sample(
            f"设 $f(x)={L(f)}$，求 $f'(x)$。",
            ["识别为复合函数，使用链式法则：先对外层函数求导，再乘以内层函数的导数。",
             f"外层函数关于内层变量求导，内层 $u={L(inner)}$ 的导数 $u'={a}$。",
             f"组合得到 $f'(x)={L(der)}$。"],
            L(der), "ap_calc"))
    return out


def gen_integral_indef(n):
    out = []
    for _ in range(n):
        kind = rng.choice(["poly", "exp", "sin", "cos", "inv"])
        if kind == "poly":
            f = poly(rng.randint(1, 3))
        elif kind == "exp":
            f = sp.exp(sp.Integer(nz(2, 4)) * x)
        elif kind == "sin":
            f = sp.sin(sp.Integer(nz(2, 4)) * x)
        elif kind == "cos":
            f = sp.cos(sp.Integer(nz(2, 4)) * x)
        else:
            f = 1 / x
        F = sp.integrate(f, x)
        out.append(sample(
            f"求不定积分 $\\int {L(f)}\\,dx$。",
            ["使用基本积分公式逐项求原函数，最后加上积分常数 $C$。",
             f"对每一项套用公式，得到原函数 ${L(F)}$。",
             "因为不定积分表示一族函数，所以必须补上常数 $C$。"],
            L(F) + " + C", "ap_calc"))
    return out


def gen_integral_def(n):
    out = []
    for _ in range(n):
        a = rng.randint(-3, 1)
        b = a + rng.randint(1, 5)
        kind = rng.choice(["poly", "sin", "exp"])
        if kind == "poly":
            f = poly(rng.randint(1, 3))
        elif kind == "sin":
            f = sp.sin(sp.Integer(nz(1, 3)) * x)
        else:
            f = sp.exp(sp.Integer(nz(1, 2)) * x)
        F = sp.integrate(f, x)
        val = sp.simplify(F.subs(x, b) - F.subs(x, a))
        out.append(sample(
            f"求定积分 $\\int_{{{a}}}^{{{b}}} {L(f)}\\,dx$ 的值。",
            ["先求原函数，再用微积分基本定理代入上下限相减。",
             f"原函数为 ${L(F)}$。",
             f"代入上限 $x={b}$ 和下限 $x={a}$：$F({b})-F({a})={L(val)}$。"],
            L(val), "ap_calc"))
    return out


def gen_integral_sub(n):
    out = []
    for _ in range(n):
        a = nz(2, 4)
        f = x * sp.exp(sp.Integer(a) * x**2)
        F = sp.integrate(f, x)
        out.append(sample(
            f"求不定积分 $\\int {L(f)}\\,dx$。",
            [f"令 $u={a}x^2$，则 $du={2*a}x\\,dx$，可把 $x\\,dx$ 换成 $\\frac{{du}}{{{2*a}}}$。",
             f"原积分化为 $\\frac{{1}}{{{2*a}}}\\int e^u\\,du=\\frac{{1}}{{{2*a}}}e^u+C$。",
             f"回代 $u={a}x^2$，得到 ${L(F)}+C$。"],
            L(F) + " + C", "ap_calc"))
    return out


def gen_limit(n):
    out = []
    for _ in range(n):
        kind = rng.choice(["inf", "factor", "sqrt"])
        if kind == "inf":
            a, b = nz(1, 9), nz(1, 9)
            c, d = nz(1, 9), nz(1, 9)
            f = (sp.Integer(a) * x**2 + rng.randint(-9, 9) * x + rng.randint(-9, 9)) / (
                sp.Integer(c) * x**2 + rng.randint(-9, 9) * x + rng.randint(-9, 9))
            val = sp.limit(f, x, sp.oo)
            out.append(sample(
                f"求极限 $\\lim_{{x\\to\\infty}}{L(f)}$。",
                ["分子分母同除以最高次幂 $x^2$，再让 $x\\to\\infty$，低次项趋于 $0$。",
                 f"同除后极限等于最高次项系数之比，即 ${L(val)}$。"],
                L(val), "ap_calc"))
        elif kind == "factor":
            r = rng.randint(-4, 4)
            f = (x**2 - r**2) / (x - r)
            val = sp.limit(f, x, r)
            out.append(sample(
                f"求极限 $\\lim_{{x\\to {r}}}{L(f)}$。",
                [f"直接代入会得到 $\\frac{{0}}{{0}}$，先把分子因式分解：$x^2-{r**2}=(x-{r})(x+{r})$。",
                 f"约去公因子 $x-{r}$（$x\\ne {r}$），得到 $x+{r}$。",
                 f"再代入 $x={r}$，极限为 ${r+r}$。"],
                L(val), "ap_calc"))
        else:
            a = rng.randint(1, 9)
            f = (sp.sqrt(x) - sp.sqrt(a)) / (x - a)
            val = sp.limit(f, x, a)
            out.append(sample(
                f"求极限 $\\lim_{{x\\to {a}}}{L(f)}$。",
                [f"分子分母同乘共轭 $\\sqrt{{x}}+\\sqrt{{{a}}}$，把分子有理化。",
                 f"分子变为 $x-{a}$，与分母约去，得到 $\\frac{{1}}{{\\sqrt{{x}}+\\sqrt{{{a}}}}}$。",
                 f"代入 $x={a}$，极限为 ${L(val)}$。"],
                L(val), "ap_calc"))
    return out


def gen_applications(n):
    out = []
    for _ in range(n):
        kind = rng.choice(["tangent", "second", "critical", "area"])
        if kind == "tangent":
            f = poly(rng.randint(2, 3))
            a = rng.randint(-3, 3)
            slope = sp.diff(f, x).subs(x, a)
            out.append(sample(
                f"设 $f(x)={L(f)}$，求曲线在 $x={a}$ 处的切线斜率。",
                [f"切线斜率等于导数在 $x={a}$ 处的值，先求 $f'(x)={L(sp.diff(f,x))}$。",
                 f"代入 $x={a}$，得到斜率 ${L(slope)}$。"],
                L(slope), "ap_calc"))
        elif kind == "second":
            f = poly(rng.randint(2, 3))
            d2 = sp.diff(f, x, 2)
            out.append(sample(
                f"设 $f(x)={L(f)}$，求 $f''(x)$。",
                [f"先求一阶导数 $f'(x)={L(sp.diff(f,x))}$。",
                 f"再对 $f'(x)$ 求导，得到 $f''(x)={L(d2)}$。"],
                L(d2), "ap_calc"))
        elif kind == "critical":
            f = poly(rng.randint(2, 3))
            roots = [r for r in sp.solve(sp.diff(f, x), x) if r.is_real]
            if not roots:
                continue
            roots = sorted(roots, key=float)
            out.append(sample(
                f"设 $f(x)={L(f)}$，求 $f'(x)=0$ 的所有解。",
                [f"先求导：$f'(x)={L(sp.diff(f,x))}$。",
                 "令导数为 $0$ 并解方程。",
                 "得到解 " + "，".join(f"$x={L(r)}$" for r in roots) + "。"],
                "，".join(f"x={L(r)}" for r in roots), "ap_calc"))
        else:
            a = rng.randint(0, 2)
            b = a + rng.randint(1, 3)
            f = poly(rng.randint(1, 2))
            g = sp.Integer(rng.randint(1, 4)) * x
            diff = sp.simplify(g - f)
            area = sp.integrate(diff, (x, a, b))
            out.append(sample(
                f"求曲线 $y={L(f)}$ 与 $y={L(g)}$ 在 $[{a},{b}]$ 上围成的面积。",
                [f"先确定哪条曲线在上方：在区间内比较 $y={L(g)}$ 与 $y={L(f)}$。",
                 f"面积 $=\\int_{{{a}}}^{{{b}}}({L(g)}-({L(f)}))\\,dx$。",
                 f"求原函数并代入上下限，得到面积 ${L(area)}$。"],
                L(area), "ap_calc"))
    return out


def gen_stats(n):
    out = []
    for _ in range(n):
        kind = rng.choice(["meanvar", "z", "binom", "reg", "comb", "iqr"])
        if kind == "meanvar":
            data = [rng.randint(1, 20) for _ in range(5)]
            mean = sp.Rational(sum(data), len(data))
            var = sp.Rational(sum((v - mean) ** 2 for v in data), len(data))
            out.append(sample(
                f"求数据 ${','.join(map(str,data))}$ 的平均数和总体方差。",
                [f"平均数 $\\bar x=\\frac{{sum}}{{n}}={L(mean)}$。",
                 f"总体方差 $\\sigma^2=\\frac{{\\sum(x_i-\\bar x)^2}}{{n}}={L(var)}$。"],
                f"平均数 {L(mean)}，总体方差 {L(var)}", "ap_stats"))
        elif kind == "z":
            mu = rng.randint(40, 80)
            sd = rng.randint(5, 15)
            val = mu + rng.randint(-2, 2) * sd
            z = sp.Rational(val - mu, sd)
            out.append(sample(
                f"某数据均值 ${mu}$、标准差 ${sd}$，观测值 ${val}$ 的 z 分数是多少？",
                [f"z 分数公式 $z=\\frac{{x-\\mu}}{{\\sigma}}$。",
                 f"代入 $x={val},\\mu={mu},\\sigma={sd}$，得到 $z={L(z)}$。"],
                L(z), "ap_stats"))
        elif kind == "binom":
            nn = rng.randint(4, 8)
            p = rng.choice([sp.Rational(1, 3), sp.Rational(2, 5), sp.Rational(1, 2), sp.Rational(3, 5)])
            k = rng.randint(1, nn - 1)
            prob = sp.binomial(nn, k) * p**k * (1 - p)**(nn - k)
            out.append(sample(
                f"设 $X\\sim B({nn},{L(p)})$，求 $P(X={k})$。",
                [f"二项分布公式 $P(X=k)=\\binom{{n}}{{k}}p^k(1-p)^{{n-k}}$。",
                 f"代入 $n={nn},k={k},p={L(p)}$：$P(X={k})={L(sp.binomial(nn,k))}\\cdot({L(p)})^{{{k}}}\\cdot({L(1-p)})^{{{nn-k}}}$。",
                 f"计算得 ${L(sp.simplify(prob))}\\approx {float(prob):.4f}$。"],
                f"{float(prob):.4f}", "ap_stats"))
        elif kind == "reg":
            xs = [1, 2, 3, 4, 5]
            ys = [rng.randint(1, 5) + 2 * v for v in xs]
            mx = sp.Rational(sum(xs), len(xs))
            my = sp.Rational(sum(ys), len(ys))
            slope = sp.Rational(sum((a - mx) * (b - my) for a, b in zip(xs, ys)),
                               sum((a - mx) ** 2 for a in xs))
            out.append(sample(
                "对数据 " + "、".join(f"$({a},{b})$" for a, b in zip(xs, ys)) + " 做线性回归，求斜率。",
                ["回归斜率公式 $b=\\frac{\\sum(x_i-\\bar x)(y_i-\\bar y)}{\\sum(x_i-\\bar x)^2}$。",
                 f"先算 $\\bar x={L(mx)}$，$\\bar y={L(my)}$。",
                 f"代入求和，得到斜率 $b={L(slope)}$。"],
                L(slope), "ap_stats"))
        elif kind == "comb":
            nn = rng.randint(5, 12)
            k = rng.randint(2, min(4, nn - 1))
            if rng.random() < 0.5:
                val = sp.binomial(nn, k)
                out.append(sample(
                    f"求 $\\binom{{{nn}}}{{{k}}}$ 的值。",
                    [f"组合数公式 $\\binom{{n}}{{k}}=\\frac{{n!}}{{k!(n-k)!}}$。",
                     f"代入 $n={nn},k={k}$，计算得 ${L(val)}$。"],
                    L(val), "ap_stats"))
            else:
                val = sp.factorial(nn) / sp.factorial(nn - k)
                out.append(sample(
                    f"求 $P({nn},{k})$ 的值。",
                    [f"排列数公式 $P(n,k)=\\frac{{n!}}{{(n-k)!}}$。",
                     f"代入 $n={nn},k={k}$，计算得 ${L(val)}$。"],
                    L(val), "ap_stats"))
        else:
            data = sorted(rng.sample(range(1, 21), 8))
            q1 = sp.Rational(data[1] + data[2], 2)
            q3 = sp.Rational(data[5] + data[6], 2)
            iqr = q3 - q1
            out.append(sample(
                f"求数据 ${','.join(map(str,data))}$ 的四分位距（IQR）。",
                [f"先排序：${','.join(map(str,data))}$。",
                 f"下四分位数 $Q_1={L(q1)}$，上四分位数 $Q_3={L(q3)}$。",
                 f"四分位距 $IQR=Q_3-Q_1={L(iqr)}$。"],
                L(iqr), "ap_stats"))
    return out


def gen_precalc(n):
    out = []
    for _ in range(n):
        kind = rng.choice(["logeq", "expeq", "trig", "seq"])
        if kind == "logeq":
            b = rng.choice([2, 3, 5])
            k = rng.randint(2, 4)
            c = rng.randint(1, 5)
            val = b**k + c
            out.append(sample(
                f"解方程 $\\log_{{{b}}}(x-{c})={k}$。",
                [f"把对数式改写成指数式：$x-{c}={b}^{{{k}}}={b**k}$。",
                 f"解得 $x={val}$。"],
                f"x={val}", "precalc"))
        elif kind == "expeq":
            b = rng.choice([2, 3])
            k = rng.randint(2, 4)
            c = rng.randint(1, 4)
            val = k - c
            out.append(sample(
                f"解方程 ${b}^{{x+{c}}}={b**k}$。",
                [f"两边同底，指数相等：$x+{c}={k}$。",
                 f"解得 $x={val}$。"],
                f"x={val}", "precalc"))
        elif kind == "trig":
            ang = rng.choice([sp.pi / 6, sp.pi / 4, sp.pi / 3,
                              2 * sp.pi / 3, 7 * sp.pi / 6])
            fn = rng.choice(["sin", "cos"])
            f = sp.sin(ang) if fn == "sin" else sp.cos(ang)
            out.append(sample(
                f"求 $\\{fn}\\left({L(ang)}\\right)$ 的值。",
                [f"在单位圆上找到对应角，读出 {fn} 值。",
                 f"结果为 ${L(f)}$。"],
                L(f), "precalc"))
        else:
            a1 = rng.randint(1, 5)
            d = rng.randint(2, 6)
            k = rng.randint(5, 12)
            val = a1 + (k - 1) * d
            out.append(sample(
                f"等差数列首项为 ${a1}$，公差为 ${d}$，求第 ${k}$ 项。",
                [f"等差数列通项 $a_n=a_1+(n-1)d$。",
                 f"代入 $a_1={a1},d={d},n={k}$，得到 $a_{{{k}}}={val}$。"],
                str(val), "precalc"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    data = []
    data += gen_derivative_poly(200)
    data += gen_product(100)
    data += gen_quotient(100)
    data += gen_chain(150)
    data += gen_integral_indef(150)
    data += gen_integral_def(150)
    data += gen_integral_sub(100)
    data += gen_limit(200)
    data += gen_applications(300)
    data += gen_stats(600)
    data += gen_precalc(200)
    rng.shuffle(data)
    n = max(1, len(data) // 10)
    val, train = data[:n], data[n:]
    for name, rows in (("train", train), ("val", val)):
        with open(os.path.join(args.outdir, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats = {"total": len(data), "train": len(train), "val": len(val),
             "categories": dict(Counter(r["category"] for r in data))}
    with open(os.path.join(args.outdir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
