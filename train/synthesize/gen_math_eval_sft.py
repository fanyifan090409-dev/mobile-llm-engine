#!/usr/bin/env python3
"""生成 math_eval 工具调用 SFT 数据（CAS 二期）。

流程：
1) 模板随机生成 1,000 道中文计算题（eval/derivative/simplify/integrate/solve/stats）；
2) 调用 cas_batch.js 走真实 CAS（math.js），拿到与线上一致的 result / 数值解标记；
3) 独立校验：数值题用 Python 精确值对拍，表达式题用采样点对拍，解方程按根集对拍；
4) 每题产出两条轨迹：call（user → tool_call）与 answer（user → tool_call → tool → 讲解）。

输出到 train/synthesize/out_math_eval_sft/（.gitignore 已忽略 out_*/）。
"""
import json
import math
import os
import random
import subprocess
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTDIR = os.path.join(ROOT, "train", "synthesize", "out_math_eval_sft")
BATCH = os.path.join(ROOT, "train", "synthesize", "cas_batch.js")

# 必须与 apps/demo-cli/Sources/demo-cli/MathEvalTool.swift 的 usagePrompt 逐字一致
USAGE_PROMPT = (
    "你是数学助手。遇到需要精确计算时，第一步只输出一个工具调用块，不要输出其他内容，格式：\n"
    '<tool_call>\n{"name": "math_eval", "arguments": {"op": "eval", "expr": "x^2+3*x"}}\n</tool_call>\n'
    "expr 用 math.js 语法：乘方 ^、乘法 *、函数 sin(x)/cos(x)/exp(x)/log(x)/log(x, 底数)；不要用 LaTeX 的 {}、\\frac、\\log_2。\n"
    "op 可选 eval（求值）/ derivative（求导）/ simplify（化简）/ integrate_def（定积分）/ solve（解方程）/ stats（统计）。"
    'solve 可写 "x^2-5x+6=0"；积分与解方程用 lower/upper 给区间（可写 pi/2）；'
    "stats 用 stat_op 与 data：mean/median/variance/std/variance_pop/std_pop/iqr/sum/min/max/combination/permutation/binomial/regression/normalcdf，"
    'data 逗号分隔，regression 用 "x1,y1;x2,y2"，normalcdf 用 "mu,sigma,x"。'
    "解题约定：面积先判断哪条曲线在上方，再用上曲线减下曲线积分；平均值 = 定积分 ÷ 区间长度；"
    "二阶行列式 = ad - bc；\\binom{n}{k} 用 stats combination；正态概率用 stats normalcdf；二项分布 Var(X)=n p (1-p)；"
    "两点距离 = sqrt((x2-x1)^2+(y2-y1)^2)；1+2+...+n = n(n+1)/2；"
    "反函数值先求反函数再代入（开方取定义域内的根）；f(g(a)) 先算 g(a) 再代入 f；"
    "多项式除以 x-a 的余数 = P(a)；等比数列首项到 a*r^k 共 k+1 项，和 = a*(r^(k+1)-1)/(r-1)。"
    "收到工具结果后，如果还需要下一步计算就继续调用工具；否则用中文简要讲解，并在最后一行写【答案】，答案必须与工具结果一致。"
)

TARGETS = {"eval": 150, "derivative": 250, "simplify": 100,
           "integrate": 150, "solve": 150, "stats": 200}

# 随机模板会重复（尤其 simplify/solve）；重复题去重后重新采样，保证 1,070 题都不同
CASE_KEYS = set()


def term_str(coeff, power):
    c = abs(coeff)
    if power == 0:
        return str(c)
    if power == 1:
        return "x" if c == 1 else f"{c}*x"
    return f"x^{power}" if c == 1 else f"{c}*x^{power}"


def linear_str(a, b, var="x"):
    if abs(a) == 1:
        body = var if a > 0 else f"-{var}"
    else:
        body = f"{a}*{var}"
    if b == 0:
        return body
    return f"{body} + {b}" if b > 0 else f"{body} - {abs(b)}"


def linear_tex(a, b):
    body = "x" if a == 1 else ("-x" if a == -1 else f"{a}x")
    return body if b == 0 else f"{body}{signed(b)}"


def poly_str(terms):
    out = ""
    for coeff, power in terms:
        if coeff == 0:
            continue
        body = term_str(coeff, power)
        if not out:
            out = ("-" if coeff < 0 else "") + body
        else:
            out += (" - " if coeff < 0 else " + ") + body
    return out or "0"


def parse_cas_number(text):
    s = text.strip().replace("（数值解）", "")
    if "/" in s:
        a, b = s.split("/", 1)
        return float(Fraction(int(a), int(b)))
    return float(s)


def pick_field(result, field):
    for part in result.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        if k.strip() == field:
            return v.strip()
    return None


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol + 1e-6 * abs(b)


def final_answer(category, result, case):
    if category == "stats" and case["check"]["kind"] == "pick":
        return pick_field(result, case["check"]["field"]) or result
    return result


def explain(category, result, case):
    if category in ("eval", "word"):
        return f"计算得到 {result}。"
    if category == "derivative":
        return f"对原式求导，得到 f'(x) = {result}。"
    if category == "simplify":
        return f"化简结果为 {result}。"
    if category == "integrate":
        return f"定积分的值为 {result}（数值解）。"
    if category == "solve":
        parts = [p.strip() for p in result.split(",") if p.strip()]
        if len(parts) > 1:
            return "解得 " + " 或 ".join(f"x = {p}" for p in parts) + "（数值解）。"
        return f"解得 x = {result}（数值解）。"
    if category == "area":
        return f"面积为 {result}。"
    if category == "stats":
        label = case.get("stat_label", "结果")
        if case["check"]["kind"] == "pick":
            field = case["check"]["field"]
            value = pick_field(result, field) or result
            return f"{label}为 {value}（数值解）。"
        return f"{label}为 {result}（数值解）。"
    return f"计算得到 {result}。"


def add(cases, category, problem, args, check, stat_label=None):
    # 全局兜底：任何生成器都不允许把 69 题评测原题写进训练数据
    if problem in eval_problem_set():
        return False
    key = json.dumps([problem, args], ensure_ascii=False, sort_keys=True)
    if key in CASE_KEYS:
        return False
    CASE_KEYS.add(key)
    idx = len([c for c in cases if c["category"] == category])
    cases.append({
        "id": f"{category}-{idx + 1:03d}",
        "category": category,
        "problem": problem,
        "args": args,
        "check": check,
        "stat_label": stat_label,
    })
    return True


