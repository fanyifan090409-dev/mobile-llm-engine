#!/usr/bin/env python3
"""训练前后对比评测：按 manifest 对每个模型跑双语料 PPL + 速度 + 生成质量 + 峰值内存。

指标：
- PPL：目标域（SFT 同源语料）+ 通用域（fineweb2 抽样），llama-perplexity
- 速度：llama-bench（pp_ts 提示处理 / tg_ts 生成速度，token/s）
- 生成质量：15 prompt 规则检查（复读/截断/空回复）+ 翻译 chrF 参考分 + 其余题关键词覆盖分
- 内存：/usr/bin/time -l 峰值 RSS（macOS）+ GGUF 文件大小

输出：work/compare/<tag>/ 原始产物 + results.json 汇总。

用法：
  python3 eval_compare.py --manifest compare_manifest.json --work <dir> --llama-bin <dir>
"""
import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

PROMPTS = {
    "translate": [
        "把这句话翻译成英文：这个会议的议程有变化，请你通知所有人明天上午十点准时参加。",
        "翻译成中文：Please make sure the report is submitted by Friday, otherwise the approval process will be delayed.",
        "帮我把这段介绍翻译成日语：我们公司专注于移动端人工智能应用开发，总部位于上海。",
    ],
    "record": [
        "整理一下这段会议记录，去掉口头禅和重复内容：呃那个我们今天的会主要就是讨论一下下个季度的目标，然后那个小王负责市场推广，嗯小李负责产品设计，还有那个预算问题，我们要在月底之前定下来，月底之前啊。",
        "把这段语音转写整理成要点：老板说今天下午三点有个客户要来，让我们把会议室准备好，还有演示用的PPT要再检查一遍，另外客户对价格比较敏感，报价的时候要留点空间。",
        "整理以下杂乱笔记：打车35块；午餐28；买书128；报销单明天交；财务说打车费可以报，餐费不行。",
    ],
    "schedule": [
        "帮我安排明天下午两点跟张经理的会议，时长一个小时，地点三号会议室，提前十五分钟提醒我。",
        "我下周三要去北京出差三天，帮我列出需要准备的事项清单。",
        "查一下我本周五上午有没有安排，如果没有就帮我约上午十点的牙医。",
    ],
    "message": [
        "帮我回复这条消息，语气礼貌一点：王总，上次说的那个合同，您看什么时候方便签一下？",
        "帮我把这条微信改得委婉一点：你的方案有问题，预算超了，重新做。",
        "根据以下信息生成一条群公告：周六上午九点公司团建，地点在郊野公园，大巴八点从公司门口出发，请穿运动鞋，风雨无阻。",
    ],
    "summary": [
        "用三句话总结这段文字：人工智能技术在医疗领域的应用越来越广泛，从影像诊断到药物研发都有涉及。影像诊断方面，AI可以辅助医生识别早期病变，准确率已经接近资深医生水平。药物研发方面，AI能够大幅缩短候选化合物的筛选时间。此外，AI还在健康管理、手术机器人等方向发挥作用，但数据隐私和算法偏见问题仍然需要解决。",
        "帮我总结这篇新闻的要点：今日上午，市交通部门宣布地铁五号线延长段正式开通，新增六个站点，覆盖三个大型居住区。延长段采用全自动驾驶技术，高峰期发车间隔缩短至两分钟。同时公交集团调整了十二条线路与地铁接驳，方便市民换乘。",
        "把这段产品介绍压缩成一条一百字以内的卖点文案：这款智能手表采用钛合金表壳，重量仅42克，支持全天候心率监测、血氧检测和睡眠分析。续航方面，正常使用可达七天，快充十五分钟可用一天。它内置了五十多种运动模式，支持五十米防水，并且兼容安卓和iOS双平台，可以接收通知、控制音乐和移动支付。",
    ],
}

# 翻译题参考译文（chrF 打分；字符级容许多种合理译法）
TRANSLATE_REFS = {
    "translate#1": "The agenda for this meeting has changed. Please notify everyone to attend on time at ten o'clock tomorrow morning.",
    "translate#2": "请确保报告在周五之前提交，否则审批流程将会延迟。",
    "translate#3": "当社はモバイル向け人工知能アプリケーションの開発に特化しており、本社は上海にあります。",
}

