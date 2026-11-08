#!/usr/bin/env python3
"""SFT19 变式解答链：variants.jsonl（变式题面+SymPy 真答案）→ 30B 数学 teacher
补写【思路】【解答】【答案】→ 答案与生成时算好的真值硬对拍 → 合格样本入池。

对拍比 verify_math.py 更硬：真值在变式生成时就确定（同一 SymPy 计算），
teacher 答案必须匹配真值才入池；不合格重试 1 次，仍不合格丢弃（记日志）。

运行时机：训练机合成链（占用 :8003）完成之后、assemble 之前。
用法：python3 solve_variants.py --variants data/sft19_variants/variants.jsonl \
        --outdir data/sft19 --limit 0
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

import sympy
from sympy import Symbol, latex, diff, integrate, Integral, simplify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_math import try_parse, extract_maths, close  # noqa: E402

X = Symbol("x")
# 答案块数字提取（数值对拍用）
NUM_RE = r"-?\d+(?:\.\d+)?"
# 30B 数学 teacher（与 synthesize_academic.py 同款接口）
ENDPOINT = "http://127.0.0.1:8003/v1/chat/completions"
MODEL = "qwen3-coder"
MAX_TOKENS = 1536
SUBJECTS = {"ap_calc": "AP 微积分", "precalc": "美高数学（Precalculus）",
            "ap_stats": "AP 统计"}

SOLVE_TPL = ("请解答下面这道{subject}题。严格按以下格式输出：\n"
             "【思路】先用 2-4 句说明解题规划（用什么方法、为什么适用）；\n"
             "【解答】分步编号写出详细步骤，每步说明理由（为什么这么做），不跳步；\n"
             "【答案】单独一行给出最终结果，并验算确认。\n"
             "题目：\n{problem}")


def chat(messages, max_tokens=MAX_TOKENS):
    """单次补全带重试；失败返回 None。"""
    import requests  # 惰性导入：judge 对拍是纯函数，不该拖网络依赖
    payload = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
               "temperature": 0.7, "top_p": 0.95, "stream": False,
               "chat_template_kwargs": {"enable_thinking": False}}
    for i in range(3):
        try:
            r = requests.post(ENDPOINT, json=payload, timeout=600)
            r.raise_for_status()
            return (r.json()["choices"][0]["message"].get("content") or "").strip()
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def answer_block(text):
    """提取【答案】块内容（【答案】到结尾或下一【块】）。"""
    m = re.search(r"【答案】\s*(.*?)(?=【|$)", text, re.S)
    return (m.group(1).strip() if m else "") or ""


def parse_problem_expr(problem):
    """从变式题面取回被求对象（f 的表达式或 Integral 的被积函数）。"""
    maths = extract_maths(problem)
    if not maths:
        return None
    obj = try_parse(maths[0])
    if obj is None:
        return None
    if isinstance(obj, sympy.Equality):
        obj = obj.rhs
    if isinstance(obj, Integral):
        obj = obj.function
    return obj


def judge(variant, teacher_text):
    """teacher 输出 vs 变式真值：返回 (ok, note)。"""
    ans_blk = answer_block(teacher_text)
    if len(ans_blk) < 2:
        return False, "无【答案】块"
    kind = variant["kind"]
    if kind in ("evaluate", "integral_def"):
        # 数值对拍：答案块最后一个数字（答案一般在句尾）
        nums = re.findall(NUM_RE, ans_blk)
        if not nums:
            return False, "答案块无数字"
        got = float(nums[-1])
        want = float(variant["true_answer_num"])
        if close(got, want):
            return True, f"{got} ≈ {want}"
        return False, f"数值不符: 给 {got} vs 真值 {want}"
    # 表达式对拍：答案块第一个 math 块
    maths = extract_maths(ans_blk)
    if not maths:
        return False, "答案块无表达式"
    g = try_parse(maths[0])
    if g is None:
        return False, "答案表达式不可解析"
    f = parse_problem_expr(variant["problem"])
    if f is None:
        return False, "题面不可解析"
    if kind == "derivative":
        ok = simplify(diff(f, X) - g) == 0
    else:  # integral_indef：对答案求导应回到被积函数
        ok = simplify(diff(g, X) - f) == 0
    return (True, "表达式一致") if ok else (False, f"表达式不符: {g}")


def to_sample(variant, teacher_text):
    """合格样本组装（与合成链同 schema）。"""
    user = SOLVE_TPL.format(subject=SUBJECTS[variant["category"]],
                            problem=variant["problem"])
    messages = [{"role": "user", "content": user},
                {"role": "assistant", "content": teacher_text}]
    h = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16]
    return {"messages": messages, "category": variant["category"],
            "form": "solve", "hash": h, "variant": True,
            "source_hash": variant["source_hash"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", required=True)
    ap.add_argument("--outdir", required=True, help="样本输出目录（data/sft19 等）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条（0=全部）")
    args = ap.parse_args()

    variants = [json.loads(l) for l in open(args.variants, encoding="utf-8")]
    if args.limit:
        variants = variants[:args.limit]
    os.makedirs(args.outdir, exist_ok=True)

    ok_n = retry_n = drop = 0
    drop_log = []
    # 按类别分文件追加（与合成链文件同构，assemble 直接收）
    for i, var in enumerate(variants):
        user = SOLVE_TPL.format(subject=SUBJECTS[var["category"]],
                                problem=var["problem"])
        teacher = chat([{"role": "user", "content": user}])
        if teacher is None:
            drop += 1
            drop_log.append((var["vseed"], "teacher 调用失败"))
            continue
        ok, note = judge(var, teacher)
        if not ok:
            teacher2 = chat([{"role": "user", "content": user},
                             {"role": "assistant", "content": teacher},
                             {"role": "user", "content": "你的【答案】与正确结果不符，"
                              "请重新检查解答步骤并更正。"}])
            if teacher2:
                ok, note = judge(var, teacher2)
                if ok:
                    teacher = teacher2
            if not ok:
                drop += 1
                retry_n += 1
                drop_log.append((var["vseed"], note))
                continue
        sample = to_sample(var, teacher)
        with open(os.path.join(args.outdir, f"{var['category']}.jsonl"),
                  "a", encoding="utf-8") as f:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        ok_n += 1
        if (i + 1) % 10 == 0:
            print(f"进度 {i + 1}/{len(variants)} | 入池 {ok_n} | 丢弃 {drop}", flush=True)

    print(f"完成: 入池 {ok_n} | 丢弃 {drop}（含重试后仍不合格 {retry_n}）")
    if drop_log:
        with open(os.path.join(args.outdir, "variant_drop.log"), "w", encoding="utf-8") as f:
            for seed, note in drop_log:
                f.write(f"{seed}\t{note}\n")
        print(f"丢弃明细 → {args.outdir}/variant_drop.log（{len(drop_log)} 条）")


if __name__ == "__main__":
    main()