def gen_eval(cases):
    n = 0
    while len([c for c in cases if c["category"] == "eval"]) < TARGETS["eval"]:
        n += 1
        kind = n % 8
        if kind in (0, 1, 2):
            b, d = random.choice([2, 3, 4, 5, 6, 8, 10, 12]), random.choice([2, 3, 4, 5, 6, 8, 10, 12])
            a, c = random.randint(1, b * 2), random.randint(1, d * 2)
            op = random.choice(["+", "-", "*"])
            expr = f"{a}/{b} {op} {c}/{d}"
            if op == "+":
                value = Fraction(a, b) + Fraction(c, d)
            elif op == "-":
                value = Fraction(a, b) - Fraction(c, d)
            else:
                value = Fraction(a, b) * Fraction(c, d)
            problem = random.choice([f"计算 {expr} 的值。", f"求 {expr}。", f"{expr} 等于多少？"])
            add(cases, "eval", problem, {"op": "eval", "expr": expr},
                {"kind": "num", "value": float(value), "tol": 1e-9})
        elif kind == 3:
            power = random.randint(3, 10)
            expr = f"2^{power}"
            add(cases, "eval", f"计算 {expr} 的值。", {"op": "eval", "expr": expr},
                {"kind": "num", "value": float(2 ** power)})
        elif kind == 4:
            k = random.choice([1, 2, 3, 4, 6])
            fn = random.choice(["sin", "cos"])
            expr = f"{fn}(pi/{k})"
            value = getattr(math, fn)(math.pi / k)
            add(cases, "eval", f"求 {expr} 的值。", {"op": "eval", "expr": expr},
                {"kind": "num", "value": value, "tol": 1e-6})
        elif kind == 5:
            base = random.choice([2, 3, 5])
            power = random.randint(2, 5)
            value = base ** power
            expr = f"log({value},{base})"
            add(cases, "eval", f"求 {expr} 的值。", {"op": "eval", "expr": expr},
                {"kind": "num", "value": float(power)})
        elif kind == 6:
            root = random.randint(2, 15)
            expr = f"sqrt({root * root})"
            add(cases, "eval", f"计算 {expr} 的值。", {"op": "eval", "expr": expr},
                {"kind": "num", "value": float(root)})
        else:
            a, b, c = random.choice([(3, 4, 5), (5, 12, 13), (8, 15, 17), (7, 24, 25)])
            expr = f"abs({a}+{b}i)"
            add(cases, "eval", f"求复数 {a}+{b}i 的模。", {"op": "eval", "expr": expr},
                {"kind": "num", "value": float(c)})


def eval_problem_set():
    with open(os.path.join(ROOT, "train", "eval", "math_eval.json"), encoding="utf-8") as f:
        return {c["problem"] for c in json.load(f)}


def gen_word(cases):
    """应用题：题面自然是中文，模型要先翻译成算术表达式（对应 69 题里的 AP 统计计算）。"""
    blocked = eval_problem_set()

    def add_word(problem, expr, value, tol=1e-6):
        if problem in blocked:
            return False
        return add(cases, "word", problem, {"op": "eval", "expr": expr},
                   {"kind": "num", "value": value, "tol": tol})

    def fill(n, make):
        got, guard = 0, 0
        while got < n and guard < n * 80:
            guard += 1
            if make():
                got += 1

    def z_score():
        mu = random.randint(40, 95)
        sigma = random.choice([4, 5, 8, 10, 12, 15, 20])
        x = mu + random.choice([-3, -2, -1, 1, 2, 3]) * sigma
        return add_word(f"某组数据均值为 {mu}、标准差为 {sigma}，观测值 {x} 的 z 分数是多少？",
                        f"({x}-{mu})/{sigma}", (x - mu) / sigma)

    def p_add():
        pa = random.choice([0.2, 0.3, 0.4, 0.5, 0.6])
        pb = random.choice([0.25, 0.35, 0.45, 0.55])
        pab = random.choice([0.1, 0.15, 0.2, 0.25])
        if pab >= min(pa, pb) or pa + pb - pab > 1:
            return False
        return add_word(f"已知 P(A)={pa}，P(B)={pb}，P(A∩B)={pab}，求 P(A∪B)。",
                        f"{pa}+{pb}-{pab}", pa + pb - pab)

    def cond():
        pb = random.choice([0.3, 0.4, 0.5, 0.6, 0.8])
        pab = random.choice([0.1, 0.15, 0.2, 0.25, 0.3])
        if pab >= pb:
            return False
        return add_word(f"已知 P(A∩B)={pab}，P(B)={pb}，求 P(A|B)。",
                        f"{pab}/{pb}", pab / pb)

    def stand_err():
        sigma = random.choice([6, 8, 9, 10, 12, 15])
        n = random.choice([4, 9, 16, 25, 36, 49])
        return add_word(f"总体标准差为 {sigma}，样本量为 {n}，求样本均值的标准误。",
                        f"{sigma}/sqrt({n})", sigma / math.sqrt(n))

    def binom_mean():
        n, p = random.randint(10, 30), random.choice([0.2, 0.25, 0.3, 0.4, 0.5])
        return add_word(f"设 X ~ B({n}, {p})，求 E(X)。", f"{n}*{p}", n * p)

    def binom_var():
        n, p = random.randint(10, 30), random.choice([0.2, 0.25, 0.3, 0.4, 0.5])
        q = round(1 - p, 2)
        return add_word(f"设 X ~ B({n}, {p})，求 Var(X)。", f"{n}*{p}*{q}", n * p * q)

    def normal():
        mu = random.choice([60, 65, 70, 75, 80])
        sigma = random.choice([5, 8, 10, 12])
        x = mu + random.choice([3, 5, 6, 8, 10])
        value = 0.5 * (1 + math.erf((x - mu) / (sigma * math.sqrt(2))))
        return add_word(f"设 X ~ N({mu}, {sigma}^2)，求 P(X < {x})（保留四位小数）。",
                        f"0.5*(1+erf(({x}-{mu})/({sigma}*sqrt(2))))", value)

    def ci_margin():
        sigma = random.choice([8, 10, 12, 15])
        n = random.choice([16, 25, 36, 49])
        return add_word(f"样本均值 50、总体标准差 {sigma}、样本量 {n}，求 95% 置信区间的边际误差（用 z*=1.96）。",
                        f"1.96*{sigma}/sqrt({n})", 1.96 * sigma / math.sqrt(n))

    def expectation():
        k = random.randint(2, 4)
        xs = random.sample(range(0, 6), k)
        ws = [random.choice([1, 2, 3, 4, 5]) for _ in xs]
        total = sum(ws)
        ps = [round(w / total, 3) for w in ws]
        ps[-1] = round(1 - sum(ps[:-1]), 3)
        if min(ps) <= 0:
            return False
        expr = "+".join(f"{x}*{p}" for x, p in zip(xs, ps))
        value = sum(x * p for x, p in zip(xs, ps))
        problem = "离散随机变量 X 取 " + "、".join(map(str, xs)) + \
            "，概率分别为 " + "、".join(map(str, ps)) + "，求 E(X)。"
        return add_word(problem, expr, value, tol=1e-9)

    for make, n in [(z_score, 30), (p_add, 12), (cond, 12), (stand_err, 16),
                    (binom_mean, 20), (binom_var, 20), (normal, 10),
                    (ci_margin, 30), (expectation, 30)]:
        fill(n, make)


