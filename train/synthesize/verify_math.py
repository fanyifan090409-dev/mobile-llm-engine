#!/usr/bin/env python3
"""SymPy 数学验证：对学术合成样本（ap_calc/ap_stats/precalc）做答案符号/数值对拍。

背景：合成 QC（qc_sft.py）只查格式（标记块/公式残缺），不查数学对错。teacher 生成的
题面/答案若算错，照样进训练池拖累正确率。本脚本用 SymPy 独立重算，把「答案错误」的
样本判违规，hash 写入 violations.jsonl，由 assemble_train.py --exclude 过滤。

原则（防误杀）：
  - 只判「可验证子集」：题型可分类且 LaTeX 可解析的样本才出判定；
  - 解析失败 / 题型不支持 / 数值抽样全遇奇点 → skip（计入报告，不算违规）；
  - 判违规标准：数值抽样多点对拍不一致（容差 rel 1e-3 + abs 1e-3，teacher 答案常写小数近似）。
第一版不判「根找全了没」（solve_eq 只验答案给的是根），不判级数收敛（skip 统计）。

用法：
  python3 verify_math.py --dir data/sft19 --outdir /tmp/verify_out
输出：<outdir>/violations.jsonl（违规样本）+ verify_report.txt（统计）。
"""
import argparse
import glob
import json
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")
import sympy
from sympy.core.relational import Relational
from sympy.parsing.latex import parse_latex

X = sympy.Symbol("x")

# 函数赋值前缀：f(x) = …、f'(x) = …、f''(x) = …、y = … 剥离后取右边表达式
# （parse_latex 会把 f(x)=expr 解析成 Eq(f(x), expr)，f'(x) 甚至解析失败）；
# 容忍前导空格（teacher 常写 $ f(x) = ... $）。左边是 x 的不剥（solve_eq 需要 Eq(x, v) 形态）
FN_ASSIGN_RE = re.compile(r"^\s*([a-zA-Z]+)(?:''|'|″|″)?\s*(?:\(x\))?\s*=")

# 数值抽样点：刻意取不规整值避开 teacher 常设的 0/1/2 奇点；遇奇点跳过该点不判
SAMPLE_POINTS = [0.13, -0.37, 0.71, -1.23, 1.79, -2.31, 2.87]
TOL_REL = 1e-3
TOL_ABS = 1e-3

MATH_CATS = {"ap_calc", "ap_stats", "precalc"}

# $$ 块优先（teacher 多用 $$...$$ 包裹），再匹配单 $
MATH_BLOCK = re.compile(r"\$\$(.*?)\$\$|\$(.*?)\$", re.S)
MARKER_END = ("【题目】", "【答案】", "【解答】", "【解析】", "【思路】", "【点评】",
              "【文章】", "【听力文本】")
# 「在 x = a 处求值」模式：题目无显式结果对象时提取代入点（容忍 $ 包裹）
AT_POINT_RE = re.compile(r"在\s*\$?\s*x\s*=\s*(-?[\d.]+)\s*\$?\s*处")


def clean_latex(s):
    """teacher LaTeX 常见非规范写法预处理，转成 parse_latex 可接受的形态。"""
    s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    s = s.replace("\\displaystyle", "").replace("\\left", "").replace("\\right", "")
    s = re.sub(r"\\text\{[^}]*\}", "", s)
    s = s.replace("\\,", "").replace("\\;", "").replace("\\!", "").replace("\\quad", " ")
    return s


def strip_assign(seg):
    """剥掉函数赋值前缀（f(x) = / f'(x) = / y =），返回纯表达式段；左边是 x 时保留。"""
    m = FN_ASSIGN_RE.match(seg)
    if m and m.group(1) != "x":
        return seg[m.end():].strip()
    return seg


def try_parse(latex_seg):
    try:
        obj = parse_latex(clean_latex(strip_assign(latex_seg)))
        # parse_latex 把 e 解析成普通符号（非自然对数底 E），log(e) 将永远无法数值化；
        # AP 数学里 e 必是欧拉数，统一替换
        e_sym = sympy.Symbol("e")
        if e_sym in obj.free_symbols:
            obj = obj.subs(e_sym, sympy.E)
        return obj
    except Exception:
        return None


def extract_maths(text):
    return [m.group(1) or m.group(2) for m in MATH_BLOCK.finditer(text) if (m.group(1) or m.group(2))]


