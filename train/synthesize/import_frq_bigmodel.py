#!/usr/bin/env python3
"""导入大模型生成的 FRQ 样本：校验 JSON/结构/锚点/数值后拼成 SFT 数据。

用法：
  python3 import_frq_bigmodel.py \
    --frq-data train/eval/private/ap_calc_bc_frq_2022_2024.json \
    --indir frq_out --outdir data/train_sft25_frq

支持两类文件：
  - 正题 {year,num,main,parts,rubric,cas_hints}：1 条整题 + 每小问 1 条；
  - 变体 variants-YYYY-qN.json（列表，每项 {variant,user,assistant,cas_hints}）：
    没有官方答案，靠 cas_hints 的数值执行 + 答案区数字回查做自动防线。
"""
import argparse
import ast
import json
import math
import os
import re

OPS = {"eval", "derivative", "simplify", "integrate_def", "integrate_indef", "solve", "stats"}
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
VARIANT_RE = re.compile(r"^variants-(\d{4})-q(\d+)\.json$")
# 变量赋值点：t=1 / h=12；r(0)=2.5 这种函数记号不会命中
ASSIGN_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z])\s*=\s*(-?\d+(?:\.\d+)?)")
MATH_FUNCS = {n: getattr(math, n) for n in
              ("sin", "cos", "tan", "asin", "acos", "atan", "exp", "log", "log10", "sqrt", "fabs")}


def eval_expr(expr, env=None):
    """受限求值：只允许数字、pi/e、白名单数学函数和四则运算。

    json 来自外部大模型，不能直接 eval；用 ast 白名单走一遍。
    """
    tree = ast.parse(expr.replace("^", "**").replace("π", "pi"), mode="eval")
    env = env or {}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id in env:
                return env[n.id]
            if n.id == "pi":
                return math.pi
            if n.id == "e":
                return math.e
            if n.id in MATH_FUNCS:
                return MATH_FUNCS[n.id]
            raise ValueError(f"未知符号 {n.id}")
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -ev(n.operand)
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            for op, fn in ((ast.Add, lambda x, y: x + y), (ast.Sub, lambda x, y: x - y),
                           (ast.Mult, lambda x, y: x * y), (ast.Div, lambda x, y: x / y),
                           (ast.Pow, lambda x, y: x ** y)):
                if isinstance(n.op, op):
                    return fn(a, b)
            raise ValueError("不支持的运算符")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in MATH_FUNCS:
            return MATH_FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError(f"不支持的表达式节点 {type(n).__name__}")

    return ev(tree)


def simpson(expr, var, lo, hi, n=20000):
    # 上下限允许写 pi / pi/2，大模型经常这么写
    lo = eval_expr(lo) if isinstance(lo, str) else float(lo)
    hi = eval_expr(hi) if isinstance(hi, str) else float(hi)
    f = lambda x: eval_expr(expr, {var: x})
    h = (hi - lo) / n
    s = f(lo) + f(hi)
    for i in range(1, n):
        s += (4 if i % 2 else 2) * f(lo + i * h)
    return s * h / 3


def num_in_text(value, text):
    """答案区是否写了这个数（按绝对值比对，只容忍 3 位小数级四舍五入）。

    相对容差必须压到 2e-5：4872.664 的 0.5% 容差能放过 4872.999，
    等于体积算错 0.3 也查不出来。
    """
    target = abs(value)
    for m in NUM_RE.finditer(text.replace("−", "-")):
        if abs(abs(float(m.group())) - target) <= max(1e-3, target * 2e-5):
            return True
    return False


def slope_direction(text):
    m = re.findall(r"[（(](increasing|decreasing)[）)]", text)
    if m:
        return m[-1]
    m = re.search(r"随\s*h\s*增大而(增大|减小)", text)
    if m:
        return "increasing" if m.group(1) == "增大" else "decreasing"
    return None


def candidate_points(var, text):
    return sorted({float(m.group(2)) for m in ASSIGN_RE.finditer(text) if m.group(1) == var})


def answer_segments(answer):
    """把【答案】按 (A)/（a）/A./A: 等标记切开，数字只在本小题段里查。

    正题答案常出现 (A)、（a）、A.、A: 四种写法，缺一种就退化成全文匹配。
    """
    marks = [(m.start(), (m.group(1) or m.group(2)).upper()) for m in re.finditer(
        r"[（(]([A-Fa-f])[)）]|(?:^|\n)\s*([A-Fa-f])[.．、:：]", answer)]
    segs = {}
    for i, (pos, letter) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(answer)
        segs.setdefault(letter, answer[pos:end])
    return segs


