#!/usr/bin/env python3
"""质检合成 SFT 数据：类别分布 / 长度分布 / 重复率 / 工具调用解析率 + 抽样人工检查。

用法：python3 qc_sft.py --dir data/sft --samples 5
"""
import argparse
import glob
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter

# 占位符残留检查：teacher 举例未知日期时写 202X/XXXX，
# 模型会学会「日期没把握→输出 X 模板」（SFT17 幻觉率根因），出现即 QC 不通过
PLACEHOLDER_RE = re.compile(r"202X|XXXX")

# 学术类（SFT18）标记块契约，与 synthesize_academic.py 保持一致：
# 生成类样本 assistant 必须含对应【】标记块且各块非空；解题类解答非空且够长
ACADEMIC_CATS = {"ap_calc", "ap_stats", "precalc", "ielts"}
ACADEMIC_MARKERS = {
    "problem_gen": ["【题目】", "【答案】", "【解答】"],
    "ielts_writing": ["【点评】"],
    "ielts_reading": ["【文章】", "【题目】", "【答案】", "【解析】"],
    "ielts_listening": ["【听力文本】", "【题目】", "【答案】", "【解析】"],
}


def section_nonempty(text, marker):
    """标记块必须非空：标记后到下一个【】标记或结尾之间 ≥20 字。"""
    parts = text.split(marker)
    if len(parts) < 2:
        return False
    seg = parts[1]
    for other in ("【题目】", "【答案】", "【解答】", "【点评】", "【解析】", "【文章】", "【听力文本】"):
        if other == marker:
            continue
        if other in seg:
            seg = seg.split(other)[0]
    return len(seg.strip()) >= 20


def check_academic(rec):
    """返回违规列表。form 缺省或未知时跳过（非学术样本）。"""
    form = rec.get("form")
    if not form:
        return []
    msgs = rec.get("messages") or []
    problems = []
    if form in ACADEMIC_MARKERS:
        # 生成类：末条 assistant 必须含全部标记块且非空
        asst = [str(m.get("content") or "") for m in msgs if m.get("role") == "assistant"]
        out = asst[-1] if asst else ""
        for marker in ACADEMIC_MARKERS[form]:
            if marker not in out or not section_nonempty(out, marker):
                problems.append(f"{form} 缺标记块或为空: {marker}")
        # 公式残缺粗查：孤立 $ 或反斜杠结尾（LaTeX 截断特征）
        if out.count("$") % 2 != 0 or out.rstrip().endswith("\\"):
            problems.append(f"{form} 公式残缺（孤立$或\\结尾）")
    elif form == "solve":
        # 解题类两条轨迹：出题轨迹（user 要题 → assistant 只给【题目】块）查题目非空；
        # 解题轨迹（user 给题 → assistant 解答）按 SFT19 契约查【思路】【解答】【答案】三块且够长
        user = next((str(m.get("content") or "") for m in msgs if m.get("role") == "user"), "")
        asst = next((str(m.get("content") or "") for m in msgs if m.get("role") == "assistant"), "")
        if len(user) < 40:
            problems.append("solve user 题目过短")
        if asst.startswith("【题目】") and "【解答】" not in asst:
            if not section_nonempty(asst, "【题目】"):
                problems.append("solve 出题轨迹【题目】块过短")
        else:
            for marker in ("【思路】", "【解答】", "【答案】"):
                if marker not in asst:
                    problems.append(f"solve 缺标记块: {marker}")
            if len(asst) < 100:
                problems.append("solve 解答过短（<100字）")
    return problems

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/sft")
    ap.add_argument("--samples", type=int, default=5)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.jsonl")))
    if not files:
        print("没有找到 jsonl 文件")
        return
    total = 0
    hashes = set()
    cat_counts = Counter()
    len_counter = Counter()
    placeholder_counts = Counter()
    academic_problems = Counter()
    sched_ok = sched_total = 0
    all_recs = []
    for fn in files:
        cat = os.path.basename(fn).replace(".jsonl", "")
        with open(fn, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                total += 1
                cat_counts[cat] += 1
                h = rec.get("hash") or hashlib.sha256(line.encode()).hexdigest()
                hashes.add(h)
                msgs = rec.get("messages") or []
                text = "".join(str(m.get("content") or "") for m in msgs)
                len_counter[min(len(text) // 200, 15)] += 1
                if PLACEHOLDER_RE.search(text):
                    placeholder_counts[cat] += 1
                if cat in ACADEMIC_CATS:
                    for prob in check_academic(rec):
                        academic_problems[prob] += 1
                if cat == "schedule":
                    sched_total += 1
                    # 数据用 Qwen3 文本 XML 工具调用（content 内嵌 <tool_call>），非 OpenAI tool_calls 字段
                    if any(m.get("role") == "assistant" and m.get("content")
                           and "<tool_call>" in str(m.get("content")) for m in msgs):
                        sched_ok += 1
                all_recs.append(rec)

    print(f"总样本 {total} | 唯一 hash {len(hashes)} | 重复率 {(1 - len(hashes)/max(total,1)):.1%}")
    for c, n in cat_counts.most_common():
        print(f"  {c}: {n}")
    print("长度分布(每200字一档):", dict(sorted(len_counter.items())))
    if sched_total:
        print(f"schedule 工具调用解析率: {sched_ok}/{sched_total} = {sched_ok/sched_total:.1%}")
    if placeholder_counts:
        print(f"⚠ 占位符残留（202X/XXXX）: {sum(placeholder_counts.values())} 条 {dict(placeholder_counts)}"
              " → QC 不通过，禁止入训练池")
        sys.exit(1)
    print("占位符检查: 0 残留，通过")
    if academic_problems:
        print(f"⚠ 学术类结构校验失败: {sum(academic_problems.values())} 条 {dict(academic_problems)}"
              " → QC 不通过，禁止入训练池")
        sys.exit(1)
    print("学术类结构校验: 0 违规，通过")

    rng = random.Random(42)
    n_pick = min(args.samples * len(files), total)
    for rec in rng.sample(all_recs, n_pick):
        print("-" * 60)
        for m in rec["messages"]:
            c = m.get("content")
            if c:
                print(f"[{m['role']}] {str(c)[:180]}")
            elif m.get("tool_calls"):
                print(f"[{m['role']}] tool_call: {str(m['tool_calls'])[:180]}")

if __name__ == "__main__":
    main()