def poly_tex(terms):
    out = ""
    for coeff, power in terms:
        if coeff == 0:
            continue
        c = abs(coeff)
        body = str(c) if power == 0 else (("x" if c == 1 else f"{c}x") + ("" if power == 1 else f"^{{{power}}}"))
        if not out:
            out = ("-" if coeff < 0 else "") + body
        else:
            out += (" - " if coeff < 0 else " + ") + body
    return out or "0"


def signed(n):
    return f"-{abs(n)}" if n < 0 else f"+{n}"


def gen_normalcdf(cases):
    made, guard = 0, 0
    while made < 30 and guard < 3000:
        guard += 1
        mu = random.choice([50, 60, 65, 70, 75, 80, 100])
        sigma = random.choice([5, 8, 10, 12, 15])
        x = mu + random.choice([-3, -2, -1, 1, 2, 3]) * random.choice([2, 3, 5])
        value = 0.5 * (1 + math.erf((x - mu) / (sigma * math.sqrt(2))))
        problem = f"设 X ~ N({mu}, {sigma}^2)，求 P(X < {x})（保留四位小数）。"
        made += int(add(cases, "stats", problem,
                        {"op": "stats", "stat_op": "normalcdf", "data": f"{mu},{sigma},{x}"},
                        {"kind": "num", "value": value, "tol": 1e-6}, stat_label="概率"))


def gen_binomial(cases):
    made, guard = 0, 0
    while made < 60 and guard < 4000:
        guard += 1
        n = random.randint(5, 20)
        k = random.randint(0, n)
        p = random.choice([0.2, 0.25, 0.3, 0.4, 0.5, 0.6])
        value = math.comb(n, k) * p ** k * (1 - p) ** (n - k)
        problem = f"设 X ~ B({n}, {p})，求 P(X = {k}) 的值。"
        made += int(add(cases, "stats", problem,
                        {"op": "stats", "stat_op": "binomial", "data": f"{n},{k},{p}"},
                        {"kind": "num", "value": value, "tol": 1e-9}, stat_label="概率"))


def gen_precalc_words(cases):
    # 余数定理：P(x) 除以 (x-a) 的余数 = P(a)
    made, guard = 0, 0
    while made < 25 and guard < 3000:
        guard += 1
        a = random.randint(-4, 4)
        deg = random.randint(2, 4)
        terms = [(random.choice([-4, -3, -2, -1, 1, 2, 3, 4]), p) for p in range(deg, -1, -1)]
        expr = poly_str(terms)
        value = sum(c * (a ** p) for c, p in terms)
        problem = f"求多项式 ${poly_tex(terms)}$ 除以 $x{signed(-a)}$ 的余数。"
        call_expr = expr.replace("x", f"({a})")
        made += int(add(cases, "eval", problem, {"op": "eval", "expr": call_expr},
                        {"kind": "num", "value": float(value)}))

    # 等比/等差求和：题面用 \cdots，工具调用写成闭式公式
    made, guard = 0, 0
    while made < 20 and guard < 2000:
        guard += 1
        r = random.choice([2, 3])
        n = random.randint(4, 9)
        a = random.choice([1, 2, 3])
        terms = "+".join(str(a * r ** k) for k in range(3)) + f"+\\cdots+{a * r ** (n - 1)}"
        value = a * (r ** n - 1) // (r - 1)
        problem = f"求 ${terms}$ 的值。"
        call_expr = f"{a}*({r}^{n}-1)/({r}-1)"
        made += int(add(cases, "eval", problem, {"op": "eval", "expr": call_expr},
                        {"kind": "num", "value": float(value)}))

    made, guard = 0, 0
    while made < 20 and guard < 2000:
        guard += 1
        a1 = random.randint(1, 5)
        d = random.randint(1, 4)
        n = random.randint(5, 20)
        an = a1 + (n - 1) * d
        terms = f"{a1}+{a1 + d}+{a1 + 2 * d}+\\cdots+{an}"
        value = n * (a1 + an) // 2
        problem = f"求 ${terms}$ 的值。"
        call_expr = f"{n}*({a1}+{an})/2"
        made += int(add(cases, "eval", problem, {"op": "eval", "expr": call_expr},
                        {"kind": "num", "value": float(value)}))


def gen_area(cases):
    # f = g + h，h = k(x-a)(b-x) ≥ 0；面积 = ∫ h，训练模型先做 f-g 再积分
    made, guard = 0, 0
    while made < 25 and guard < 3000:
        guard += 1
        a, b = random.choice([(0, 1), (0, 2), (1, 2), (1, 3)])
        k = random.choice([1, 2, 3])
        m, c0 = random.randint(-3, 3), random.randint(-4, 4)
        g_terms = [(m, 1), (c0, 0)]
        f_terms = [(-k, 2), (k * (a + b) + m, 1), (c0 - k * a * b, 0)]
        h_terms = [(-k, 2), (k * (a + b), 1), (-k * a * b, 0)]
        value = Fraction(k * (b - a) ** 3, 6)
        problem = (f"求曲线 $y={poly_tex(f_terms)}$ 与 $y={poly_tex(g_terms)}$ "
                   f"在 $[{a},{b}]$ 上围成的面积。")
        args = {"op": "integrate_def", "expr": poly_str(h_terms),
                "lower": str(a), "upper": str(b)}
        made += int(add(cases, "area", problem, args,
                        {"kind": "num", "value": float(value), "tol": 1e-6}))


def gen_latex_rational(cases):
    made, guard = 0, 0
    while made < 30 and guard < 3000:
        guard += 1
        a, c = random.randint(1, 5), random.randint(1, 4)
        b, d = random.randint(-6, 6), random.randint(-6, 6)
        if a * d - b * c == 0:
            continue
        expr = f"({linear_str(a, b)})/({linear_str(c, d)})"
        expected = f"({a}*{d}-{b}*{c})/({linear_str(c, d)})^2"
        problem = f"设 $f(x)=\\frac{{{a}x{signed(b)}}}{{{c}x{signed(d)}}}$，求 $f'(x)$。"
        made += int(add(cases, "derivative", problem,
                        {"op": "derivative", "expr": expr, "expected_expr": expected},
                        {"kind": "match"}))


def gen_latex_explog(cases):
    made, guard = 0, 0
    while made < 20 and guard < 2000:
        guard += 1
        kind = guard % 3
        if kind == 0:
            a, b = random.choice([2, 3]), random.choice([2, 3, 4])
            expr = f"exp({a}*x)+log({b}*x)"
            expected = f"{a}*exp({a}*x)+1/x"
            problem = f"设 $f(x)=e^{{{a}x}}+\\log({b}x)$，求 $f'(x)$。"
        elif kind == 1:
            a = random.choice([2, 3])
            expr = f"x^2*exp({a}*x)"
            expected = f"2*x*exp({a}*x)+{a}*x^2*exp({a}*x)"
            problem = f"设 $f(x)=x^{{2}}e^{{{a}x}}$，求 $f'(x)$。"
        else:
            a = random.choice([1, 2, 3])
            expr = f"log(x^2+{a})"
            expected = f"2*x/(x^2+{a})"
            problem = f"设 $f(x)=\\log(x^{{2}}+{a})$，求 $f'(x)$。"
        made += int(add(cases, "derivative", problem,
                        {"op": "derivative", "expr": expr, "expected_expr": expected},
                        {"kind": "match"}))


