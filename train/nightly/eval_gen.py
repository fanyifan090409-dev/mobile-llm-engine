#!/usr/bin/env python3
"""生成评测：五类手机高频任务 ×3 prompt，llama-cli 单轮生成 + 规则检查 + 报告。

规则（自动可判，宁漏勿误报）：
- 空回复（<8 字符）
- 3-gram 循环重复 ≥5 次（复读机）
- 结尾 8 字符片段重复 ≥2 次（"的。的。"式循环）
- 疑似截断（达到 max-tokens 且结尾无句末标点）
红灯判定：≥2 类任务红灯 → 该档模型质量红灯（触发加训）。

用法：
  python3 eval_gen.py --model <gguf> --llama-cli <path> --out <dir> [--tag Q8_0]
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

END_TOKENS = "。！？!?.…"
# 复读判定只认「含实际内容」的 3-gram：Markdown 格式符号（\n**、  *、-）不算复读
MEANINGFUL = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def check_text(text, max_tokens):
    problems = []
    t = text.strip()
    if len(t) < 8:
        return ["空回复"]
    # 3-gram 复读
    grams = [t[i:i + 3] for i in range(len(t) - 2)]
    for g, n in Counter(grams).items():
        if n >= 5 and MEANINGFUL.search(g):
            problems.append(f"复读({g!r}x{n})")
            break
    # 结尾 8 字符片段循环
    tail = t[-8:]
    if len(t) >= 20 and t.endswith(tail + tail):
        problems.append("尾部循环")
    # 截断
    if len(t) >= max_tokens - 20 and not re.search(f"[{END_TOKENS}]$", t):
        problems.append("疑似截断")
    return problems


def run_cli(cli, model, prompt, max_tokens=512):
    # 实测（b11857）：徽标/加载信息/prompt 回显全部走 stdout，--simple-io 关不掉徽标，
    # 所以从 "> {prompt}" 回显标记后截取生成文本，到 "[ Prompt:" 统计行为止；
    # 不解析会误判复读（徽标 ██ x25）
    r = subprocess.run(
        [cli, "-m", model, "-p", prompt, "-st", "-n", str(max_tokens),
         "--temp", "0.7", "-c", "2048", "--jinja"],
        capture_output=True, text=True, timeout=300,
    )
    out = r.stdout
    marker = f"> {prompt}"
    if marker in out:
        out = out.split(marker, 1)[1]
    if "[ Prompt:" in out:
        out = out.split("[ Prompt:", 1)[0]
    out = out.replace("Exiting...", "")
    # Qwen3 的 eos 有时没被当 stop，会残留在尾部
    out = out.replace("<|im_end|>", "").strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--llama-cli", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--skip-cats", default="", help="逗号分隔，跳过类别（其他档抽样用）")
    ap.add_argument("--sample-only", action="store_true", help="每类只跑 1 个 prompt（非判定档提速）")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    skip = {s for s in args.skip_cats.split(",") if s}

    results = {}
    for cat, prompts in PROMPTS.items():
        if cat in skip:
            continue
        if args.sample_only:
            prompts = prompts[:1]
        results[cat] = []
        for i, p in enumerate(prompts):
            text = run_cli(args.llama_cli, args.model, p, args.max_tokens)
            probs = check_text(text, args.max_tokens)
            results[cat].append({"prompt": p, "text": text, "problems": probs})
            (outdir / f"{args.tag}_{cat}_{i+1}.txt").write_text(
                f"PROMPT: {p}\n\n--- 生成 ---\n{text}\n\n--- 问题 ---\n{probs or '无'}\n",
                encoding="utf-8",
            )
            print(f"[{args.tag}] {cat}#{i+1} 问题={probs or '无'} 长度={len(text)}", flush=True)

    # 判定：类别红灯 = 该类全部 prompt 都有问题（抽样档不参与判定）
    if args.sample_only:
        print("JUDGE: 抽样档，不参与红灯判定")
        return
    red_cats = [c for c, items in results.items() if items and all(i["problems"] for i in items)]
    red = len(red_cats) >= 2
    print(f"JUDGE: 红灯类别={red_cats or '无'} 总体={'RED' if red else 'PASS'}")
    (outdir / f"{args.tag}_judge.json").write_text(
        json.dumps({"red": red, "red_cats": red_cats, "results": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    sys.exit(2 if red else 0)


if __name__ == "__main__":
    main()
