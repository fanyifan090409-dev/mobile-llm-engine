#!/usr/bin/env python3
"""生成数学客观验收集：70 道新题（AP Calc 25 / Precalc 25 / AP Stats 20）。

每题由 SymPy 现场出题并算真值，输出 train/eval/math_eval.json：
  {id, category, topic, problem, expected, expected_latex, answer_type}
answer_type: num（数值）/ expr（含 x 表达式）/ set（解集）/ text（文字）
训练机 venv 跑（需要 sympy）：
  python3 gen_math_eval.py --out /home/ubuntu/llm-mobile/eval_tmp/math_eval.json
"""
import argparse
import json
import math

import sympy as sp

x = sp.Symbol("x")
t = sp.Symbol("t")
records = []


def add(category, topic, problem, expected, answer_type, tol=1e-6, display=None):
    if answer_type == "num":
        exp_str = str(expected)
        try:
            exp_latex = sp.latex(expected)
        except Exception:
            exp_latex = str(expected)
    elif answer_type == "expr":
        exp_str = str(sp.simplify(expected))
        exp_latex = sp.latex(sp.simplify(expected))
    elif answer_type == "set":
        exp_str = json.dumps([str(sp.simplify(e)) for e in expected], ensure_ascii=False)
        exp_latex = "\\{" + ", ".join(sp.latex(e) for e in expected) + "\\}"
    else:
        exp_str = str(expected)
        exp_latex = str(expected)
    records.append({
        "id": f"{category}-{len([r for r in records if r['category'] == category]) + 1:02d}",
        "category": category, "topic": topic, "problem": problem,
        "expected": exp_str, "expected_latex": display or exp_latex,
        "answer_type": answer_type, "tol": tol,
    })


# ---------------- AP Calc 25 ----------------
f1 = 2 * x**3 - 5 * x**2 + 3 * x - 7
add("ap_calc", "求导", f"设 $f(x)={sp.latex(f1)}$，求 $f'(x)$。", sp.diff(f1, x), "expr")

f2 = x**2 * sp.sin(x)
add("ap_calc", "乘积法则", f"设 $f(x)={sp.latex(f2)}$，求 $f'(x)$。", sp.diff(f2, x), "expr")

f3 = (3 * x + 1) / (x - 2)
add("ap_calc", "商法则", f"设 $f(x)={sp.latex(f3)}$，求 $f'(x)$。", sp.diff(f3, x), "expr")

f4 = sp.sin(4 * x - 1)
add("ap_calc", "链式法则", f"设 $f(x)={sp.latex(f4)}$，求 $f'(x)$。", sp.diff(f4, x), "expr")

f5 = sp.exp(3 * x) + sp.log(2 * x)
add("ap_calc", "指数与对数求导", f"设 $f(x)={sp.latex(f5)}$，求 $f'(x)$。", sp.diff(f5, x), "expr")

f6 = x**2 * sp.exp(x)
add("ap_calc", "乘积法则", f"设 $f(x)={sp.latex(f6)}$，求 $f'(x)$。", sp.diff(f6, x), "expr")

f7 = sp.log(x**2 + 1)
add("ap_calc", "链式法则", f"设 $f(x)={sp.latex(f7)}$，求 $f'(x)$。", sp.diff(f7, x), "expr")

f8 = sp.sqrt(5 * x + 2)
add("ap_calc", "链式法则", f"设 $f(x)={sp.latex(f8)}$，求 $f'(x)$。", sp.diff(f8, x), "expr")

add("ap_calc", "不定积分",
    r"求不定积分 $\int (3x^2-4x+1)\,dx$。", sp.integrate(3 * x**2 - 4 * x + 1, x), "expr")

add("ap_calc", "定积分",
    r"求定积分 $\int_{0}^{2}(x^3-2x+1)\,dx$ 的值。",
    sp.integrate(x**3 - 2 * x + 1, (x, 0, 2)), "num")

add("ap_calc", "定积分",
    r"求定积分 $\int_{1}^{4}\frac{1}{\sqrt{x}}\,dx$ 的值。",
    sp.integrate(1 / sp.sqrt(x), (x, 1, 4)), "num")

add("ap_calc", "定积分",
    r"求定积分 $\int_{0}^{\pi}\sin(2x)\,dx$ 的值。",
    sp.integrate(sp.sin(2 * x), (x, 0, sp.pi)), "num")

add("ap_calc", "换元积分",
    r"求不定积分 $\int x e^{x^2}\,dx$。",
    sp.integrate(x * sp.exp(x**2), x), "expr")

add("ap_calc", "极限",
    r"求极限 $\lim_{x\to\infty}\frac{3x^2+2x-1}{5x^2-x+4}$。",
    sp.limit((3 * x**2 + 2 * x - 1) / (5 * x**2 - x + 4), x, sp.oo), "num")

add("ap_calc", "极限",
    r"求极限 $\lim_{x\to 2}\frac{x^2-4}{x-2}$。",
    sp.limit((x**2 - 4) / (x - 2), x, 2), "num")