# 非翻译题的内容要点（关键词覆盖分：生成里出现即得分，客观可判）
KEYWORDS = {
    "record#1": ["季度", "目标", "市场", "小王", "产品", "小李", "预算", "月底"],
    "record#2": ["三点", "客户", "会议室", "PPT", "报价"],
    "record#3": ["35", "28", "128", "报销", "餐费"],
    "schedule#1": ["两点", "张经理", "一个小时", "三号", "十五分钟"],
    "schedule#2": ["周三", "北京", "三天", "清单"],
    "schedule#3": ["周五", "牙医", "十点"],
    "message#1": ["王总", "合同", "签"],
    "message#2": ["方案", "预算", "重新"],
    "message#3": ["周六", "九点", "9点", "团建", "公园", "大巴", "八点", "8点", "运动鞋"],
    "summary#1": ["医疗", "影像", "药物", "研发"],
    "summary#2": ["五号线", "站点", "自动驾驶", "公交"],
    "summary#3": ["手表", "42", "续航", "防水"],
}

END_TOKENS = "。！？!?.…"
MEANINGFUL = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")

CLI_ARGS = ["-st", "-n", "512", "--temp", "0.7", "-c", "2048", "--jinja", "-ngl", "99", "-t", "8"]


def check_text(text, max_tokens=512):
    problems = []
    t = text.strip()
    if len(t) < 8:
        return ["空回复"]
    grams = [t[i:i + 3] for i in range(len(t) - 2)]
    for g, n in Counter(grams).items():
        if n >= 5 and MEANINGFUL.search(g):
            problems.append(f"复读({g!r}x{n})")
            break
    tail = t[-8:]
    if len(t) >= 20 and t.endswith(tail + tail):
        problems.append("尾部循环")
    if len(t) >= max_tokens - 20 and not re.search(f"[{END_TOKENS}]$", t):
        problems.append("疑似截断")
    return problems


def run_cli(cli, model, prompt, max_tokens=512):
    # 徽标/加载信息走 stdout：从 "> {prompt}" 回显标记后截取，到 "[ Prompt:" 为止
    r = subprocess.run(
        [cli, "-m", model, "-p", prompt] + CLI_ARGS,
        capture_output=True, text=True, timeout=300,
    )
    out = r.stdout
    marker = f"> {prompt}"
    if marker in out:
        out = out.split(marker, 1)[1]
    if "[ Prompt:" in out:
        out = out.split("[ Prompt:", 1)[0]
    out = out.replace("Exiting...", "").replace("<|im_end|>", "").strip()
    return out


def chrf(hyp, ref, max_n=6, beta=2.0):
    # 词级 chrF（sacreBLEU 标准：中文经 jieba 分词，空格保留在字符序列里参与 n-gram）
    try:
        import jieba
        h = " ".join(jieba.lcut(hyp))
        r = " ".join(jieba.lcut(ref))
    except ImportError:
        h, r = hyp, ref
    if not h or not r:
        return 0.0
    precs, recs = [], []
    for n in range(1, max_n + 1):
        hn = Counter(h[i:i + n] for i in range(len(h) - n + 1))
        rn = Counter(r[i:i + n] for i in range(len(r) - n + 1))
        match = sum((hn & rn).values())
        precs.append(match / max(1, sum(hn.values())))
        recs.append(match / max(1, sum(rn.values())))
    prec = sum(precs) / len(precs)
    rec = sum(recs) / len(recs)
    if prec + rec == 0:
        return 0.0
    return (1 + beta ** 2) * prec * rec / (beta ** 2 * prec + rec)


THINK_RE = re.compile(r"\[Start thinking\].*?\[End thinking\]", re.S)


def strip_thinking(text):
    # 原版默认开思考模式：打分前剥掉思考块，只评内容部分（问题检查仍用原文）
    return THINK_RE.sub("", text).strip() or text


def run_ppl(bin_dir, model, corpus, out_txt):
    r = subprocess.run(
        [str(bin_dir / "llama-perplexity"), "-m", model, "-f", corpus, "-ngl", "99", "-t", "8"],
        capture_output=True, text=True, timeout=900,
    )
    # llama.cpp 日志走 stderr：Final estimate 在 stderr，进度行在 stdout，两处合并找
    m = re.search(r"Final estimate: PPL = ([\d.]+) \+/- ([\d.]+)", r.stdout + r.stderr)
    if not m:
        raise RuntimeError(f"PPL 解析失败: {(r.stdout + r.stderr)[-300:]}")
    mean, std = float(m.group(1)), float(m.group(2))
    out_txt.write_text(f"{mean} {std}\n", encoding="utf-8")
    return mean, std