def gen_latex_derivative(cases):
    """LaTeX 题面：练「把试卷写法翻译成 math.js 表达式」（69 题原题就是 LaTeX）。"""
    made, guard = 0, 0
    while made < 40 and guard < 4000:
        guard += 1
        kind = guard % 8
        if kind == 0:
            terms = [(random.choice([-4, -3, -2, -1, 1, 2, 3, 4]), p) for p in random.sample([1, 2, 3], k=3)]
            expr = poly_str(terms)
            expected = poly_str([(c * p, p - 1) for c, p in terms]) or "0"
            problem = f"设 $f(x)={poly_tex(terms)}$，求 $f'(x)$。"
        elif kind == 1:
            a = random.choice([2, 3, 4])
            expr = f"x^2*sin({a}*x)"
            expected = f"2*x*sin({a}*x)+{a}*x^2*cos({a}*x)"
            problem = f"设 $f(x)=x^{{2}}\\sin({a}x)$，求 $f'(x)$。"
        elif kind == 2:
            a, c = random.randint(2, 5), random.randint(1, 4)
            b, d = random.randint(-6, 6), random.randint(-6, 6)
            expr = f"({linear_str(a, b)})/({linear_str(c, d)})"
            expected = f"({a}*{d}-{b}*{c})/({linear_str(c, d)})^2"
            problem = f"设 $f(x)=\\frac{{{a}x{signed(b)}}}{{{c}x{signed(d)}}}$，求 $f'(x)$。"
        elif kind == 3:
            a = random.choice([2, 3, 4])
            b = random.randint(-5, 5)
            expr = f"sin({linear_str(a, b)})"
            expected = f"{a}*cos({linear_str(a, b)})"
            problem = f"设 $f(x)=\\sin({a}x{signed(b)})$，求 $f'(x)$。"
        elif kind == 4:
            a = random.choice([2, 3, 4])
            b = random.choice([2, 3, 4])
            expr = f"exp({a}*x)+log({b}*x)"
            expected = f"{a}*exp({a}*x)+1/x"
            problem = f"设 $f(x)=e^{{{a}x}}+\\log({b}x)$，求 $f'(x)$。"
        elif kind == 5:
            a = random.choice([2, 3])
            expr = f"x^2*exp({a}*x)"
            expected = f"2*x*exp({a}*x)+{a}*x^2*exp({a}*x)"
            problem = f"设 $f(x)=x^{{2}}e^{{{a}x}}$，求 $f'(x)$。"
        elif kind == 6:
            a = random.choice([1, 2, 3, 5])
            expr = f"log(x^2+{a})"
            expected = f"2*x/(x^2+{a})"
            problem = f"设 $f(x)=\\log(x^{{2}}+{a})$，求 $f'(x)$。"
        else:
            a, b = random.randint(2, 5), random.randint(1, 6)
            expr = f"sqrt({linear_str(a, b)})"
            expected = f"{a}/(2*sqrt({linear_str(a, b)}))"
            problem = f"设 $f(x)=\\sqrt{{{a}x{signed(b)}}}$，求 $f'(x)$。"
        made += int(add(cases, "derivative", problem,
                        {"op": "derivative", "expr": expr, "expected_expr": expected},
                        {"kind": "match"}))


def gen_latex_integral(cases):
    made, guard = 0, 0
    while made < 30 and guard < 2000:
        guard += 1
        kind = guard % 4
        if kind == 0:
            terms = [(random.choice([-3, -2, -1, 1, 2, 3]), p) for p in random.sample([0, 1, 2, 3], k=3)]
            a, b = random.choice([(0, 1), (0, 2), (1, 3), (-1, 1)])
            expr = poly_str(terms)
            value = integral_poly_value(terms, a, b)
            problem = f"求定积分 $\\int_{{{a}}}^{{{b}}}({poly_tex(terms)})\\,dx$ 的值。"
            args = {"op": "integrate_def", "expr": expr, "lower": str(a), "upper": str(b)}
        elif kind == 1:
            k = random.choice([2, 3])
            expr = f"sin({k}*x)"
            value = (1 - math.cos(k * math.pi)) / k
            problem = f"求定积分 $\\int_{{0}}^{{\\pi}}\\sin({k}x)\\,dx$ 的值。"
            args = {"op": "integrate_def", "expr": expr, "lower": "0", "upper": "pi"}
        elif kind == 2:
            b = random.choice([4, 9, 16])
            expr = "1/sqrt(x)"
            value = 2 * (math.sqrt(b) - 1)
            problem = f"求定积分 $\\int_{{1}}^{{{b}}}\\frac{{1}}{{\\sqrt{{x}}}}\\,dx$ 的值。"
            args = {"op": "integrate_def", "expr": expr, "lower": "1", "upper": str(b)}
        else:
            a = random.choice([1, 2, 3])
            expr = f"exp({a}*x)"
            value = (math.exp(a) - 1) / a
            problem = f"求定积分 $\\int_{{0}}^{{1}}e^{{{a}x}}\\,dx$ 的值。"
            args = {"op": "integrate_def", "expr": expr, "lower": "0", "upper": "1"}
        made += int(add(cases, "integrate", problem, args,
                        {"kind": "num", "value": float(value), "tol": 1e-5}))


