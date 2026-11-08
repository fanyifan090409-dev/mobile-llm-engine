#!/usr/bin/env python3
"""SFT27 CAS 数据拼装：math_eval 2,138 + 工具派单 1,000 + 反问 300 + chat 200 + 学术 700。

在训练机跑（读 data/ 下的既有数据 + 上传的 math_eval_sft）：
  python3 assemble_sft27_cas.py --outdir data/train_sft27_cas

分层原则：
- math_eval 用生成器自己的 train/val（按题分组，避免同一题的两条轨迹跨 split）；
- 回放数据按池随机打乱后 10% 做 val；
- 派单只留「时间明确、任务清楚」的行，模糊指令交给反问数据。
"""
import argparse
import json
import os
import random
import re

ROOT = "/home/ubuntu/llm-mobile"
rng = random.Random(20261108)
TIME_RE = re.compile(r"今天|明天|后天|大后天|周[一二三四五六日天]|星期[一二三四五六日天]|"
                     r"下个?月|\d{1,2}\s*月\s*\d{1,2}\s*[日号]|\d{1,2}\s*[点时]|"
                     r"上午|下午|晚上|中午|早上|傍晚|月底|月初")
AMBIG_RE = re.compile(r"具体时间我发你|时间还没定|回头再说|看房|夜跑|那个会|刚才那个|"
                      r"帮我约个事|帮我安排一下$|提醒我一下")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def split(pool, val_ratio=0.1):
    rng.shuffle(pool)
    n = max(1, int(len(pool) * val_ratio))
    return pool[n:], pool[:n]


def dispatch_ok(r):
    u = r["messages"][1]["content"]
    t = r.get("task_type")
    if AMBIG_RE.search(u):
        return False
    if t in ("calendar", "reminder", "mixed"):
        return bool(TIME_RE.search(u))
    if t == "translate":
        return "翻译" in u
    if t == "summary":
        return any(k in u for k in ("总结", "摘要", "缩成", "概括", "压缩"))
    return False


def academic_rows(cat, n):
    rows = read_jsonl(os.path.join(ROOT, f"data/sft19/{cat}.jsonl"))
    if cat == "ielts":
        rows = [r for r in rows if r.get("form") == "ielts_writing"]
    else:
        rows = [r for r in rows if "【答案】" in r["messages"][-1]["content"]]
    rng.shuffle(rows)
    return rows[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data/train_sft27_cas")
    args = ap.parse_args()
    outdir = os.path.join(ROOT, args.outdir)
    os.makedirs(outdir, exist_ok=True)

    math_train = read_jsonl(os.path.join(ROOT, "data/math_eval_sft/train.jsonl"))
    math_val = read_jsonl(os.path.join(ROOT, "data/math_eval_sft/val.jsonl"))

    # 派单回放：单轮 800 + 多轮 200；多轮保留完整 tool 轨迹
    leader = read_jsonl(os.path.join(ROOT, "data/train_sft20_leader/train.jsonl"))
    pool = [r for r in leader if dispatch_ok(r)]
    single = [{"messages": r["messages"]} for r in pool
              if len(r["messages"]) == 3 and "<tool_call>" in r["messages"][2]["content"]]
    multi = [{"messages": r["messages"]} for r in pool
             if len(r["messages"]) >= 4 and any(m["role"] == "tool" for m in r["messages"])]
    rng.shuffle(single)
    rng.shuffle(multi)
    dispatch = single[:800] + multi[:200]

    # 反问 300、闲聊 200
    t21 = read_jsonl(os.path.join(ROOT, "data/train_sft21b_leader/train.jsonl"))
    clarify = [r for r in t21 if r.get("task_type") == "clarify"]
    chat = [r for r in t21 if r.get("task_type") == "chat"]
    rng.shuffle(clarify)
    rng.shuffle(chat)
    clarify = clarify[:300]
    chat = chat[:200]

    academic = (academic_rows("ap_calc", 250) + academic_rows("precalc", 250)
                + academic_rows("ap_stats", 100) + academic_rows("ielts", 100))

    # 去重（同一池里可能有重复行），按 messages 内容哈希
    seen = set()
    def dedup(rows):
        out = []
        for r in rows:
            key = json.dumps(r["messages"], ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    math_train = dedup(math_train)
    math_val = dedup(math_val)
    replay = dedup(dispatch + clarify + chat + academic)
    replay_train, replay_val = split(replay)

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
    stats = {
        "math_train": len(math_train), "math_val": len(math_val),
        "dispatch": len(dispatch), "clarify": len(clarify), "chat": len(chat),
        "academic": len(academic),
        "train": len(train), "val": len(val), "total": len(train) + len(val),
    }
    with open(os.path.join(outdir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
