#!/usr/bin/env python3
"""SFT27g 定向修复集：从 v6 数学数据里只挑本次要修的题型 + 行为回放。

- 目标：平均值、复合函数、二阶导、limit（v5 已通过，保留）；
- 回放：派单 800 + 反问 200 + chat 150 + 学术 400，防止行为/学术漂移；
- 用法（训练机）：python3 scripts/assemble_repair27g.py --outdir data/train_sft27g_cas
"""
import argparse
import json
import os
import random

ROOT = "/home/ubuntu/llm-mobile"
rng = random.Random(20261109)


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def keep_math(r):
    p = r["messages"][1]["content"]
    return ("上的平均值" in p or "f(g(" in p or "g(f(" in p
            or "f''" in p or "极限" in p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data/train_sft27g_cas")
    args = ap.parse_args()
    outdir = os.path.join(ROOT, args.outdir)
    os.makedirs(outdir, exist_ok=True)

    math = []
    for name in ("train.jsonl", "val.jsonl", "multistep_train.jsonl", "multistep_val.jsonl"):
        math.extend(read_jsonl(os.path.join(ROOT, "data/math_eval_sft", name)))
    math = [r for r in math if keep_math(r)]
    rng.shuffle(math)
    n_val = max(1, len(math) // 10)
    math_val, math_train = math[:n_val], math[n_val:]

    leader = read_jsonl(os.path.join(ROOT, "data/train_sft20_leader/train.jsonl"))
    dispatch = [{"messages": r["messages"]} for r in leader
                if len(r["messages"]) == 3 and "<tool_call>" in r["messages"][2]["content"]]
    rng.shuffle(dispatch)
    t21 = read_jsonl(os.path.join(ROOT, "data/train_sft21b_leader/train.jsonl"))
    clarify = [r for r in t21 if r.get("task_type") == "clarify"]
    chat = [r for r in t21 if r.get("task_type") == "chat"]
    rng.shuffle(clarify)
    rng.shuffle(chat)
    academic = []
    for cat in ("ap_calc", "precalc", "ap_stats", "ielts"):
        rows = read_jsonl(os.path.join(ROOT, f"data/sft19/{cat}.jsonl"))
        if cat == "ielts":
            rows = [r for r in rows if r.get("form") == "ielts_writing"]
        else:
            rows = [r for r in rows if "【答案】" in r["messages"][-1]["content"]]
        rng.shuffle(rows)
        academic.extend(rows[:100])
    replay = dispatch[:800] + clarify[:200] + chat[:150] + academic
    rng.shuffle(replay)
    r_val = max(1, len(replay) // 10)
    replay_val, replay_train = replay[:r_val], replay[r_val:]

    train = math_train + replay_train
    val = math_val + replay_val
    rng.shuffle(train)
    rng.shuffle(val)

    def write(name, rows):
        with open(os.path.join(outdir, name), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    write("train.jsonl", train)
    write("val.jsonl", val)
    stats = {"math": len(math), "replay": len(replay),
             "train": len(train), "val": len(val)}
    with open(os.path.join(outdir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
