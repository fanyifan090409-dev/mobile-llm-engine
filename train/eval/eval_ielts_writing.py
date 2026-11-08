#!/usr/bin/env python3
"""雅思写作 held-out 评测：生成 12 篇作文 + 客观启发式检查 + 人工/裁判评分表。

用法：
  python3 eval_ielts_writing.py --model <gguf> --port 8150 --outdir <dir>
"""
import argparse
import json
import os
import re
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_FILE = os.path.join(ROOT, "train/eval/ielts_writing_eval.json")

BANNED = ["delve", "pivotal", "paramount", "multifaceted", "tapestry",
          "double-edged sword", "in today's fast-paced world", "it is worth noting",
          "a testament to", "navigate the complexities", "furthermore, furthermore"]
OPINION_WORDS = ["i believe", "in my view", "in my opinion", "i agree", "i disagree",
                 "i would argue", "personally"]
DATA_WORDS = ["increase", "increased", "decrease", "decreased", "rise", "rose",
              "fall", "fell", "percent", "%", "figure", "respectively", "compared"]


def chat(port, user, max_tokens=800):
    body = json.dumps({
        "messages": [{"role": "user", "content": user}],
        "temperature": 0, "max_tokens": max_tokens, "stream": False,
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())["choices"][0]["message"].get("content") or ""


def prompt_for(t):
    task_name = "Task 1" if t["task"] == 1 else "Task 2"
    extra = ("\n" + t["data"]) if t.get("data") else ""
    return (f"雅思写作 {task_name}（{t['type']}）。题目：{t['prompt']}{extra}\n"
            f"请用英文写一篇 {t['min_words']} 词以上的回答。要求：以亚洲考生真人风格写作，"
            f"目标 band 7.0-7.5，不背模板、不堆砌生僻词、不出现 AI 腔；结构自然，论证具体。")


def stats(essay, task):
    words = re.findall(r"[A-Za-z']+", essay)
    lower = [w.lower() for w in words]
    paragraphs = [p for p in re.split(r"\n\s*\n", essay.strip()) if p.strip()]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", essay.strip()) if s.strip()]
    unique = len(set(lower))
    ttr = unique / max(1, len(lower))
    banned_hits = [b for b in BANNED if b in essay.lower()]
    opinion_hits = sum(1 for w in OPINION_WORDS if w in essay.lower())
    data_hits = sum(1 for w in DATA_WORDS if w in essay.lower())
    # 高频实词重复（去停用词）
    stop = set("the a an and or but of to in on for with is are was were be been this that these those it its as at by from".split())
    freq = {}
    for w in lower:
        if len(w) > 3 and w not in stop:
            freq[w] = freq.get(w, 0) + 1
    top = sorted(freq.items(), key=lambda kv: -kv[1])[:5]
    return {
        "words": len(words), "paragraphs": len(paragraphs), "sentences": len(sentences),
        "avg_sentence_len": round(len(words) / max(1, len(sentences)), 1),
        "ttr": round(ttr, 3), "banned_hits": banned_hits,
        "opinion_markers": opinion_hits, "data_markers": data_hits,
        "top_repeated": top,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, default=8150)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    tasks = json.load(open(EVAL_FILE, encoding="utf-8"))["tasks"]
    results = []
    for i, t in enumerate(tasks, 1):
        t0 = time.time()
        try:
            essay = chat(args.port, prompt_for(t))
        except Exception as e:
            essay = f"__ERROR__ {type(e).__name__}: {e}"
        s = stats(essay, t["task"])
        results.append({"id": t["id"], "task": t["task"], "type": t["type"],
                        "prompt": t["prompt"], "min_words": t["min_words"],
                        "essay": essay, "stats": s})
        print(f"[{i}/{len(tasks)}] {t['id']} words={s['words']} paras={s['paragraphs']} {time.time()-t0:.1f}s", flush=True)
    with open(os.path.join(args.outdir, "outputs.json"), "w", encoding="utf-8") as f:
        json.dump({"model": os.path.basename(args.model), "results": results}, f, ensure_ascii=False, indent=2)

    # 评分表：四项 blank，人工/裁判填
    lines = [f"# 雅思写作评分表（{os.path.basename(args.model)}）", "",
             "| 题目 | 类型 | 字数 | 段落 | 句均长 | TTR | 禁用词 | 观点/数据标记 | TR | CC | LR | GRA | 总分 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["stats"]
        lines.append(f"| {r['id']} | {r['type']} | {s['words']}/{r['min_words']} | {s['paragraphs']} | "
                     f"{s['avg_sentence_len']} | {s['ttr']} | {','.join(s['banned_hits']) or '-'} | "
                     f"{s['opinion_markers']}/{s['data_markers']} |  |  |  |  |  |")
    lines += ["", "评分口径：TR 任务回应 / CC 连贯衔接 / LR 词汇资源 / GRA 语法多样与准确；",
              "每项 1-9 分，0.5 分档；总分 = 四项平均，按 IELTS 取整规则。",
              "建议双评：两名评分者独立打分，分差 >1 分时由第三人仲裁。"]
    with open(os.path.join(args.outdir, "score_sheet.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("DONE")


if __name__ == "__main__":
    main()
