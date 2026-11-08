#!/usr/bin/env python3
"""生成 CAS 一期验收数据：apps/demo-cli/Sources/demo-cli/Resources/calc_acceptance.json

口径（docs/plans/数学CAS工具接入.md 一期）：
- 从 train/eval/math_eval.json 的 69 题里取「求值/求导/定积分/统计/解方程」纯计算子集；
- 应用题、极限、证明、最值、参数方程、化简/因式分解不进子集（列式与推导本身是考点，
  CAS 只保证算得准，不保证读得懂题）；
- 每题声明 1-2 个 CAS 步骤，期望答案沿用 math_eval.json 的 expected/tol；表达式里的
  Python 幂运算 ** 转成 math.js 的 ^。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "train", "eval", "math_eval.json")
OUT = os.path.join(ROOT, "apps", "demo-cli", "Sources", "demo-cli", "Resources", "calc_acceptance.json")

# id -> (steps, 备注)；steps 里 use_previous 表示把上一步结果当 expr
MAPPING = {
    # ---- AP Calculus：求导 / 定积分 / 求值 ----
    # 隐式乘法（2x/5x）是学生最常见的写法，专门留作解析回归
    "ap_calc-01": [{"op": "derivative", "expr": "2x^3-5x^2+3x-7"}],
    "ap_calc-02": [{"op": "derivative", "expr": "x^2*sin(x)"}],
    "ap_calc-03": [{"op": "derivative", "expr": "(3*x+1)/(x-2)"}],
    "ap_calc-04": [{"op": "derivative", "expr": "sin(4*x-1)"}],
    "ap_calc-05": [{"op": "derivative", "expr": "e^(3*x)+log(2*x)"}],
    "ap_calc-06": [{"op": "derivative", "expr": "x^2*e^x"}],
    "ap_calc-07": [{"op": "derivative", "expr": "log(x^2+1)"}],
    "ap_calc-08": [{"op": "derivative", "expr": "sqrt(5*x+2)"}],
    "ap_calc-10": [{"op": "integrate_def", "expr": "x^3-2*x+1", "lower": "0", "upper": "2"}],
    "ap_calc-11": [{"op": "integrate_def", "expr": "1/sqrt(x)", "lower": "1", "upper": "4"}],
    "ap_calc-12": [{"op": "integrate_def", "expr": "sin(2*x)", "lower": "0", "upper": "pi"}],
    "ap_calc-16": [
        {"op": "derivative", "expr": "x^3-3*x"},
        {"op": "solve", "use_previous": True},
    ],
    "ap_calc-18": [{"op": "integrate_def", "expr": "x^2/3", "lower": "0", "upper": "3"}],
    "ap_calc-22": [{"op": "integrate_def", "expr": "x-x^2", "lower": "0", "upper": "1"}],
    "ap_calc-23": [
        {"op": "derivative", "expr": "x^3-6*x^2+9*x"},
        {"op": "solve", "use_previous": True},
    ],
    "ap_calc-24": [{"op": "eval", "expr": "2^3"}],
    "ap_calc-25": [{"op": "derivative", "expr": "atan(x)"}],
    # ---- Precalculus：求值 / 解方程 ----
    "precalc-01": [{"op": "eval", "expr": "log(32,2)"}],
    "precalc-02": [{"op": "eval", "expr": "log(1/9,3)"}],
    "precalc-03": [{"op": "solve", "expr": "2^(x+1)=32"}],
    "precalc-04": [{"op": "solve", "expr": "log(x-1,2)=3"}],
    "precalc-05": [{"op": "eval", "expr": "sin(pi/6)"}],
    "precalc-06": [{"op": "eval", "expr": "cos(2*pi/3)"}],
    "precalc-07": [{"op": "eval", "expr": "tan(pi/4)"}],
    "precalc-08": [{"op": "eval", "expr": "sin(7*pi/6)"}],
    "precalc-10": [{"op": "solve", "expr": "2*x+3=7"}],
    "precalc-11": [{"op": "eval", "expr": "(2*2-1)^2+1"}],
    "precalc-12": [{"op": "eval", "expr": "2^3-2*2^2+4*2-1"}],
    "precalc-14": [{"op": "eval", "expr": "3+9*4"}],
    "precalc-15": [{"op": "eval", "expr": "2^10-1"}],
    "precalc-16": [{"op": "stats", "stat_op": "combination", "data": "8,3"}],
    "precalc-17": [{"op": "eval", "expr": "3*5-4*2"}],
    "precalc-19": [{"op": "eval", "expr": "sqrt((4-1)^2+(6-2)^2)"}],
    "precalc-21": [{"op": "eval", "expr": "20*21/2"}],
    "precalc-22": [{"op": "eval", "expr": "150*pi/180"}],
    "precalc-23": [{"op": "eval", "expr": "abs(3+4i)"}],
    "precalc-24": [{"op": "solve", "expr": "x^2-5x+6=0"}],
    # ---- AP Statistics ----
    "ap_stats-01": [{"op": "stats", "stat_op": "mean", "data": "4,8,6,10,2"}],
    "ap_stats-02": [{"op": "stats", "stat_op": "median", "data": "3,7,9,4,5"}],
    "ap_stats-03": [{"op": "stats", "stat_op": "variance_pop", "data": "2,4,6,8"}],
    "ap_stats-04": [{"op": "stats", "stat_op": "std", "data": "2,4,6,8"}],
    "ap_stats-05": [{"op": "eval", "expr": "(85-70)/10"}],
    "ap_stats-06": [{"op": "eval", "expr": "0.5*(1+erf(5/(10*sqrt(2))))"}],
    "ap_stats-07": [{"op": "stats", "stat_op": "binomial", "data": "5,3,0.4"}],
    "ap_stats-08": [{"op": "eval", "expr": "0*0.2+1*0.5+2*0.3"}],
    "ap_stats-09": [{"op": "stats", "stat_op": "regression", "data": "1,2;2,4;3,5;4,8", "pick": "slope"}],
    "ap_stats-10": [{"op": "stats", "stat_op": "regression", "data": "1,2;2,4;3,5;4,8", "pick": "r"}],
    "ap_stats-11": [{"op": "eval", "expr": "1.96*10/sqrt(25)"}],
    "ap_stats-12": [{"op": "eval", "expr": "0.5+0.4-0.2"}],
    "ap_stats-13": [{"op": "eval", "expr": "0.2/0.4"}],
    "ap_stats-14": [{"op": "stats", "stat_op": "combination", "data": "10,2"}],
    "ap_stats-15": [{"op": "stats", "stat_op": "permutation", "data": "10,3"}],
    "ap_stats-16": [{"op": "eval", "expr": "10/sqrt(25)"}],
    "ap_stats-17": [{"op": "stats", "stat_op": "iqr", "data": "1,3,5,7,9,11,13,15"}],
    "ap_stats-18": [{"op": "eval", "expr": "20*0.3"}],
    "ap_stats-19": [{"op": "eval", "expr": "20*0.3*0.7"}],
}


def kind_of(case):
    if case["answer_type"] == "set":
        return "set"
    expected = case["expected"]
    if "x" in expected:
        return "expr"
    try:
        float(expected)
        return "num"
    except ValueError:
        return "expr"


def main():
    cases = {c["id"]: c for c in json.load(open(SRC, encoding="utf-8"))}
    out = []
    for cid, steps in MAPPING.items():
        case = cases[cid]
        kind = kind_of(case)
        item = {
            "id": cid,
            "category": case["category"],
            "topic": case["topic"],
            "problem": case["problem"],
            "steps": [
                {k: v for k, v in step.items()}
                for step in steps
            ],
            "kind": kind,
            "tol": case.get("tol", 1e-6),
        }
        if kind == "set":
            item["expect_set"] = json.loads(case["expected"])
        elif kind == "num":
            item["expect_num"] = float(case["expected"])
        else:
            item["expect_expr"] = case["expected"].replace("**", "^")
        out.append(item)

    used = set(MAPPING)
    excluded = [cid for cid in cases if cid not in used]
    payload = {
        "source": "train/eval/math_eval.json（69 题纯计算子集）",
        "note": "排除项：不定积分/极限/最值/切线/二阶/参数方程/化简/因式分解/方程组/圆等需要推导或本期未覆盖的能力",
        "excluded": excluded,
        "cases": out,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"wrote {OUT}: {len(out)} cases, excluded {len(excluded)} -> {', '.join(excluded)}")


if __name__ == "__main__":
    main()