def check_numeric(hints, user, assistant, part_users=None, strict=True):
    """把 cas_hints 当程序执行，独立复核答案区数字和增减方向。

    返回 (errs, warnings)。导数复核的取值点优先从对应小题题面里找；
    多点候选时只要有一个点同时对上方向和数值就放行，并留 warning，
    这样参数方程题的 t=0 背景值不会误伤 t=1 的求值点。

    strict=False（正题）：hint 只是辅助步骤，很多是中间量（积分结果再除以
    区间长度、求导验证单调性），答案区本来就不会写，所以全部降为 warning，
    正确性由官方锚点兜底。strict=True（变体）：没有官方答案，hint 必须对上。
    """
    errs, warnings = [], []
    answer = assistant.split("【答案】")[-1]
    segments = answer_segments(answer)
    part_users = part_users or {}
    for h in hints:
        op = h.get("op")
        seg = segments.get(h.get("part"), answer)
        try:
            if op == "eval":
                val = eval_expr(h["expr"])
                if not num_in_text(val, seg):
                    errs.append(f"{h.get('part')} eval={val:.6g} 未出现在本小题答案段")
            elif op == "integrate_def":
                val = simpson(h["expr"], h.get("variable", "h"), float(h["lower"]), float(h["upper"]))
                if not num_in_text(val, seg):
                    errs.append(f"{h.get('part')} 积分={val:.6g} 未出现在本小题答案段")
            elif op == "derivative":
                var = h.get("variable", "h")
                pts = candidate_points(var, part_users.get(h.get("part"), user))
                if not pts:
                    warnings.append(f"{h.get('part')} 导数复核跳过：题面没有 {var}=数值")
                    continue
                direction = slope_direction(seg)
                matched, details = None, []
                for x0 in pts:
                    eps = 1e-6
                    d = (eval_expr(h["expr"], {var: x0 + eps})
                         - eval_expr(h["expr"], {var: x0 - eps})) / (2 * eps)
                    tag = "increasing" if d > 1e-9 else "decreasing" if d < -1e-9 else "flat"
                    details.append(f"{var}={x0:g}: f'={d:.4f}({tag})")
                    if (direction is None or direction == tag) and num_in_text(d, seg):
                        matched = x0
                        break
                if matched is None:
                    errs.append(f"{h.get('part')} 导数与答案对不上: " + "；".join(details))
                elif len(pts) > 1:
                    warnings.append(f"{h.get('part')} 多候选点，按 {var}={matched:g} 对上: " + "；".join(details))
        except Exception as e:
            errs.append(f"{h.get('part')} {op} 执行失败: {e}")
    if not strict:
        warnings += errs
        errs = []
    return errs, warnings


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def load_json(path):
    """容忍大模型输出常见的 ```json 围栏，其余情况按纯 JSON 解析。"""
    text = open(path, encoding="utf-8").read().strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    return json.loads(text)


def norm(s):
    return re.sub(r"\s+", "", s.replace("−", "-").replace("′", "'"))


def official_answers(q):
    out = {}
    for p in q.get("parts", []):
        nums = NUM_RE.findall(str(p.get("answer", "")))
        out[p["id"]] = nums
    return out


def check_sample(gen, q):
    errs = []
    main = gen.get("main", {})
    if not main.get("user") or not main.get("assistant"):
        errs.append("main 缺 user/assistant")
    parts = gen.get("parts", [])
    if not parts:
        errs.append("parts 为空")
    ids = {p.get("id") for p in parts}
    for p in q.get("parts", []):
        if p["id"] not in ids:
            errs.append(f"缺小题 {p['id']}")
    for p in parts:
        a = p.get("assistant", "")
        if not all(f"【{b}】" in a for b in ("思路", "解答", "答案")):
            errs.append(f"{p.get('id')} 缺标记块")
        if "$" in a:
            errs.append(f"{p.get('id')} 含 LaTeX $")
    if "$" in main.get("assistant", ""):
        errs.append("main 含 LaTeX $")

    # 锚点：每个小题官方答案里的数字，至少命中一个（官方答案可能是解释题，无数字则跳过）
    flat = norm(main.get("assistant", ""))
    for p in q.get("parts", []):
        nums = NUM_RE.findall(str(p.get("answer", "")))
        if not nums:
            continue
        if not any(norm(n) in flat for n in nums):
            errs.append(f"锚点缺失 {p['id']}: {nums[:3]}")

    hints = gen.get("cas_hints", [])
    for h in hints:
        if h.get("op") not in OPS:
            errs.append(f"cas op 非法: {h.get('op')}")
        if not h.get("expr"):
            errs.append("cas_hints 缺 expr")
    warnings = []
    if hints:
        e, w = check_numeric(hints, main.get("user", ""), main.get("assistant", ""),
                             {p["id"]: p.get("user", "") for p in gen.get("parts", [])},
                             strict=False)
        errs += e
        warnings += w
    return errs, warnings