def gen_derivative(cases):
    n = 0
    while len([c for c in cases if c["category"] == "derivative"]) < TARGETS["derivative"]:
        n += 1
        kind = n % 7
        if kind in (0, 1, 2):
            powers = random.sample([0, 1, 2, 3, 4], k=random.randint(2, 4))
            terms = [(random.choice([-6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6]), p) for p in powers]
            expr = poly_str(terms)
            expected = poly_str([(c * p, p - 1) for c, p in terms if p > 0]) or "0"
            problem = f"设 f(x) = {expr}，求 f'(x)。"
            check = {"kind": "match"}
        elif kind == 3:
            power = random.randint(2, 4)
            expr = f"x^{power}*sin(x)"
            expected = f"{power}*x^{power - 1}*sin(x)+x^{power}*cos(x)"
            problem = f"设 f(x) = {expr}，求 f'(x)。"
            check = {"kind": "match"}
        elif kind == 4:
            a, b = random.randint(1, 5), random.randint(-6, 6)
            c, d = random.randint(1, 4), random.randint(-6, 6)
            expr = f"({linear_str(a, b)})/({linear_str(c, d)})"
            expected = f"({a}*{d}-{b}*{c})/({linear_str(c, d)})^2"
            problem = f"设 f(x) = {expr}，求 f'(x)。"
            check = {"kind": "match"}
        elif kind == 5:
            a, b = random.randint(1, 5), random.randint(-4, 4)
            fn = random.choice(["sin", "cos", "exp", "log", "sqrt"])
            inner = linear_str(a, b)
            expr = f"{fn}({inner})"
            if fn == "sin":
                expected = f"{a}*cos({inner})"
            elif fn == "cos":
                expected = f"-{a}*sin({inner})"
            elif fn == "exp":
                expected = f"{a}*exp({inner})"
            elif fn == "log":
                expected = f"{a}/({inner})"
            else:
                expected = f"{a}/(2*sqrt({inner}))"
            problem = f"设 f(x) = {expr}，求 f'(x)。"
            check = {"kind": "match"}
        else:
            a = random.choice([1, 2, 3])
            expr, expected = random.choice([
                (f"x*exp({a}*x)", f"exp({a}*x)+{a}*x*exp({a}*x)"),
                (f"x^2*log(x)", "2*x*log(x)+x"),
                (f"atan({linear_str(a, 0)})", f"{a}/(1+({linear_str(a, 0)})^2)"),
                (f"exp({a}*x)*sin(x)", f"{a}*exp({a}*x)*sin(x)+exp({a}*x)*cos(x)"),
            ])
            problem = f"设 f(x) = {expr}，求 f'(x)。"
            check = {"kind": "match"}
        add(cases, "derivative", problem,
            {"op": "derivative", "expr": expr, "expected_expr": expected}, check)


def gen_simplify(cases):
    n = 0
    while len([c for c in cases if c["category"] == "simplify"]) < TARGETS["simplify"]:
        n += 1
        kind = n % 4
        if kind == 0:
            a, b = random.randint(1, 9), random.randint(1, 9)
            expr, expected = f"{a}*x+{b}*x", f"{a + b}*x"
        elif kind == 1:
            a, b = random.randint(2, 9), random.randint(1, 8)
            expr, expected = f"{a}*x-{b}*x", f"{a - b}*x"
        elif kind == 2:
            expr, expected = "x^2/x", "x"
        else:
            a = random.randint(2, 9)
            expr, expected = f"{a}*x^2/x", f"{a}*x"
        add(cases, "simplify", f"化简 {expr}。",
            {"op": "simplify", "expr": expr, "expected_expr": expected},
            {"kind": "match"})


def integral_poly_value(terms, a, b):
    total = Fraction(0)
    for c, p in terms:
        total += Fraction(c, p + 1) * (Fraction(b) ** (p + 1) - Fraction(a) ** (p + 1))
    return total


def gen_integrate(cases):
    n = 0
    while len([c for c in cases if c["category"] == "integrate"]) < TARGETS["integrate"]:
        n += 1
        if n % 4 == 0:
            k = random.randint(1, 3)
            lo, hi = 0, "pi"
            expr = f"sin({k}*x)" if k > 1 else "sin(x)"
            value = (1 - math.cos(k * math.pi)) / k
            problem = f"求定积分 ∫_{{0}}^{{π}} {expr} dx 的值。"
            add(cases, "integrate", problem,
                {"op": "integrate_def", "expr": expr, "lower": "0", "upper": "pi"},
                {"kind": "num", "value": value, "tol": 1e-5})
            continue
        if n % 7 == 0:
            expr = "e^x"
            problem = "求定积分 ∫_{0}^{1} e^x dx 的值。"
            add(cases, "integrate", problem,
                {"op": "integrate_def", "expr": expr, "lower": "0", "upper": "1"},
                {"kind": "num", "value": math.e - 1, "tol": 1e-5})
            continue
        powers = random.sample([0, 1, 2, 3], k=random.randint(2, 3))
        terms = [(random.choice([-4, -3, -2, -1, 1, 2, 3, 4]), p) for p in powers]
        expr = poly_str(terms)
        a, b = random.choice([(0, 1), (0, 2), (1, 3), (-1, 1), (0, 3)])
        value = integral_poly_value(terms, a, b)
        problem = f"求定积分 ∫_{{{a}}}^{{{b}}} {expr} dx 的值。"
        add(cases, "integrate", problem,
            {"op": "integrate_def", "expr": expr, "lower": str(a), "upper": str(b)},
            {"kind": "num", "value": float(value), "tol": 1e-5})


def gen_solve(cases):
    n = 0
    while len([c for c in cases if c["category"] == "solve"]) < TARGETS["solve"]:
        n += 1
        kind = n % 4
        if kind == 0:
            a = random.randint(1, 5)
            r1 = random.randint(-9, 9)
            r2 = random.choice([r for r in range(-9, 10) if r != r1])
            b, c = -a * (r1 + r2), a * r1 * r2
            expr = poly_str([(a, 2), (b, 1), (c, 0)]) + "=0"
            check = {"kind": "set", "values": [float(r1), float(r2)]}
        elif kind == 1:
            a = random.choice([2, 3, 4, 5])
            root = random.randint(-9, 9)
            b = random.randint(-9, 9)
            c = a * root + b
            expr = f"{a}*x+{b}={c}"
            check = {"kind": "set", "values": [float(root)]}
        elif kind == 2:
            base = random.choice([2, 3])
            k = random.randint(0, 3)
            m = random.randint(k + 2, k + 5)
            expr = f"{base}^(x+{k})={base}^{m}"
            root = m - k
            check = {"kind": "set", "values": [float(root)]}
        else:
            base = random.choice([2, 3])
            a = random.randint(0, 5)
            m = random.randint(2, 4)
            expr = f"log(x-{a},{base})={m}"
            root = a + base ** m
            check = {"kind": "set", "values": [float(root)]}
        add(cases, "solve", f"解方程 {expr}。", {"op": "solve", "expr": expr}, check)