def block_of(text, marker):
    """取 marker 到下一个【】标记之间的内容（无下一个标记则到结尾）。"""
    if marker not in text:
        return ""
    seg = text.split(marker, 1)[1]
    for m in MARKER_END:
        if m == marker:
            continue
        if m in seg:
            seg = seg.split(m)[0]
    return seg.strip()


def problem_text(rec):
    """题面：problem_gen 取 assistant【题目】块；solve 取 user 最后一条（剥掉「请解答」前缀）。"""
    form = rec.get("form")
    msgs = rec.get("messages") or []
    if form == "problem_gen":
        asst = next((str(m.get("content") or "") for m in reversed(msgs)
                     if m.get("role") == "assistant"), "")
        t = block_of(asst, "【题目】")
        return t or asst
    user = next((str(m.get("content") or "") for m in reversed(msgs)
                 if m.get("role") == "user"), "")
    if "请解答下面这道" in user:
        user = user.split("请解答下面这道", 1)[1]
        # 合成模板「…验算确认。\n题目：\n{题面}」：题面在最后的「题目：」之后（rfind 防题面含字样）
        pos = user.rfind("题目：")
        if pos >= 0:
            user = user[pos + len("题目："):]
        elif "答案：" in user:
            user = user.split("答案：", 1)[1]
        else:
            # 无「题目：/答案：」分界：格式要求尾巴在题面之前，取最后一条尾巴之后的文本
            best = max(((user.rfind(t), t) for t in
                        ("请写出详细步骤", "写出详细步骤", "最后明确给出答案")),
                       key=lambda kv: kv[0])
            if best[0] >= 0:
                user = user[best[0] + len(best[1]):].lstrip("：:。 \n")
    return user


def answer_text(rec):
    msgs = rec.get("messages") or []
    asst = next((str(m.get("content") or "") for m in reversed(msgs)
                 if m.get("role") == "assistant"), "")
    return block_of(asst, "【答案】")


def is_plain_expr(obj):
    """普通含 x 表达式：不是关系式（x>0 定义域之类）、不是 Limit/Integral/Eq。"""
    return (isinstance(obj, sympy.Expr) and not isinstance(obj, Relational)
            and not isinstance(obj, (sympy.Limit, sympy.Integral, sympy.Sum)))


def classify(problem):
    if re.search(r"求导|导数|f'|f''|f″|dy/dx|d y/d x|隐函数求导|切线", problem):
        return "derivative"
    if "极限" in problem or "lim" in problem or "\\lim" in problem:
        return "limit"
    if "不定积分" in problem or "原函数" in problem or "∫" in problem and "_" not in problem:
        return "integral_indef"
    if "定积分" in problem or ("∫" in problem and "_" in problem) or "\\int_" in problem:
        return "integral_def"
    if re.search(r"级数|收敛|发散|泰勒|麦克劳林|求和", problem):
        return "series"
    if re.search(r"解方程|求根|求解|的根|根为", problem):
        return "solve_eq"
    if re.search(r"求值|计算|化简|求|的值|等于|在\s*x\s*=", problem):
        return "evaluate"
    return "other"


def _to_float(obj):
    """sympy 对象 → float；符号残留（如 log(e) 未化简）先 N 数值化，失败返回 None。"""
    try:
        if not obj.is_number:
            obj = sympy.N(obj)
        v = complex(obj)
    except Exception:
        return None
    if abs(v.imag) > 1e-8:
        return None
    return v.real


def eval_at(expr, point):
    """代入求值；遇奇点（除零/复数/符号残留）返回 None。"""
    try:
        return _to_float(expr.subs(X, point))
    except Exception:
        return None


def close(a, b):
    try:
        return abs(a - b) <= TOL_ABS + TOL_REL * abs(b)
    except Exception:
        return False


def num_of(obj):
    """把答案对象转数值：Limit/Integral/Sum 先 doit，再数值化（符号残留 N 兜底）。"""
    try:
        if isinstance(obj, (sympy.Limit, sympy.Integral, sympy.Sum)):
            obj = obj.doit()
        return _to_float(obj)
    except Exception:
        return None


def parse_first(text, want_x=False):
    """解析文本第一个 math 块。want_x=True 时要求是含 x 的普通表达式，跳过关系式等。"""
    for seg in extract_maths(text):
        obj = try_parse(seg)
        if obj is None:
            continue
        if want_x:
            if is_plain_expr(obj) and X in obj.free_symbols:
                return obj
        else:
            return obj
    return None