def check_variant(v):
    errs = []
    user, ans = v.get("user", ""), v.get("assistant", "")
    if not user or not ans:
        return ["缺 user/assistant"], []
    if "$" in ans:
        errs.append("含 LaTeX $")
    if not all(f"【{b}】" in ans for b in ("思路", "解答", "答案")):
        errs.append("缺标记块")
    ids = set(re.findall(r"[(（]([A-D])[)）]", user))
    if ids != set("ABCD"):
        errs.append(f"小题不全: {sorted(ids)}")
    hints = v.get("cas_hints", [])
    if not hints:
        errs.append("cas_hints 为空")
    for h in hints:
        if h.get("op") not in OPS:
            errs.append(f"cas op 非法: {h.get('op')}")
        if not h.get("expr"):
            errs.append("cas_hints 缺 expr")
        if h.get("part") not in ids:
            errs.append(f"cas 指向不存在的小题 {h.get('part')}")
    warnings = []
    if hints:
        e, w = check_numeric(hints, user, ans)
        errs += e
        warnings += w
    return errs, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frq-data", nargs="+", required=True)
    ap.add_argument("--indir", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    qmap = {}
    for path in args.frq_data:
        d = json.load(open(path, encoding="utf-8"))
        for q in d["questions"]:
            qmap[(q["year"], q["num"])] = q

    rows, report = [], []
    for name in sorted(os.listdir(args.indir)):
        if not name.endswith(".json"):
            continue
        try:
            raw = load_json(os.path.join(args.indir, name))
        except Exception as e:
            report.append({"file": name, "error": f"JSON 失败: {e}"})
            continue

        if isinstance(raw, list):
            mv = VARIANT_RE.match(name)
            if not mv:
                report.append({"file": name, "error": "列表格式但文件名不是 variants-YYYY-qN.json"})
                continue
            key = (int(mv.group(1)), int(mv.group(2)))
            q = qmap.get(key)
            if not q:
                report.append({"file": name, "error": f"找不到原题 {key}"})
                continue
            ok, warns = 0, []
            for i, v in enumerate(raw, 1):
                errs, w = check_variant(v)
                warns += [f"variant {i}: {x}" for x in w]
                if errs:
                    report.append({"file": name, "error": f"variant {i}: " + "; ".join(errs[:6])})
                    continue
                rows.append({"messages": [{"role": "user", "content": v["user"]},
                                          {"role": "assistant", "content": v["assistant"]}],
                             "category": "ap_calc", "form": "solve_frq_variant",
                             "source": f"{key[0]}-Q{key[1]}-v{i}"})
                ok += 1
            report.append({"file": name, "ok": ok > 0, "samples": ok, "variants": len(raw),
                           "warnings": warns})
            continue

        gen = raw
        key = (gen.get("year"), gen.get("num"))
        q = qmap.get(key)
        if not q:
            report.append({"file": name, "error": f"找不到原题 {key}"})
            continue
        errs, warnings = check_sample(gen, q)
        if errs:
            report.append({"file": name, "error": "; ".join(errs[:6]),
                           **({"warnings": warnings} if warnings else {})})
            continue
        src = f"{key[0]}-Q{key[1]}"
        main = gen["main"]
        rows.append({"messages": [{"role": "user", "content": main["user"]},
                                  {"role": "assistant", "content": main["assistant"]}],
                     "category": "ap_calc", "form": "solve_frq", "source": src})
        for p in gen["parts"]:
            rows.append({"messages": [{"role": "user", "content": p["user"]},
                                      {"role": "assistant", "content": p["assistant"]}],
                         "category": "ap_calc", "form": "solve_frq_part",
                         "source": f"{src}-{p['id']}"})
        report.append({"file": name, "ok": True, "samples": 1 + len(gen["parts"]),
                       **({"warnings": warnings} if warnings else {})})

    os.makedirs(args.outdir, exist_ok=True)
    # 按题分池：同题（含变体）只进 train 或只进 val，防止泄漏；题数不足 10 时不抽 val
    keys = sorted({"-".join(r["source"].split("-")[:2]) for r in rows})
    val_keys = set(keys[::10]) if len(keys) >= 10 else set()
    val = [r for r in rows if "-".join(r["source"].split("-")[:2]) in val_keys]
    train = [r for r in rows if r not in val]
    for name, data in (("train", train), ("val", val)):
        with open(os.path.join(args.outdir, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(args.outdir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    ok = sum(1 for r in report if r.get("ok"))
    print(f"OK {ok}/{len(report)} files, samples={len(rows)} (train {len(train)} / val {len(val)})")
    print(f"report -> {os.path.join(args.outdir, 'report.json')}")


if __name__ == "__main__":
    main()