def run_bench(bin_dir, model, out_json):
    r = subprocess.run(
        [str(bin_dir / "llama-bench"), "-m", model, "-p", "512", "-n", "128", "-r", "5",
         "-o", "json", "-ngl", "99", "-t", "8"],
        capture_output=True, text=True, timeout=900,
    )
    out_json.write_text(r.stdout, encoding="utf-8")
    i = r.stdout.find("[")
    data = json.loads(r.stdout[i:])
    pp = next((e["avg_ts"] for e in data if e.get("n_gen") == 0), None)
    tg = next((e["avg_ts"] for e in data if e.get("n_gen") and e.get("n_gen") > 0), None)
    return pp, tg


def run_rss(bin_dir, model):
    # macOS /usr/bin/time -l 输出 "       123456  maximum resident set size"（列对齐无等号）
    prompt = PROMPTS["summary"][1]
    r = subprocess.run(
        ["/usr/bin/time", "-l", str(bin_dir / "llama-cli"), "-m", model, "-p", prompt] + CLI_ARGS,
        capture_output=True, text=True, timeout=300,
    )
    m = re.search(r"(\d+)\s+maximum resident set size", r.stderr)
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--llama-bin", required=True)
    ap.add_argument("--skip-gen", action="store_true", help="跳过生成评测（冒烟 PPL/速度用）")
    args = ap.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    bin_dir = Path(args.llama_bin)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    results = {}
    for spec in manifest["models"]:
        tag, gguf = spec["tag"], spec["gguf"]
        if not Path(gguf).exists():
            print(f"[{tag}] GGUF 不存在，跳过: {gguf}", flush=True)
            continue
        outdir = work / tag
        outdir.mkdir(parents=True, exist_ok=True)
        entry = {"group": spec.get("group", ""), "quant": spec.get("quant", ""),
                 "file_size": Path(gguf).stat().st_size}

        print(f"[{tag}] bench（冷态优先，速度更稳）...", flush=True)
        entry["bench_pp_ts"], entry["bench_tg_ts"] = run_bench(bin_dir, gguf, outdir / "bench.json")
        print(f"[{tag}] PPL 目标域...", flush=True)
        entry["ppl_target"] = run_ppl(bin_dir, gguf, manifest["corpora"]["target"],
                                      outdir / "ppl_target.txt")
        print(f"[{tag}] PPL 通用域...", flush=True)
        entry["ppl_general"] = run_ppl(bin_dir, gguf, manifest["corpora"]["general"],
                                       outdir / "ppl_general.txt")
        print(f"[{tag}] RSS...", flush=True)
        entry["rss_bytes"] = run_rss(bin_dir, gguf)

        if args.skip_gen:
            results[tag] = entry
            continue

        print(f"[{tag}] 生成评测 15 prompt...", flush=True)
        per_prompt = []
        red_cats = []
        for cat, prompts in PROMPTS.items():
            cat_problems = []
            for i, p in enumerate(prompts):
                text = run_cli(str(bin_dir / "llama-cli"), gguf, p)
                probs = check_text(text)
                key = f"{cat}#{i + 1}"
                scored = strip_thinking(text)
                # 数字格式归一（9:00/9点 统一为 9点），避免同一语义被格式差异扣分
                scored = re.sub(r"(\d{1,2}):00", r"\1点", scored)
                item = {"cat": cat, "idx": i + 1, "prompt": p, "text": text, "problems": probs}
                if key in TRANSLATE_REFS:
                    item["chrf"] = round(chrf(scored, TRANSLATE_REFS[key]), 4)
                if key in KEYWORDS:
                    hit = sum(1 for k in KEYWORDS[key] if k in scored)
                    item["kcov"] = round(hit / len(KEYWORDS[key]), 4)
                per_prompt.append(item)
                cat_problems.append(probs)
                (outdir / f"gen_{cat}_{i + 1}.txt").write_text(
                    f"PROMPT: {p}\n\n--- 生成 ---\n{text}\n\n--- 问题 ---\n{probs or '无'}\n",
                    encoding="utf-8",
                )
                print(f"  {key} 问题={probs or '无'} chrf={item.get('chrf')} kcov={item.get('kcov')}", flush=True)
            if cat_problems and all(cat_problems):
                red_cats.append(cat)
        entry["per_prompt"] = per_prompt
        entry["red_cats"] = red_cats
        entry["pass"] = len(red_cats) < 2
        results[tag] = entry
        print(f"[{tag}] 判定: {'PASS' if entry['pass'] else 'RED'} 红灯={red_cats or '无'}", flush=True)

    (work / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
