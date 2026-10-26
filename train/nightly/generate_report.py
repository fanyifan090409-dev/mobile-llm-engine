#!/usr/bin/env python3
"""对比评测报告生成器：results.json → Markdown 报告（专业版 + 大众版）。

用法：
  python3 generate_report.py --results <results.json> --out <report.md> \
      --title "..." --headline-pair orig-F16,sft1-Q5_K_M
"""
import argparse
import json
from pathlib import Path

CHARS_PER_TOKEN = 1.6  # Qwen3 中文平均 ~1.6 字符/token（估算值，用于大众版速度换算）

QUANT_ORDER = ["F16", "Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "IQ4_XS"]
GROUP_LABEL = {"orig": "原版 Qwen3-0.6B（Instruct）", "sft1": "我们 SFT1", "sft2": "我们 最终版（PT2+SFT2）"}


def fmt_ppl(v):
    return f"{v[0]:.2f} ± {v[1]:.2f}"


def mb(n):
    return f"{n / 1024 / 1024:.0f} MB"


def pct(a, b):
    return f"{round((a - b) / b * 100):+d}%"


def model_rows(results):
    rows = sorted(results.items(), key=lambda kv: (
        list(GROUP_LABEL).index(kv[1]["group"]) if kv[1]["group"] in GROUP_LABEL else 9,
        QUANT_ORDER.index(kv[1]["quant"]) if kv[1]["quant"] in QUANT_ORDER else 9,
    ))
    return rows


def build_report(results, title, headline_pair):
    L = []
    L.append(f"# {title}\n")
    L.append(f"生成时间：由 generate_report.py 自动产出。评测环境：Mac（Apple M5，Metal），llama.cpp b11857，"
             f"同机同脚本同语料同参数（--jinja、temp 0.7、ctx 2048、max 512 tokens）。\n")

    # ============ 专业版 ============
    L.append("## 一、专业数据\n")
    L.append("### 1. 困惑度 PPL（越低越好）\n")
    L.append("| 模型 | 档位 | 目标域 PPL | 通用域 PPL |")
    L.append("|---|---|---|---|")
    for tag, e in model_rows(results):
        L.append(f"| {GROUP_LABEL.get(e['group'], e['group'])} | {e['quant']} | "
                 f"{fmt_ppl(e['ppl_target'])} | {fmt_ppl(e['ppl_general'])} |")
    L.append("")

    L.append("### 2. 生成质量（15 题：翻译 chrF / 其余题关键词覆盖 / 问题检出）\n")
    L.append("| 模型 | 档位 | 翻译 chrF | 关键词覆盖 | 有问题题数 | 红灯判定 |")
    L.append("|---|---|---|---|---|---|")
    for tag, e in model_rows(results):
        if "per_prompt" not in e:
            continue
        chrfs = [p["chrf"] for p in e["per_prompt"] if "chrf" in p]
        kcovs = [p["kcov"] for p in e["per_prompt"] if "kcov" in p]
        nprob = sum(1 for p in e["per_prompt"] if p["problems"])
        L.append(f"| {GROUP_LABEL.get(e['group'], e['group'])} | {e['quant']} | "
                 f"{sum(chrfs) / len(chrfs):.3f} | {sum(kcovs) / len(kcovs):.1%} | "
                 f"{nprob}/15 | {'PASS' if e['pass'] else 'RED(' + ','.join(e['red_cats']) + ')'} |")
    L.append("")

    L.append("### 3. 速度与内存\n")
    L.append("| 模型 | 档位 | 文件大小 | 生成速度 | 提示处理速度 | 峰值内存（实测 RSS） |")
    L.append("|---|---|---|---|---|---|")
    for tag, e in model_rows(results):
        L.append(f"| {GROUP_LABEL.get(e['group'], e['group'])} | {e['quant']} | {mb(e['file_size'])} | "
                 f"{e['bench_tg_ts']:.0f} t/s | {e['bench_pp_ts']:.0f} t/s | "
                 f"{mb(e['rss_bytes']) if e['rss_bytes'] else 'N/A'} |")
    L.append("")

    L.append("### 4. 拆解分析\n")
    # 训练增益：同档位 原版 → 我们（自动识别训练组，冒烟=sft1、正式=sft2）
    groups = {}
    for tag, e in results.items():
        groups.setdefault(e["quant"], {})[e["group"]] = (tag, e)
    trained_groups = sorted({e["group"] for e in results.values() if e["group"] != "orig"})
    for tg_grp in trained_groups:
        L.append(f"**训练增益（同档位，原版 → {GROUP_LABEL.get(tg_grp, tg_grp)}，目标域 PPL 降幅）：**\n")
        for q in QUANT_ORDER:
            if q in groups and "orig" in groups[q] and tg_grp in groups[q]:
                o, s = groups[q]["orig"][1], groups[q][tg_grp][1]
                if "pass" in o and "pass" in s:
                    verdict = f"；生成判定 {'RED' if not o['pass'] else 'PASS'} → {'PASS' if s['pass'] else 'RED'}"
                else:
                    verdict = ""
                L.append(f"- {q}：PPL {o['ppl_target'][0]:.2f} → {s['ppl_target'][0]:.2f}"
                         f"（{pct(s['ppl_target'][0], o['ppl_target'][0])}）{verdict}")
        L.append("")
        # 量化代价：该组 F16 → 各档
        if "F16" in groups and tg_grp in groups["F16"]:
            base = groups["F16"][tg_grp][1]
            L.append(f"**量化代价（{GROUP_LABEL.get(tg_grp, tg_grp)} F16 → 各档）：**\n")
            for q in QUANT_ORDER:
                if q != "F16" and q in groups and tg_grp in groups[q]:
                    s = groups[q][tg_grp][1]
                    L.append(f"- {q}：体积 {mb(base['file_size'])} → {mb(s['file_size'])}"
                             f"（{pct(s['file_size'], base['file_size'])}），PPL {base['ppl_target'][0]:.2f} → "
                             f"{s['ppl_target'][0]:.2f}（{pct(s['ppl_target'][0], base['ppl_target'][0])}），"
                             f"生成速度 {base['bench_tg_ts']:.0f} → {s['bench_tg_ts']:.0f} t/s")
            L.append("")

    # ============ 大众版 ============
    L.append("## 二、大众版（不用懂技术）\n")
    L.append("### 1. 日常任务通过率\n")
    L.append("模型在 15 道日常任务题（翻译、记录整理、日程、消息、摘要各 3 题）上的表现：\n")
    L.append("| 模型 | 档位 | 通过题数 | 通过率 |")
    L.append("|---|---|---|---|")
    for tag, e in model_rows(results):
        if "per_prompt" not in e:
            continue
        ok = sum(1 for p in e["per_prompt"] if not p["problems"])
        L.append(f"| {GROUP_LABEL.get(e['group'], e['group'])} | {e['quant']} | "
                 f"{ok}/15 | {ok / 15:.0%} |")
    L.append("")

    L.append("### 2. 速度：一秒钟能写多少字\n")
    L.append("（按中文平均 1.6 字/词元换算，估算值）\n")
    L.append("| 模型 | 档位 | 每秒生成字数 | 生成一条 100 字回复耗时 |")
    L.append("|---|---|---|---|")
    for tag, e in model_rows(results):
        cps = e["bench_tg_ts"] * CHARS_PER_TOKEN
        t100 = 100 / cps
        L.append(f"| {GROUP_LABEL.get(e['group'], e['group'])} | {e['quant']} | "
                 f"约 {cps:,.0f} 字 | {t100:.2f} 秒 |")
    L.append("")

    L.append("### 3. 内存：装进手机占多少\n")
    L.append("（按 iPhone 12GB 内存估算，模型文件 + 运行时开销）\n")
    L.append("| 模型 | 档位 | 模型文件 | 运行时实测占用 | 占 12GB 手机比例 |")
    L.append("|---|---|---|---|---|")
    for tag, e in model_rows(results):
        rss = e.get("rss_bytes")
        L.append(f"| {GROUP_LABEL.get(e['group'], e['group'])} | {e['quant']} | {mb(e['file_size'])} | "
                 f"{mb(rss) if rss else 'N/A'} | {rss / 12e9:.1%} |" if rss else
                 f"| {GROUP_LABEL.get(e['group'], e['group'])} | {e['quant']} | {mb(e['file_size'])} | N/A | N/A |")
    L.append("")

    L.append("### 4. 实际效果对比（原版 vs 我们，同一道题）\n")
    if headline_pair and "," in headline_pair:
        a, b = headline_pair.split(",")
        if a in results and b in results:
            la = GROUP_LABEL.get(results[a]["group"], a)
            lb = GROUP_LABEL.get(results[b]["group"], b)
            L.append(f"左：**{la} {results[a]['quant']}**　右：**{lb} {results[b]['quant']}**\n")
            # 每类任务挑一题：translate#1 / record#2 / schedule#1 / message#3 / summary#2
            picks = {"translate": 0, "record": 1, "schedule": 0, "message": 2, "summary": 1}
            cats = ["translate", "record", "schedule", "message", "summary"]
            for pos, cat in enumerate(cats):
                idx = pos * 3 + picks[cat]
                pa = results[a]["per_prompt"][idx]
                pb = results[b]["per_prompt"][idx]
                L.append(f"#### {cat} 任务\n")
                L.append(f"> {pa['prompt'][:60]}\n")
                L.append(f"**{la}**：{pa['text'][:350]}\n")
                L.append(f"**{lb}**：{pb['text'][:350]}\n")
            L.append("> 完整 15 题输出存档在各模型目录 gen_*.txt。")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="0.6B 模型训练前后对比评测报告")
    ap.add_argument("--headline-pair", default="")
    args = ap.parse_args()
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    # per_prompt 里补 text（脚本目前没存全文，从 gen_*.txt 读）
    report = build_report(results, args.title, args.headline_pair)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"OK -> {args.out}")


if __name__ == "__main__":
    main()
