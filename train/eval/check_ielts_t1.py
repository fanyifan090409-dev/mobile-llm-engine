#!/usr/bin/env python3
"""雅思 Task 1 客观一致性检查：数字越界 + 趋势方向矛盾。

用法：
  python3 check_ielts_t1.py --tasks train/eval/ielts_writing_eval.json \
      --outputs train/nightly/work/ielts_writing/<tag>/outputs.json
"""
import argparse
import itertools
import json
import re

NUM_RE = re.compile(r"\d+(?:\.\d+)?")
DIR_RE = re.compile(
    r"(rose|increased|grew|climbed|fell|declined|dropped|decreased)\s+from\s+"
    r"(\d+(?:\.\d+)?)\s*%?\s+to\s+(\d+(?:\.\d+)?)\s*%?",
    re.I,
)
UP = {"rose", "increased", "grew", "climbed"}


def data_numbers(task):
    text = task["prompt"] + " " + task.get("data", "")
    vals = [float(x) for x in NUM_RE.findall(text)]
    allowed = set(vals)
    for a, b in itertools.combinations(vals, 2):
        allowed.add(abs(a - b))
        allowed.add(a + b)
    return allowed, vals


def check(task, essay):
    allowed, vals = data_numbers(task)
    used = [float(x) for x in NUM_RE.findall(essay)]
    unknown = sorted({x for x in used if x not in allowed})
    contradictions = []
    for m in DIR_RE.finditer(essay):
        verb, a, b = m.group(1).lower(), float(m.group(2)), float(m.group(3))
        if (verb in UP and b < a) or (verb not in UP and b > a):
            contradictions.append(m.group(0))
    return unknown, contradictions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="train/eval/ielts_writing_eval.json")
    ap.add_argument("--outputs", required=True)
    args = ap.parse_args()
    tasks = json.load(open(args.tasks, encoding="utf-8"))
    tasks = tasks if isinstance(tasks, list) else tasks.get("tasks", tasks)
    out = json.load(open(args.outputs, encoding="utf-8"))
    essays = {r["id"]: r["essay"] for r in out["results"]}
    print("| 题目 | 越界数字 | 趋势矛盾 |")
    print("|---|---|---|")
    bad = 0
    for t in tasks:
        if t["task"] != 1:
            continue
        unknown, contra = check(t, essays[t["id"]])
        if unknown or contra:
            bad += 1
        print(f"| {t['id']} | {', '.join(map(str, unknown)) or '-'} | {'; '.join(contra) or '-'} |")
    print(f"\n有问题题目：{bad}/6")


if __name__ == "__main__":
    main()