f16 = x**3 - 3 * x
add("ap_calc", "驻点", f"设 $f(x)={sp.latex(f16)}$，求 $f'(x)=0$ 的所有解。",
    sp.solve(sp.diff(f16, x), x), "set")

add("ap_calc", "最值",
    "设 $f(x)=x^3-3x$，求 $f$ 在区间 $[-2,2]$ 上的最大值。",
    max(f16.subs(x, v) for v in (-2, -1, 1, 2)), "num")

add("ap_calc", "平均值",
    r"求函数 $f(x)=x^2$ 在区间 $[0,3]$ 上的平均值。",
    sp.integrate(x**2, (x, 0, 3)) / 3, "num")

add("ap_calc", "切线斜率",
    "设 $f(x)=x^3-2x$，求曲线在 $x=1$ 处的切线斜率。",
    sp.diff(x**3 - 2 * x, x).subs(x, 1), "num")

add("ap_calc", "二阶导数",
    r"设 $f(x)=\sin(2x)$，求 $f''(x)$。",
    sp.diff(sp.sin(2 * x), x, 2), "expr")

add("ap_calc", "参数方程求导",
    r"曲线由 $x=t^2-1,\ y=t^3$ 给出，求 $t=2$ 处的 $\frac{dy}{dx}$。",
    sp.diff(t**3, t).subs(t, 2) / sp.diff(t**2 - 1, t).subs(t, 2), "num")

add("ap_calc", "面积",
    r"求曲线 $y=x^2$ 与 $y=x$ 在 $[0,1]$ 上围成的面积。",
    sp.integrate(x - x**2, (x, 0, 1)), "num")

f23 = x**3 - 6 * x**2 + 9 * x
add("ap_calc", "驻点", f"设 $f(x)={sp.latex(f23)}$，求 $f'(x)=0$ 的所有解。",
    sp.solve(sp.diff(f23, x), x), "set")

add("ap_calc", "指数函数求值", r"设 $f(x)=2^x$，求 $f(3)$ 的值。", 8, "num")

add("ap_calc", "反三角函数求导",
    r"设 $f(x)=\arctan x$，求 $f'(x)$。", sp.diff(sp.atan(x), x), "expr")

# ---------------- Precalc 25 ----------------
add("precalc", "对数计算", r"求 $\log_2 32$ 的值。", sp.log(32, 2), "num")
add("precalc", "对数计算", r"求 $\log_3 \frac{1}{9}$ 的值。", sp.log(sp.Rational(1, 9), 3), "num")
add("precalc", "指数方程", r"解方程 $2^{x+1}=32$。", sp.solve(2**(x + 1) - 32, x), "set")
add("precalc", "对数方程", r"解方程 $\log_2(x-1)=3$。", sp.solve(sp.log(x - 1, 2) - 3, x), "set")
add("precalc", "三角函数值", r"求 $\sin\frac{\pi}{6}$ 的值。", sp.sin(sp.pi / 6), "num")
add("precalc", "三角函数值", r"求 $\cos\frac{2\pi}{3}$ 的值。", sp.cos(2 * sp.pi / 3), "num")
add("precalc", "三角函数值", r"求 $\tan\frac{\pi}{4}$ 的值。", sp.tan(sp.pi / 4), "num")
add("precalc", "三角函数值", r"求 $\sin\frac{7\pi}{6}$ 的值。", sp.sin(7 * sp.pi / 6), "num")
add("precalc", "化简", r"当 $x\neq 3$ 时，化简 $\frac{x^2-9}{x-3}$。", x + 3, "expr")
add("precalc", "反函数", r"设 $f(x)=2x+3$，求 $f^{-1}(7)$ 的值。", sp.solve(sp.Eq(2 * x + 3, 7), x)[0], "num")
add("precalc", "复合函数", r"设 $f(x)=x^2+1,\ g(x)=2x-1$，求 $f(g(2))$ 的值。",
    (x**2 + 1).subs(x, 2 * x - 1).subs(x, 2), "num")
add("precalc", "余数定理", r"求多项式 $x^3-2x^2+4x-1$ 除以 $x-2$ 的余数。",
    sp.rem(x**3 - 2 * x**2 + 4 * x - 1, x - 2, x), "num")
add("precalc", "因式分解", r"因式分解 $x^3-4x$。", sp.factor(x**3 - 4 * x), "expr")
add("precalc", "等差数列", r"等差数列首项为 $3$，公差为 $4$，求第 $10$ 项。", 3 + 9 * 4, "num")
add("precalc", "等比数列", r"求 $1+2+4+\cdots+2^9$ 的和。", sum(2**k for k in range(10)), "num")
add("precalc", "组合数", r"求 $\binom{8}{3}$ 的值。", sp.binomial(8, 3), "num")
add("precalc", "行列式", r"求行列式 $\begin{vmatrix}3&4\\2&5\end{vmatrix}$ 的值。",
    sp.Matrix([[3, 4], [2, 5]]).det(), "num")
add("precalc", "线性方程组", r"解方程组 $x+y=7,\ 2x-y=2$，求 $x$ 的值。",
    sp.solve([x + sp.Symbol("y") - 7, 2 * x - sp.Symbol("y") - 2], [x, sp.Symbol("y")])[x], "num")