def gen_stats(cases):
    n = 0
    ops = ["mean", "median", "variance_pop", "std", "iqr",
           "combination", "permutation", "binomial", "regression_slope", "regression_r"]
    while len([c for c in cases if c["category"] == "stats"]) < TARGETS["stats"]:
        op = ops[n % len(ops)]
        n += 1
        if op in ("mean", "median", "variance_pop", "std", "iqr"):
            size = random.randint(5, 8)
            xs = [random.randint(1, 20) for _ in range(size)]
            data = ",".join(map(str, xs))
            mean = Fraction(sum(xs), len(xs))
            if op == "mean":
                value = float(mean)
            elif op == "median":
                s = sorted(xs)
                value = float(s[len(s) // 2]) if len(s) % 2 else float(Fraction(s[len(s) // 2 - 1] + s[len(s) // 2], 2))
            elif op == "variance_pop":
                value = float(sum((Fraction(x) - mean) ** 2 for x in xs) / len(xs))
            elif op == "std":
                var_sample = sum((Fraction(x) - mean) ** 2 for x in xs) / (len(xs) - 1)
                value = math.sqrt(float(var_sample))
            else:
                s = sorted(xs)
                half = len(s) // 2
                lower = s[:half]
                upper = s[half + 1:] if len(s) % 2 else s[half:]
                med = lambda arr: Fraction(arr[len(arr) // 2]) if len(arr) % 2 else Fraction(arr[len(arr) // 2 - 1] + arr[len(arr) // 2], 2)
                value = float(med(upper) - med(lower))
            labels_extra = {"mean": "平均数", "median": "中位数", "variance_pop": "总体方差",
                            "std": "样本标准差", "iqr": "四分位距"}
            problem = f"求数据 {data} 的{labels_extra[op]}。"
            add(cases, "stats", problem,
                {"op": "stats", "stat_op": op, "data": data},
                {"kind": "num", "value": value, "tol": 1e-6}, stat_label=labels_extra[op])
        elif op in ("combination", "permutation"):
            nn = random.randint(5, 12)
            kk = random.randint(2, min(4, nn))
            value = math.comb(nn, kk) if op == "combination" else math.perm(nn, kk)
            problem = (f"求 C({nn},{kk}) 的值。" if op == "combination" else f"求 P({nn},{kk}) 的值。")
            label = "组合数" if op == "combination" else "排列数"
            add(cases, "stats", problem,
                {"op": "stats", "stat_op": op, "data": f"{nn},{kk}"},
                {"kind": "num", "value": float(value)}, stat_label=label)
        elif op == "binomial":
            nn = random.randint(5, 10)
            kk = random.randint(0, nn)
            p = random.choice([0.2, 0.25, 0.3, 0.4, 0.5])
            value = math.comb(nn, kk) * (p ** kk) * ((1 - p) ** (nn - kk))
            problem = f"设 X ~ B({nn}, {p})，求 P(X = {kk}) 的值。"
            add(cases, "stats", problem,
                {"op": "stats", "stat_op": "binomial", "data": f"{nn},{kk},{p}"},
                {"kind": "num", "value": value, "tol": 1e-9}, stat_label="概率")
        else:
            count = random.randint(4, 7)
            slope = random.choice([-2, -1.5, -1, 0.5, 1, 1.5, 2, 3])
            intercept = random.randint(-4, 5)
            noise = random.choice([0, 0, 0.1, 0.2, 0.3])
            pts = [(x, round(slope * x + intercept + random.uniform(-noise, noise), 3))
                   for x in range(1, count + 1)]
            # 期望值必须按写进 data 的同一份（已舍入）数据算，否则 CAS 与 Python 会差在舍入上
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            sxx = sum((x - mx) ** 2 for x in xs)
            sxy = sum((x - mx) * (y - my) for x, y in pts)
            syy = sum((y - my) ** 2 for y in ys)
            slope_v = sxy / sxx
            intercept_v = my - slope_v * mx
            r_v = sxy / math.sqrt(sxx * syy)
            data = ";".join(f"{x},{round(y, 3)}" for x, y in pts)
            if op == "regression_slope":
                problem = f"对数据 ({data.replace(';', '), (')}) 做线性回归，求回归直线的斜率。"
                field, value, label = "slope", slope_v, "回归直线斜率"
            else:
                problem = f"对数据 ({data.replace(';', '), (')})，求相关系数 r。"
                field, value, label = "r", r_v, "相关系数"
            add(cases, "stats", problem,
                {"op": "stats", "stat_op": "regression", "data": data},
                {"kind": "pick", "field": field, "value": value, "tol": 1e-5}, stat_label=label)


def gen_v3_targeted(cases):
    """v3 定向补数据：对应 v2 e2e 的失败题型（反函数/合成/余数/级数/行列式/
    二项式系数/正态概率/二项方差/反三角导数/面积），题面随机生成，不复制 69 题原题。"""
    blocked = eval_problem_set()

    # 反函数值：线性先解 y，再代值；二次反函数限定 x≥0 取正根
    made, guard = 0, 0
    while made < 25 and guard < 3000:
        guard += 1
        if guard % 2 == 0:
            a, b = random.choice([2, 3, 4, 5]), random.randint(-6, 6)
            c = a * random.randint(1, 8) + b
            problem = f"设 $f(x)={linear_tex(a, b)}$，求 $f^{{-1}}({c})$ 的值。"
            expr, value = f"({c}-{b})/{a}", (c - b) / a
        else:
            b = random.randint(1, 6)
            c = b + random.choice([1, 4, 9, 16, 25, 36])
            problem = f"设 $f(x)=x^2+{b}$（$x\\ge 0$），求 $f^{{-1}}({c})$ 的值。"
            expr, value = f"sqrt({c}-{b})", math.sqrt(c - b)
        if problem in blocked:
            continue
        made += int(add(cases, "eval", problem, {"op": "eval", "expr": expr},
                        {"kind": "num", "value": value}))

    # 复合函数值：先算内层再代入外层
    made, guard = 0, 0
    while made < 25 and guard < 3000:
        guard += 1
        a = random.randint(1, 4)
        b, c = random.choice([2, 3, 4]), random.randint(-5, 5)
        t = random.randint(-3, 4)
        if guard % 2 == 0:
            problem = f"设 $f(x)=x^2+{a}$，$g(x)={linear_tex(b, c)}$，求 $f(g({t}))$ 的值。"
            expr, value = f"({b}*({t})+{c})^2+{a}", (b * t + c) ** 2 + a
        else:
            problem = f"设 $f(x)=x^2+{a}$，$g(x)={linear_tex(b, c)}$，求 $g(f({t}))$ 的值。"
            expr, value = f"{b}*(({t})^2+{a})+{c}", b * (t * t + a) + c
        if problem in blocked:
            continue
        made += int(add(cases, "eval", problem, {"op": "eval", "expr": expr},
                        {"kind": "num", "value": float(value)}))

    # 余数定理加量：P(x) 除以 x-a 的余数 = P(a)
    made, guard = 0, 0
    while made < 40 and guard < 5000:
        guard += 1
        a = random.randint(-5, 5)
        deg = random.randint(2, 4)
        terms = [(random.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5]), p)
                 for p in range(deg, -1, -1)]
        problem = f"求多项式 ${poly_tex(terms)}$ 除以 $x{signed(-a)}$ 的余数。"
        if problem in blocked:
            continue
        value = sum(co * (a ** p) for co, p in terms)
        made += int(add(cases, "eval", problem,
                        {"op": "eval", "expr": poly_str(terms).replace("x", f"({a})")},
                        {"kind": "num", "value": float(value)}))

    # 等比数列求和：首项到 a*r^k 共 k+1 项，和 = a*(r^(k+1)-1)/(r-1)
    made, guard = 0, 0
    while made < 40 and guard < 4000:
        guard += 1
        r, a = random.choice([2, 3]), random.choice([1, 2, 3])
        k_last = random.randint(5, 12)
        terms = "+".join(str(a * r ** i) for i in range(3)) + f"+\\cdots+{a * r ** k_last}"
        problem = f"求 ${terms}$ {'的和' if guard % 2 else '的值'}。"
        if problem in blocked:
            continue
        value = a * (r ** (k_last + 1) - 1) // (r - 1)
        made += int(add(cases, "eval", problem,
                        {"op": "eval", "expr": f"{a}*({r}^{k_last + 1}-1)/({r}-1)"},
                        {"kind": "num", "value": float(value)}))

    # 二阶行列式
    made, guard = 0, 0
    while made < 25 and guard < 4000:
        guard += 1
        a, b, c, d = (random.randint(-6, 9) for _ in range(4))
        if a * d == b * c:
            continue
        problem = f"求行列式 $\\begin{{vmatrix}}{a}&{b}\\\\{c}&{d}\\end{{vmatrix}}$ 的值。"
        if problem in blocked:
            continue
        made += int(add(cases, "eval", problem,
                        {"op": "eval", "expr": f"{a}*{d}-{b}*{c}"},
                        {"kind": "num", "value": float(a * d - b * c)}))

    # 二项式系数 LaTeX：\binom{n}{k} 走 stats combination
    made, guard = 0, 0
    while made < 30 and guard < 3000:
        guard += 1
        n = random.randint(6, 20)
        k = random.randint(2, min(6, n - 1))
        problem = f"求 $\\binom{{{n}}}{{{k}}}$ 的值。"
        if problem in blocked:
            continue
        made += int(add(cases, "stats", problem,
                        {"op": "stats", "stat_op": "combination", "data": f"{n},{k}"},
                        {"kind": "num", "value": float(math.comb(n, k))}, stat_label="组合数"))

    # 正态概率（LaTeX 题面，贴近试卷写法）
    made, guard = 0, 0
    while made < 40 and guard < 4000:
        guard += 1
        mu = random.choice([45, 50, 55, 60, 65, 70, 75, 80, 85, 90])
        sigma = random.choice([4, 5, 8, 10, 12, 15])
        x = mu + random.choice([-3, -2, -1, 1, 2, 3]) * random.choice([2, 3, 5])
        problem = f"设 $X\\sim N({mu},{sigma}^2)$，求 $P(X<{x})$（保留四位小数）。"
        if problem in blocked:
            continue
        value = 0.5 * (1 + math.erf((x - mu) / (sigma * math.sqrt(2))))
        made += int(add(cases, "stats", problem,
                        {"op": "stats", "stat_op": "normalcdf", "data": f"{mu},{sigma},{x}"},
                        {"kind": "num", "value": value, "tol": 1e-6}, stat_label="概率"))

    # 二项分布方差：Var(X) = n p (1-p)
    made, guard = 0, 0
    while made < 30 and guard < 3000:
        guard += 1
        n = random.randint(8, 30)
        p = random.choice([0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7])
        q = round(1 - p, 2)
        problem = f"设 $X\\sim B({n},{p})$，求 $\\operatorname{{Var}}(X)$。"
        if problem in blocked:
            continue
        made += int(add(cases, "word", problem,
                        {"op": "eval", "expr": f"{n}*{p}*{q}"},
                        {"kind": "num", "value": n * p * q}))

    # 反三角导数（避免与 eval 的 arctan x 原题逐字相同，用系数变式）
    made, guard = 0, 0
    while made < 30 and guard < 3000:
        guard += 1
        a = random.choice([2, 3, 4])
        kind = guard % 4
        if kind == 0:
            problem = f"设 $f(x)=\\arctan({a}x)$，求 $f'(x)$。"
            expr, expected = f"atan({a}*x)", f"{a}/(1+({a}*x)^2)"
        elif kind == 1:
            problem = f"设 $f(x)={a}\\arctan x$，求 $f'(x)$。"
            expr, expected = f"{a}*atan(x)", f"{a}/(1+x^2)"
        elif kind == 2:
            problem = f"设 $f(x)=\\arcsin({a}x)$，求 $f'(x)$。"
            expr, expected = f"asin({a}*x)", f"{a}/sqrt(1-({a}*x)^2)"
        else:
            problem = f"设 $f(x)=\\arccos({a}x)$，求 $f'(x)$。"
            expr, expected = f"acos({a}*x)", f"-{a}/sqrt(1-({a}*x)^2)"
        if problem in blocked:
            continue
        made += int(add(cases, "derivative", problem,
                        {"op": "derivative", "expr": expr, "expected_expr": expected},
                        {"kind": "match"}))

    # 面积加量：上曲线减下曲线
    made, guard = 0, 0
    while made < 30 and guard < 4000:
        guard += 1
        a, b = random.choice([(0, 1), (0, 2), (1, 2), (1, 3), (-1, 1)])
        k = random.choice([1, 2, 3, 4])
        m, c0 = random.randint(-3, 3), random.randint(-4, 4)
        g_terms = [(m, 1), (c0, 0)]
        h_terms = [(-k, 2), (k * (a + b), 1), (-k * a * b, 0)]
        f_terms = [(h_terms[0][0], 2), (h_terms[1][0] + m, 1), (h_terms[2][0] + c0, 0)]
        problem = (f"求曲线 $y={poly_tex(f_terms)}$ 与 $y={poly_tex(g_terms)}$ "
                   f"在 $[{a},{b}]$ 上围成的面积。")
        if problem in blocked:
            continue
        value = Fraction(k * (b - a) ** 3, 6)
        made += int(add(cases, "area", problem,
                        {"op": "integrate_def", "expr": poly_str(h_terms),
                         "lower": str(a), "upper": str(b)},
                        {"kind": "num", "value": float(value), "tol": 1e-6}))


def gen_v4_targeted(cases):
    """v4：两点距离、等差数列、等比数列加量、题面先给下方曲线的面积题。"""
    blocked = eval_problem_set()

    # 两点距离公式
    made, guard = 0, 0
    while made < 30 and guard < 3000:
        guard += 1
        x1, y1 = random.randint(-5, 5), random.randint(-5, 5)
        x2, y2 = random.randint(-5, 8), random.randint(-5, 8)
        if (x1, y1) == (x2, y2):
            continue
        problem = f"求点 $({x1},{y1})$ 与 $({x2},{y2})$ 之间的距离。"
        if problem in blocked:
            continue
        made += int(add(cases, "eval", problem,
                        {"op": "eval", "expr": f"sqrt(({x2}-{x1})^2+({y2}-{y1})^2)"},
                        {"kind": "num", "value": math.hypot(x2 - x1, y2 - y1)}))

    # 1+2+…+n
    made, guard = 0, 0
    while made < 30 and guard < 2000:
        guard += 1
        n = random.randint(5, 40)
        problem = f"求 $1+2+3+\\cdots+{n}$ 的和。"
        if problem in blocked:
            continue
        made += int(add(cases, "eval", problem,
                        {"op": "eval", "expr": f"{n}*({n}+1)/2"},
                        {"kind": "num", "value": float(n * (n + 1) // 2)}))

    # 等比数列：首项 a、公比 r，末项 a*r^k，共 k+1 项
    made, guard = 0, 0
    while made < 30 and guard < 3000:
        guard += 1
        a, r = random.choice([1, 2, 3]), random.choice([2, 3])
        k = random.randint(6, 12)
        problem = (f"求 ${a}+{a * r}+{a * r ** 2}+\\cdots+{a * r ** k}$ 的和。")
        if problem in blocked:
            continue
        made += int(add(cases, "eval", problem,
                        {"op": "eval", "expr": f"{a}*({r}^{k + 1}-1)/({r}-1)"},
                        {"kind": "num", "value": float(a * (r ** (k + 1) - 1) // (r - 1))}))

    # 面积：题面先给下方曲线（lower 在前），仍要用上曲线减下曲线
    made, guard = 0, 0
    while made < 30 and guard < 4000:
        guard += 1
        a, b = random.choice([(0, 1), (0, 2), (1, 2), (1, 3), (-1, 1)])
        k = random.choice([1, 2, 3, 4])
        m, c0 = random.randint(-3, 3), random.randint(-4, 4)
        lower = [(m, 1), (c0, 0)]
        upper = [(-k, 2), (m + k * (a + b), 1), (c0 - k * a * b, 0)]
        problem = (f"求曲线 $y={poly_tex(lower)}$ 与 $y={poly_tex(upper)}$ "
                   f"在 $[{a},{b}]$ 上围成的面积。")
        if problem in blocked:
            continue
        h = [(-k, 2), (k * (a + b), 1), (-k * a * b, 0)]
        value = Fraction(k * (b - a) ** 3, 6)
        made += int(add(cases, "area", problem,
                        {"op": "integrate_def", "expr": poly_str(h),
                         "lower": str(a), "upper": str(b)},
                        {"kind": "num", "value": float(value), "tol": 1e-6}))


def verify(case, result):
    check = case["check"]
    if result.get("status") != "ok":
        return False, result.get("result", "CAS error")
    text = result["result"]
    try:
        if check["kind"] == "match":
            if not result.get("match"):
                return False, "表达式采样点对拍不一致"
        elif check["kind"] == "num":
            value = parse_cas_number(text)
            if not close(value, check["value"], check.get("tol", 1e-6)):
                return False, f"{value} vs {check['value']}"
        elif check["kind"] == "set":
            parts = [p.strip() for p in text.replace("（数值解）", "").split(",") if p.strip()]
            values = [parse_cas_number(p) for p in parts]
            for want in check["values"]:
                if not any(close(v, want, check.get("tol", 1e-6)) for v in values):
                    return False, f"缺根 {want}: {values}"
        elif check["kind"] == "pick":
            value = pick_field(text, check["field"])
            if value is None:
                return False, "结果缺字段"
            if not close(parse_cas_number(value), check["value"], check.get("tol", 1e-6)):
                return False, f"{value} vs {check['value']}"
    except Exception as exc:
        return False, f"校验异常 {exc}"
    return True, ""


def make_rows(case, result):
    args = {k: v for k, v in case["args"].items() if k != "expected_expr"}
    call = "<tool_call>\n" + json.dumps(
        {"name": "math_eval", "arguments": args}, ensure_ascii=False) + "\n</tool_call>"
    content = result["result"] + ("（数值解）" if result["numeric"] else "")
    tool = json.dumps({"status": "ok", "result": content}, ensure_ascii=False, separators=(",", ":"))
    head = [{"role": "system", "content": USAGE_PROMPT},
            {"role": "user", "content": case["problem"]}]
    answer_text = explain(case["category"], result["result"], case) + \
        "\n【答案】" + final_answer(case["category"], result["result"], case)
    call_row = {"messages": head + [{"role": "assistant", "content": call}],
                "category": "math_eval_call", "source": "math_eval_synth"}
    answer_row = {"messages": head + [
        {"role": "assistant", "content": call},
        {"role": "tool", "content": tool},
        {"role": "assistant", "content": answer_text},
    ], "category": "math_eval_answer", "source": "math_eval_synth"}
    return [call_row, answer_row]


def main():
    random.seed(20261108)
    os.makedirs(OUTDIR, exist_ok=True)
    cases = []
    gen_eval(cases)
    gen_word(cases)
    gen_derivative(cases)
    gen_latex_derivative(cases)
    gen_latex_rational(cases)
    gen_latex_explog(cases)
    gen_simplify(cases)
    gen_integrate(cases)
    gen_latex_integral(cases)
    gen_solve(cases)
    gen_stats(cases)
    gen_normalcdf(cases)
    gen_binomial(cases)
    gen_precalc_words(cases)
    gen_area(cases)
    gen_v3_targeted(cases)
    gen_v4_targeted(cases)

    req_path = os.path.join(OUTDIR, "requests.jsonl")
    res_path = os.path.join(OUTDIR, "results.jsonl")
    with open(req_path, "w", encoding="utf-8") as f:
        for case in cases:
            row = {"id": case["id"],
                   **{k: v for k, v in case["args"].items() if k != "expected_expr"}}
            if "expected_expr" in case["args"]:
                row["expected_expr"] = case["args"]["expected_expr"]
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    subprocess.run(["node", BATCH, req_path, res_path], check=True)
    results = {}
    with open(res_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            results[row["id"]] = row

    verified, dropped = [], []
    for case in cases:
        result = results.get(case["id"])
        if result is None:
            dropped.append((case["id"], "missing"))
            continue
        ok, reason = verify(case, result)
        if ok:
            verified.append((case, result))
        else:
            dropped.append((case["id"], reason))

    rows = []
    for case, result in verified:
        rows.extend(make_rows(case, result))

    # 分层抽 val：每类取约 5%
    by_cat = {}
    for row in rows:
        by_cat.setdefault(row["category"], []).append(row)
    val_ids = set()
    for cat_rows in by_cat.values():
        take = max(1, int(len(cat_rows) * 0.05))
        val_ids.update(id(r) for r in cat_rows[:take])
    train = [r for r in rows if id(r) not in val_ids]
    val = [r for r in rows if id(r) in val_ids]

    def write_jsonl(path, items):
        with open(path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    write_jsonl(os.path.join(OUTDIR, "all.jsonl"), rows)
    write_jsonl(os.path.join(OUTDIR, "train.jsonl"), train)
    write_jsonl(os.path.join(OUTDIR, "val.jsonl"), val)

    cat_counts = {}
    for case, _ in verified:
        cat_counts[case["category"]] = cat_counts.get(case["category"], 0) + 1
    report = {
        "cases": len(cases),
        "verified": len(verified),
        "dropped": dropped[:30],
        "dropped_count": len(dropped),
        "by_category": cat_counts,
        "rows": len(rows),
        "train": len(train),
        "val": len(val),
    }
    with open(os.path.join(OUTDIR, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUTDIR, "preview.txt"), "w", encoding="utf-8") as f:
        for row in rows[:2]:
            f.write(json.dumps(row, ensure_ascii=False)[:1500] + "\n\n")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