def parse_main_obj(problem):
    """题目主对象：Limit/Integral/Eq/普通含 x 表达式，按出现顺序取第一个可用的。
    「x = 数字」代入点声明（不是题目对象）跳过。"""
    for seg in extract_maths(problem):
        obj = try_parse(seg)
        if obj is None:
            continue
        if isinstance(obj, sympy.Eq) and obj.lhs == X and obj.rhs.is_number:
            continue
        if isinstance(obj, (sympy.Limit, sympy.Integral, sympy.Eq)):
            return obj
        if is_plain_expr(obj) and X in obj.free_symbols:
            return obj
    return None


def sample_match(fn_a, fn_b, points=SAMPLE_POINTS):
    """数值抽样对拍：所有可算点都一致才判对；一个点都不一致且无点可算 → None（不判）。"""
    ok = bad = 0
    for p in points:
        va = eval_at(fn_a, p)
        vb = eval_at(fn_b, p)
        if va is None or vb is None:
            continue
        if close(va, vb):
            ok += 1
        else:
            bad += 1
    if bad:
        return False
    return True if ok else None


def verify(rec):
    """返回 (verdict, note)。verdict ∈ ok / mismatch / skip。"""
    problem = problem_text(rec)
    answer = answer_text(rec)
    # solve 出题轨迹：user 要题、assistant 只给【题目】，无答案可验（合法样本，不适用验证）
    if rec.get("form") == "solve" and not answer:
        return "skip", "出题轨迹（无答案）"
    if len(problem) < 20 or not answer:
        return "skip", "题面或答案缺失"
    kind = classify(problem)
    if kind == "other":
        return "skip", "题型未分类(other)"
    if kind == "series":
        return "skip", "级数类第一版不验证"

    if kind == "derivative":
        # 守卫：表值题/已知导函数题不是求导对拍范围（2026-11-02 harness 批次 4 条误杀实发——
        # 表值题无解析表达式；「已知 f'(x)=… 求原函数/参数」答案不是导数）
        if re.search(r"如下表|\\begin\{array|\\hline", problem):
            return "skip", "表值题不验证"
        if re.search(r"f['′]\s*\(?x\)?\s*=", problem):
            return "skip", "已知导函数题不验证"
        fobj = parse_main_obj(problem)
        aobj = parse_first(answer, want_x=True)
        if fobj is None or aobj is None:
            return "skip", "题目函数或答案导数不可解析"
        if isinstance(fobj, sympy.Eq) and fobj.lhs.has(sympy.Derivative):
            return "skip", "已知导函数题不验证"
        fp = sympy.diff(fobj, X)
        r = sample_match(fp, aobj)
        return (("ok", "导数对拍一致") if r else ("mismatch", f"导数不一致: d/dx[{fobj}]={fp} vs {aobj}") if r is False else ("skip", "导数抽样全遇奇点"))

    if kind == "limit":
        mobj = parse_main_obj(problem)
        if isinstance(mobj, sympy.Limit):
            val = num_of(mobj)
        else:
            return "skip", "极限结构不可解析"
        aval = num_of(parse_first(answer))
        if val is None or aval is None:
            return "skip", "极限值或答案不可数值化"
        return ("ok", f"极限={val}") if close(val, aval) else ("mismatch", f"极限 {mobj.doit()}={val} vs 答案 {aval}")

    if kind == "integral_def":
        mobj = parse_main_obj(problem)
        if not isinstance(mobj, sympy.Integral) or len(mobj.limits) != 1 or len(mobj.limits[0]) != 3:
            return "skip", "定积分结构不可解析"
        val = num_of(mobj)
        aval = num_of(parse_first(answer))
        if val is None or aval is None:
            return "skip", "积分值或答案不可数值化"
        return ("ok", f"积分={val}") if close(val, aval) else ("mismatch", f"定积分={val} vs 答案 {aval}")

    if kind == "integral_indef":
        mobj = parse_main_obj(problem)
        aobj = parse_first(answer, want_x=True)
        if mobj is None or aobj is None:
            return "skip", "被积函数或答案原函数不可解析"
        if isinstance(mobj, sympy.Integral):
            mobj = mobj.function
        # 验证 diff(F) == f：抽样对拍免疫积分常数 C
        r = sample_match(sympy.diff(aobj, X), mobj)
        return (("ok", "原函数求导还原一致") if r else ("mismatch", f"原函数 {aobj} 求导 ≠ {mobj}") if r is False else ("skip", "原函数抽样全遇奇点"))

    if kind == "solve_eq":
        eq = parse_main_obj(problem)
        if not isinstance(eq, sympy.Eq):
            return "skip", "方程结构不可解析"
        # 根只认「x = 表达式」形态的 math 块：孤立数字块（验算过程中的 8、12）会误伤，
        # 文本正则也会把 x = -1 + 2√3 截断成 -1，均不可靠
        roots = []
        for seg in extract_maths(answer):
            obj = try_parse(seg)
            if isinstance(obj, sympy.Eq) and obj.lhs == X:
                roots.append(obj.rhs)
        if not roots:
            return "skip", "答案根不可解析"
        # 只验「给的确实是根」，不验完整性（第一版）
        for r in roots[:4]:
            try:
                if abs(complex((eq.lhs - eq.rhs).evalf(subs={X: r}))) > TOL_ABS:
                    return "mismatch", f"答案根 x={r} 代入方程 ≠0"
            except Exception:
                return "skip", "根代入遇奇点"
        return "ok", f"答案根代入成立（验 {len(roots[:4])} 个）"

    if kind == "evaluate":
        fobj = parse_main_obj(problem)
        aobj = parse_first(answer)
        if fobj is None or aobj is None:
            return "skip", "表达式不可解析"
        # 「在 x = a 处」模式：直接对拍 f(a) vs 答案数值
        m = AT_POINT_RE.search(problem)
        if m:
            try:
                a = sympy.Rational(m.group(1))
            except Exception:
                return "skip", "代入点不可解析"
            va, vb = eval_at(fobj, a), num_of(aobj)
            if va is None or vb is None:
                return "skip", "代入点遇奇点"
            return ("ok", f"f({a})={va}") if close(va, vb) else ("mismatch", f"f({a})={va} vs 答案 {vb}")
        # 通式模式：答案含 x → 抽样对拍；答案为常数但题目含 x → 不可判
        if is_plain_expr(aobj) and X in aobj.free_symbols:
            r = sample_match(fobj, aobj)
            return (("ok", "表达式对拍一致") if r else ("mismatch", f"表达式 {fobj} vs {aobj} 不一致") if r is False else ("skip", "抽样全遇奇点"))
        return "skip", "答案非通式且题目无代入点"

    return "skip", "未命中验证分支"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="学术数据目录（data/sft19 等，含 ap_calc/ap_stats/precalc jsonl）")
    ap.add_argument("--outdir", default="/tmp/verify_out")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    files = [f for f in sorted(glob.glob(os.path.join(args.dir, "*.jsonl")))
             if os.path.basename(f).replace(".jsonl", "") in MATH_CATS]
    if not files:
        print("没有可验证的数学 jsonl（ap_calc/ap_stats/precalc）")
        return

    stats = {k: {"ok": 0, "mismatch": 0, "skip": 0} for k in MATH_CATS}
    skip_notes = {}
    viol = open(os.path.join(args.outdir, "violations.jsonl"), "w", encoding="utf-8")
    report = [f"dir={args.dir}", f"时间={__import__('datetime').datetime.now():%F %T}"]
    total = 0
    for fn in files:
        cat = os.path.basename(fn).replace(".jsonl", "")
        with open(fn, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                total += 1
                verdict, note = verify(rec)
                stats[cat][verdict] += 1
                if verdict == "skip":
                    skip_notes[note] = skip_notes.get(note, 0) + 1
                if verdict == "mismatch":
                    viol.write(json.dumps({**rec, "verify_note": note}, ensure_ascii=False) + "\n")
    viol.close()

    report.append(f"总样本 {total}")
    for cat in MATH_CATS:
        s = stats[cat]
        n = sum(s.values())
        if n:
            report.append(f"  {cat}: {n} 条 | ok {s['ok']} | mismatch {s['mismatch']} | skip {s['skip']}")
    if skip_notes:
        report.append("skip 原因分布: " + " | ".join(f"{k}×{v}" for k, v in sorted(skip_notes.items(), key=lambda kv: -kv[1])[:12]))
    text = "\n".join(report)
    with open(os.path.join(args.outdir, "verify_report.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)
    n_mis = sum(s["mismatch"] for s in stats.values())
    if n_mis:
        print(f"⚠ 违规 {n_mis} 条已写入 {args.outdir}/violations.jsonl，assemble 时 --exclude 过滤")
        sys.exit(1)


if __name__ == "__main__":
    main()