add("precalc", "两点距离", r"求点 $(1,2)$ 与 $(4,6)$ 之间的距离。",
    sp.sqrt((4 - 1)**2 + (6 - 2)**2), "num")
add("precalc", "圆", r"圆 $x^2+y^2-4x+6y-12=0$ 的半径是多少？", 5, "num")
add("precalc", "数列求和", r"求 $1+2+3+\cdots+20$ 的和。", sum(range(1, 21)), "num")
add("precalc", "弧度制", r"把 $150^\circ$ 化成弧度。", sp.rad(150), "expr")
add("precalc", "复数模", r"求复数 $3+4i$ 的模。", abs(3 + 4 * sp.I), "num")
add("precalc", "解方程", r"解方程 $x^2-5x+6=0$。", sp.solve(x**2 - 5 * x + 6, x), "set")
add("precalc", "三角恒等式", r"化简 $\sin^2 x+\cos^2 x$。", 1, "num")

# ---------------- AP Stats 20 ----------------
add("ap_stats", "平均数", r"求数据 $4,8,6,10,2$ 的平均数。", sp.Rational(4 + 8 + 6 + 10 + 2, 5), "num")
add("ap_stats", "中位数", r"求数据 $3,7,9,4,5$ 的中位数。", 5, "num")
add("ap_stats", "总体方差", r"求数据 $2,4,6,8$ 的总体方差。", sp.Rational(5), "num")
add("ap_stats", "样本标准差", r"求数据 $2,4,6,8$ 的样本标准差。",
    sp.sqrt(sp.Rational(20, 3)), "num", tol=1e-4)
add("ap_stats", "z 分数", r"某数据均值 $70$、标准差 $10$，观测值 $85$ 的 z 分数是多少？", 1.5, "num")
add("ap_stats", "正态概率", r"设 $X\sim N(70,10^2)$，求 $P(X<75)$（保留四位小数）。",
    sp.N((1 + sp.erf((75 - 70) / (10 * sp.sqrt(2)))) / 2, 8), "num", tol=1e-3)
add("ap_stats", "二项分布", r"设 $X\sim B(5,0.4)$，求 $P(X=3)$（保留四位小数）。",
    sp.binomial(5, 3) * sp.Rational(4, 10)**3 * sp.Rational(6, 10)**2, "num", tol=1e-3)
add("ap_stats", "期望", r"离散随机变量 $X$ 取 $0,1,2$ 的概率分别为 $0.2,0.5,0.3$，求 $E(X)$。",
    0 * 0.2 + 1 * 0.5 + 2 * 0.3, "num")
xs = [1, 2, 3, 4]
ys = [2, 4, 5, 8]
mx, my = sum(xs) / 4, sum(ys) / 4
slope = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / sum((a - mx)**2 for a in xs)
add("ap_stats", "回归斜率", r"对数据 $(1,2),(2,4),(3,5),(4,8)$ 做线性回归，求斜率。", slope, "num", tol=1e-4)
r = (sum((a - mx) * (b - my) for a, b in zip(xs, ys))
     / sp.sqrt(sum((a - mx)**2 for a in xs) * sum((b - my)**2 for b in ys)))
add("ap_stats", "相关系数", r"对数据 $(1,2),(2,4),(3,5),(4,8)$，求相关系数 $r$。", r, "num", tol=1e-4)
add("ap_stats", "置信区间", r"样本均值 $50$、总体标准差 $10$、样本量 $25$，求 95% 置信区间的边际误差（用 $z^*=1.96$）。",
    1.96 * 10 / 5, "num", tol=1e-4)
add("ap_stats", "概率加法", r"已知 $P(A)=0.5,\ P(B)=0.4,\ P(A\cap B)=0.2$，求 $P(A\cup B)$。", 0.7, "num")
add("ap_stats", "条件概率", r"已知 $P(A\cap B)=0.2,\ P(B)=0.4$，求 $P(A\mid B)$。", 0.5, "num")
add("ap_stats", "组合", r"求 $\binom{10}{2}$ 的值。", sp.binomial(10, 2), "num")
add("ap_stats", "排列", r"求 $P(10,3)$ 的值。", sp.factorial(10) / sp.factorial(7), "num")
add("ap_stats", "标准误", r"总体标准差 $10$、样本量 $25$，求样本均值的标准误。", 10 / 5, "num")
add("ap_stats", "四分位距", r"求数据 $1,3,5,7,9,11,13,15$ 的四分位距（IQR）。", 8, "num")
add("ap_stats", "二项均值", r"设 $X\sim B(20,0.3)$，求 $E(X)$。", 20 * 0.3, "num")
add("ap_stats", "二项方差", r"设 $X\sim B(20,0.3)$，求 $\operatorname{Var}(X)$。", 20 * 0.3 * 0.7, "num")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    from collections import Counter
    print("total", len(records), dict(Counter(r["category"] for r in records)))
    for r in records[:3]:
        print(r["id"], r["problem"][:60], "=>", r["expected"])


if __name__ == "__main__":
    main()
