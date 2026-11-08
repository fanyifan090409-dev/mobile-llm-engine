#!/usr/bin/env python3
"""Task 1 事实管线评测：给 SFT19 喂确定性 FACTS，看数字/趋势是否还错。

用法：
  python3 eval_ielts_facts.py --model <gguf> --port 8153 --outdir <dir>
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_ielts_writing import chat, stats
from t1_facts import facts_for

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_FILE = os.path.join(ROOT, "train/eval/ielts_writing_eval.json")
STRUCT_FILE = os.path.join(ROOT, "train/eval/ielts_t1_structured.json")


def prompt_with_facts(t, fact_lines):
    facts = "\n".join(f"- {f}" for f in fact_lines)
    return (f"雅思写作 Task 1（{t['type']}）。题目：{t['prompt']}\n"
            f"FACTS（只能使用以下事实；不得添加任何未给出的数字或关系）：\n{facts}\n"
            f"请用英文写一篇 {t['min_words']} 词以上的回答。要求：以亚洲考生真人风格写作，"
            f"目标 band 7.0-7.5，不背模板、不堆砌生僻词、不出现 AI 腔；结构自然，论证具体。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, default=8153)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    tasks = json.load(open(EVAL_FILE, encoding="utf-8"))["tasks"]
    structured = json.load(open(STRUCT_FILE, encoding="utf-8"))["tasks"]
    results = []
    t1 = [t for t in tasks if t["task"] == 1]
    for i, t in enumerate(t1, 1):
        t0 = time.time()
        fact_lines = facts_for(t["id"], structured[t["id"]])
        try:
            essay = chat(args.port, prompt_with_facts(t, fact_lines), max_tokens=900)
        except Exception as e:
            essay = f"__ERROR__ {type(e).__name__}: {e}"
        s = stats(essay, t["task"])
        results.append({"id": t["id"], "task": 1, "type": t["type"],
                        "prompt": t["prompt"], "min_words": t["min_words"],
                        "facts": fact_lines, "essay": essay, "stats": s})
        print(f"[{i}/{len(t1)}] {t['id']} words={s['words']} paras={s['paragraphs']} {time.time()-t0:.1f}s", flush=True)
    with open(os.path.join(args.outdir, "outputs.json"), "w", encoding="utf-8") as f:
        json.dump({"model": os.path.basename(args.model), "results": results}, f, ensure_ascii=False, indent=2)
    lines = [f"# Task 1 事实管线评测（{os.path.basename(args.model)}）", "",
             "| 题目 | 类型 | 字数 | 段落 | TTR | 禁用词 | 观点/数据标记 |",
             "|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["stats"]
        lines.append(f"| {r['id']} | {r['type']} | {s['words']}/{r['min_words']} | {s['paragraphs']} | "
                     f"{s['ttr']} | {','.join(s['banned_hits']) or '-'} | {s['opinion_markers']}/{s['data_markers']} |")
    with open(os.path.join(args.outdir, "score_sheet.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("DONE")


if __name__ == "__main__":
    main()
